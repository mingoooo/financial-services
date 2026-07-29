from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from scripts.vcp_lib.data_sources import (
    cache_path,
    frame_to_serializable_records,
    load_json_cache,
    load_yfinance_history,
    normalize_daily_ohlcv_frame,
    serializable_records_to_frame,
    write_json_cache,
)

DEFAULT_BATCH_SIZE = 25
DEFAULT_TIMEOUT = 20
DEFAULT_RETRIES = 2
_MARKET_TZ = ZoneInfo('America/New_York')
_INCREMENTAL_OVERLAP_DAYS = 5


@dataclass
class SymbolLoadStatus:
    symbol: str
    status: str
    source: str
    rows: int = 0
    attempts: int = 0
    message: str | None = None


@dataclass
class DailyDataLoadResult:
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    statuses: dict[str, SymbolLoadStatus] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


BatchDownloadFn = Callable[..., pd.DataFrame | None]
HistoryLoaderFn = Callable[..., pd.DataFrame | None]
EventFetcherFn = Callable[[], Any]


def build_scan_window_key(*, as_of: str | None = None, period: str = '1y', interval: str = '1d') -> str:
    return f'{as_of or "latest"}_{period}_{interval}'


def _append_warning(warnings: list[str], message: str) -> None:
    if message not in warnings:
        warnings.append(message)


def _is_timeout_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return isinstance(exc, TimeoutError) or 'timed out' in text or 'timeout' in text


def _is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return 'rate limit' in text or 'too many requests' in text or '429' in text


def _ohlcv_namespace(window_key: str) -> str:
    return f'oneil_scanner/ohlcv/{window_key}'


def _events_namespace(window_key: str) -> str:
    return f'oneil_scanner/events/{window_key}'


def _cache_key_for_symbol(symbol: str) -> str:
    return symbol.upper()


def _event_cache_key(scope: str) -> str:
    return scope.replace(':', '_')


def _event_result_metadata(scope: str, source: str, warnings: list[str]) -> dict[str, Any]:
    return {
        'scope': scope,
        'source': source,
        'warning_count': len(warnings),
        'warnings': list(warnings),
        'run_metadata': {
            'warnings': list(warnings),
        },
    }


def _cached_event_warnings(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get('warnings')
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


def _serialize_frame(frame: pd.DataFrame) -> dict:
    payload = frame.copy()
    payload['Date'] = pd.to_datetime(payload['Date'])
    return {
        'frame': frame_to_serializable_records(payload.set_index('Date')),
        'fetched_at': _today_market_date(),
        'last_date': payload['Date'].max().date().isoformat() if not payload.empty else None,
    }


def _today_market_date() -> str:
    return datetime.now(_MARKET_TZ).date().isoformat()


def _frame_last_date(frame: pd.DataFrame | None) -> str | None:
    if frame is None or frame.empty or 'Date' not in frame.columns:
        return None
    return pd.to_datetime(frame['Date']).max().date().isoformat()


def _cache_frame_payload(payload: dict | list | None) -> dict | None:
    if not isinstance(payload, dict):
        return None
    frame_payload = payload.get('frame')
    if isinstance(frame_payload, dict):
        return frame_payload
    if payload.get('kind') in {'single', 'multi'}:
        return payload
    return None


def _cache_fetched_at(payload: dict | list | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    fetched_at = payload.get('fetched_at')
    if fetched_at is None:
        return None
    return str(fetched_at)


def _cache_last_date(payload: dict | list | None, frame: pd.DataFrame | None) -> str | None:
    if isinstance(payload, dict) and payload.get('last_date'):
        return str(payload['last_date'])
    return _frame_last_date(frame)


def _cache_is_current_for_target(*, payload: dict | list | None, frame: pd.DataFrame | None, as_of: str | None) -> bool:
    if as_of:
        return frame is not None and not frame.empty
    cached_last_date = _cache_last_date(payload, frame)
    if cached_last_date is None:
        return False
    return _cache_fetched_at(payload) == _today_market_date()


def _window_key_is_latest(window_key: str) -> bool:
    return str(window_key).startswith('latest_')


def _event_cache_is_current(payload: Any, *, window_key: str) -> bool:
    if not isinstance(payload, dict):
        return False
    if not _window_key_is_latest(window_key):
        return True
    fetched_at = _cache_fetched_at(payload)
    if fetched_at is None:
        return False
    return fetched_at[:10] == _today_market_date()


def _refresh_start_date(cached_last_date: str | None, *, period: str, as_of: str | None) -> str | None:
    if cached_last_date:
        last_date = datetime.fromisoformat(cached_last_date).date()
        return (last_date - timedelta(days=_INCREMENTAL_OVERLAP_DAYS)).isoformat()
    if period.endswith('y'):
        years = max(1, int(period[:-1] or '1'))
        anchor = datetime.fromisoformat(as_of).date() if as_of else datetime.now(_MARKET_TZ).date()
        return (anchor - timedelta(days=366 * years)).isoformat()
    if period.endswith('mo'):
        months = max(1, int(period[:-2] or '1'))
        anchor = datetime.fromisoformat(as_of).date() if as_of else datetime.now(_MARKET_TZ).date()
        return (anchor - timedelta(days=31 * months)).isoformat()
    return None


def _refresh_end_date(as_of: str | None) -> str | None:
    if not as_of:
        return None
    return (datetime.fromisoformat(as_of).date() + timedelta(days=1)).isoformat()


def _merge_frames(cached: pd.DataFrame, live_update: pd.DataFrame | None) -> pd.DataFrame:
    if live_update is None or live_update.empty:
        return normalize_daily_ohlcv_frame(cached)
    merged = pd.concat([cached, live_update], ignore_index=True)
    merged['Date'] = pd.to_datetime(merged['Date'])
    merged = merged.sort_values('Date').drop_duplicates(subset=['Date'], keep='last')
    return normalize_daily_ohlcv_frame(merged)


def _restore_frame(payload: dict | list | None) -> pd.DataFrame | None:
    frame_payload = _cache_frame_payload(payload)
    if frame_payload is None:
        return None
    restored = serializable_records_to_frame(frame_payload)
    if restored is None or restored.empty:
        return None
    return normalize_daily_ohlcv_frame(restored)


def _extract_frames_by_symbol(data: pd.DataFrame | None, symbols: list[str]) -> dict[str, pd.DataFrame]:
    if data is None or data.empty:
        return {}

    frames: dict[str, pd.DataFrame] = {}
    if isinstance(data.columns, pd.MultiIndex):
        available_symbols = set(data.columns.get_level_values(0))
        for symbol in symbols:
            if symbol not in available_symbols:
                continue
            normalized = normalize_daily_ohlcv_frame(data[symbol])
            if not normalized.empty:
                frames[symbol] = normalized
        return frames

    if len(symbols) == 1:
        normalized = normalize_daily_ohlcv_frame(data)
        if not normalized.empty:
            frames[symbols[0]] = normalized
    return frames


def _default_download(symbols: list[str], **kwargs: Any) -> pd.DataFrame | None:
    return yf.download(
        tickers=' '.join(symbols),
        group_by='ticker',
        threads=False,
        progress=False,
        auto_adjust=False,
        **kwargs,
    )


def _default_history_loader(symbol: str, **kwargs: Any) -> pd.DataFrame | None:
    return load_yfinance_history(symbol, auto_adjust=False, **kwargs)


def fetch_event_payload(
    scope: str,
    *,
    fetcher: EventFetcherFn,
    cache_dir: str | Path,
    window_key: str,
    retries: int = DEFAULT_RETRIES,
    warnings: list[str] | None = None,
    refresh: bool = False,
) -> tuple[Any, dict[str, Any]]:
    event_warnings = warnings if warnings is not None else []
    target = cache_path(Path(cache_dir), _events_namespace(window_key), _event_cache_key(scope))
    cached = load_json_cache(target)
    cached_warnings = _cached_event_warnings(cached)
    for warning in cached_warnings:
        _append_warning(event_warnings, warning)
    merged_cached_warnings = list(cached_warnings)
    for warning in event_warnings:
        _append_warning(merged_cached_warnings, warning)
    if not refresh and isinstance(cached, dict) and 'payload' in cached and _event_cache_is_current(cached, window_key=window_key):
        return cached['payload'], _event_result_metadata(scope, 'cache', merged_cached_warnings)

    last_error: Exception | None = None
    for attempt in range(1, retries + 2):
        try:
            payload = fetcher()
            if payload in (None, [], {}):
                _append_warning(event_warnings, f'Sparse event data for {scope}; continuing without enrichment.')
            write_json_cache(
                target,
                {
                    'fetched_at': datetime.now(UTC).isoformat(timespec='seconds'),
                    'payload': payload,
                    'warnings': list(event_warnings),
                },
            )
            return payload, _event_result_metadata(scope, 'live', event_warnings)
        except Exception as exc:
            last_error = exc
            if _is_timeout_error(exc):
                _append_warning(event_warnings, f'Event fetch timeout for {scope}; using cached data when available.')
            if _is_rate_limit_error(exc):
                _append_warning(event_warnings, f'Event rate-limit degradation for {scope}; scan continues with reduced enrichment.')
            if attempt > retries:
                break

    if isinstance(cached, dict) and 'payload' in cached:
        fallback_warnings = list(cached_warnings)
        for warning in event_warnings:
            _append_warning(fallback_warnings, warning)
        for warning in fallback_warnings:
            _append_warning(event_warnings, warning)
        return cached['payload'], _event_result_metadata(scope, 'cache-fallback', fallback_warnings)

    if last_error is not None and not (_is_timeout_error(last_error) or _is_rate_limit_error(last_error)):
        _append_warning(event_warnings, f'Event fetch failed for {scope}: {last_error}')
    return None, _event_result_metadata(scope, 'unavailable', event_warnings)


def load_daily_ohlcv(
    symbols: list[str],
    *,
    cache_dir: str | Path,
    as_of: str | None = None,
    period: str = '1y',
    interval: str = '1d',
    batch_size: int = DEFAULT_BATCH_SIZE,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    refresh: bool = False,
    download_fn: BatchDownloadFn | None = None,
    history_loader: HistoryLoaderFn | None = None,
) -> DailyDataLoadResult:
    ordered_symbols = [symbol.strip().upper() for symbol in symbols if symbol and symbol.strip()]
    result = DailyDataLoadResult()
    window_key = build_scan_window_key(as_of=as_of, period=period, interval=interval)
    target_cache_dir = Path(cache_dir)
    download = download_fn or _default_download
    load_history = history_loader or _default_history_loader
    stale_cached_frames: dict[str, pd.DataFrame] = {}
    stale_cached_payloads: dict[str, dict | list | None] = {}

    for symbol in ordered_symbols:
        cache_file = cache_path(target_cache_dir, _ohlcv_namespace(window_key), _cache_key_for_symbol(symbol))
        cached_payload = load_json_cache(cache_file)
        cached = _restore_frame(cached_payload)
        if cached is None or cached.empty:
            continue
        if not refresh and _cache_is_current_for_target(payload=cached_payload, frame=cached, as_of=as_of):
            result.frames[symbol] = cached
            result.statuses[symbol] = SymbolLoadStatus(symbol=symbol, status='ok', source='cache', rows=len(cached), attempts=0)
            continue
        stale_cached_frames[symbol] = cached
        stale_cached_payloads[symbol] = cached_payload

    misses = [symbol for symbol in ordered_symbols if symbol not in result.frames and symbol not in stale_cached_frames]
    for start in range(0, len(misses), max(1, batch_size)):
        batch = misses[start:start + max(1, batch_size)]
        batch_frames: dict[str, pd.DataFrame] = {}
        batch_error: Exception | None = None

        for attempt in range(1, retries + 2):
            try:
                batch_frames = _extract_frames_by_symbol(
                    download(batch, period=period, interval=interval, timeout=timeout),
                    batch,
                )
                batch_error = None
                break
            except Exception as exc:
                batch_error = exc
                if attempt > retries:
                    break

        if batch_error is not None:
            if _is_timeout_error(batch_error):
                _append_warning(result.warnings, f'OHLCV batch timeout for {", ".join(batch)}; falling back to symbol loads.')
            elif _is_rate_limit_error(batch_error):
                _append_warning(result.warnings, f'OHLCV rate-limit degradation for {", ".join(batch)}; falling back to symbol loads.')
            else:
                _append_warning(result.warnings, f'OHLCV batch fetch failed for {", ".join(batch)}; falling back to symbol loads.')

        for symbol, frame in batch_frames.items():
            result.frames[symbol] = frame
            result.statuses[symbol] = SymbolLoadStatus(symbol=symbol, status='ok', source='live', rows=len(frame), attempts=1)
            write_json_cache(
                cache_path(target_cache_dir, _ohlcv_namespace(window_key), _cache_key_for_symbol(symbol)),
                _serialize_frame(frame),
            )

        missing_symbols = [symbol for symbol in batch if symbol not in batch_frames]
        if batch_frames and missing_symbols:
            _append_warning(result.warnings, f'Partial OHLCV batch coverage; retrying individually for {", ".join(missing_symbols)}.')

        for symbol in missing_symbols if batch_frames else batch:
            if symbol in result.frames:
                continue
            last_error: Exception | None = None
            for attempt in range(1, retries + 2):
                try:
                    frame = normalize_daily_ohlcv_frame(
                        load_history(symbol, period=period, interval=interval, timeout=timeout),
                    )
                    if frame.empty:
                        raise RuntimeError(f'No daily data for {symbol}')
                    result.frames[symbol] = frame
                    result.statuses[symbol] = SymbolLoadStatus(symbol=symbol, status='ok', source='live', rows=len(frame), attempts=attempt)
                    write_json_cache(
                        cache_path(target_cache_dir, _ohlcv_namespace(window_key), _cache_key_for_symbol(symbol)),
                        _serialize_frame(frame),
                    )
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt > retries:
                        break
            if last_error is None:
                continue
            status = 'timeout' if _is_timeout_error(last_error) else 'error'
            if status == 'timeout':
                _append_warning(result.warnings, f'OHLCV timeout for {symbol}; symbol skipped.')
            elif _is_rate_limit_error(last_error):
                _append_warning(result.warnings, f'OHLCV rate-limit degradation for {symbol}; symbol skipped.')
            else:
                _append_warning(result.warnings, f'OHLCV load failed for {symbol}; symbol skipped.')
            result.statuses[symbol] = SymbolLoadStatus(
                symbol=symbol,
                status=status,
                source='live',
                rows=0,
                attempts=retries + 1,
                message=str(last_error),
            )

    stale_symbols = [symbol for symbol in ordered_symbols if symbol in stale_cached_frames and symbol not in result.frames]
    for start in range(0, len(stale_symbols), max(1, batch_size)):
        batch = stale_symbols[start:start + max(1, batch_size)]
        batch_frames: dict[str, pd.DataFrame] = {}
        batch_error: Exception | None = None
        refresh_starts = [_refresh_start_date(_cache_last_date(stale_cached_payloads[symbol], stale_cached_frames[symbol]), period=period, as_of=as_of) for symbol in batch]
        effective_start = min([value for value in refresh_starts if value is not None], default=None)
        effective_end = _refresh_end_date(as_of)

        for attempt in range(1, retries + 2):
            try:
                batch_frames = _extract_frames_by_symbol(
                    download(batch, start=effective_start, end=effective_end, interval=interval, timeout=timeout),
                    batch,
                )
                batch_error = None
                break
            except Exception as exc:
                batch_error = exc
                if attempt > retries:
                    break

        if batch_error is not None:
            if _is_timeout_error(batch_error):
                _append_warning(result.warnings, f'OHLCV incremental batch timeout for {", ".join(batch)}; falling back to symbol refresh.')
            elif _is_rate_limit_error(batch_error):
                _append_warning(result.warnings, f'OHLCV incremental rate-limit degradation for {", ".join(batch)}; falling back to symbol refresh.')
            else:
                _append_warning(result.warnings, f'OHLCV incremental batch fetch failed for {", ".join(batch)}; falling back to symbol refresh.')

        for symbol, update_frame in batch_frames.items():
            merged = _merge_frames(stale_cached_frames[symbol], update_frame)
            result.frames[symbol] = merged
            result.statuses[symbol] = SymbolLoadStatus(symbol=symbol, status='ok', source='cache+live', rows=len(merged), attempts=1)
            write_json_cache(
                cache_path(target_cache_dir, _ohlcv_namespace(window_key), _cache_key_for_symbol(symbol)),
                _serialize_frame(merged),
            )

        missing_symbols = [symbol for symbol in batch if symbol not in batch_frames]
        for symbol in missing_symbols if batch_frames else batch:
            if symbol in result.frames:
                continue
            last_error: Exception | None = None
            refresh_start = _refresh_start_date(
                _cache_last_date(stale_cached_payloads[symbol], stale_cached_frames[symbol]),
                period=period,
                as_of=as_of,
            )
            refresh_end = _refresh_end_date(as_of)
            for attempt in range(1, retries + 2):
                try:
                    update_frame = normalize_daily_ohlcv_frame(
                        load_history(symbol, start=refresh_start, end=refresh_end, interval=interval, timeout=timeout),
                    )
                    merged = _merge_frames(stale_cached_frames[symbol], update_frame)
                    result.frames[symbol] = merged
                    result.statuses[symbol] = SymbolLoadStatus(symbol=symbol, status='ok', source='cache+live', rows=len(merged), attempts=attempt)
                    write_json_cache(
                        cache_path(target_cache_dir, _ohlcv_namespace(window_key), _cache_key_for_symbol(symbol)),
                        _serialize_frame(merged),
                    )
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt > retries:
                        break
            if last_error is None:
                continue
            cached = stale_cached_frames[symbol]
            result.frames[symbol] = cached
            result.statuses[symbol] = SymbolLoadStatus(
                symbol=symbol,
                status='ok',
                source='cache-fallback',
                rows=len(cached),
                attempts=retries + 1,
                message=str(last_error),
            )
            if _is_timeout_error(last_error):
                _append_warning(result.warnings, f'OHLCV incremental timeout for {symbol}; using cached history.')
            elif _is_rate_limit_error(last_error):
                _append_warning(result.warnings, f'OHLCV incremental rate-limit degradation for {symbol}; using cached history.')
            else:
                _append_warning(result.warnings, f'OHLCV incremental refresh failed for {symbol}; using cached history.')

    result.metadata = {
        'run_metadata': {
            'window_key': window_key,
            'cache_dir': str(target_cache_dir),
            'batch_size': max(1, batch_size),
            'timeout': timeout,
            'retries': retries,
            'refresh': refresh,
            'warnings': list(result.warnings),
        }
    }
    return result
