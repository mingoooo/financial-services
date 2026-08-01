from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable, Mapping

import pandas as pd

from .detectors import DETECTOR_REGISTRY, DetectorFn
from .filters import evaluate_eligibility, evaluate_trend_filters
from .models import PatternCandidate, SymbolContext
from .preprocess import add_shared_preprocessing

SUPPORTED_V1_FAMILIES = frozenset({'ibd_base_family', 'vcp_breakout_family'})
SUPPORTED_V1_PATTERN_TYPES = {
    'ibd_base_family': frozenset({'cup-with-handle', 'double-bottom', 'flat-base'}),
    'vcp_breakout_family': frozenset({'vcp', '52-week-high-breakout', 'platform-breakout'}),
}

_RANKING_WEIGHTS = {
    'setup_score': 0.50,
    'quality_score': 0.30,
    'normalized_rs_score': 0.20,
}


@dataclass(frozen=True)
class ScannerBacktestSignal:
    symbol: str
    trigger_date: str | None
    entry_date: str | None
    entry_price_ref: float | None
    breakout_level: float | None
    stop_reference: float | None
    primary_pattern_family: str
    primary_pattern_type: str
    primary_pattern_variant: str
    secondary_patterns: tuple[str, ...]
    ranking_score: float | None
    quality_score: float | None
    setup_score: float | None
    rs_score: float | None
    normalized_rs_score: float | None


@dataclass(frozen=True)
class DaySignalCache:
    date: str
    signals: tuple[ScannerBacktestSignal, ...]
    warnings: tuple[str, ...] = ()


def candidate_to_signal(candidate: PatternCandidate) -> ScannerBacktestSignal:
    _validate_supported_candidate(candidate)

    normalized_rs_score = _normalize_rs_score(candidate.rs_score)
    ranking_score = _compute_ranking_score(
        setup_score=candidate.setup_score,
        quality_score=candidate.quality_score,
        normalized_rs_score=normalized_rs_score,
    )

    return ScannerBacktestSignal(
        symbol=candidate.symbol,
        trigger_date=candidate.trigger_date,
        entry_date=_next_trading_day_placeholder(candidate.trigger_date),
        entry_price_ref=candidate.breakout_level,
        breakout_level=candidate.breakout_level,
        stop_reference=candidate.stop_reference,
        primary_pattern_family=candidate.pattern_family,
        primary_pattern_type=candidate.pattern_type,
        primary_pattern_variant=candidate.pattern_variant,
        secondary_patterns=(),
        ranking_score=ranking_score,
        quality_score=_clamp_score(candidate.quality_score),
        setup_score=_clamp_score(candidate.setup_score),
        rs_score=candidate.rs_score,
        normalized_rs_score=normalized_rs_score,
    )


def collapse_candidates_for_day(candidates: list[PatternCandidate]) -> ScannerBacktestSignal:
    if not candidates:
        raise ValueError('collapse_candidates_for_day requires at least one candidate')

    symbols = {candidate.symbol for candidate in candidates}
    if len(symbols) != 1:
        raise ValueError('collapse_candidates_for_day requires candidates for exactly one symbol')

    trigger_dates = {candidate.trigger_date for candidate in candidates}
    if len(trigger_dates) != 1:
        raise ValueError('collapse_candidates_for_day requires candidates for exactly one trigger_date')

    ordered = sorted((candidate_to_signal(candidate) for candidate in candidates), key=_signal_order_key)
    primary = ordered[0]

    secondary_patterns: list[str] = []
    for overlap in ordered[1:]:
        label = _secondary_pattern_label(overlap)
        if label not in secondary_patterns:
            secondary_patterns.append(label)

    return ScannerBacktestSignal(
        symbol=primary.symbol,
        trigger_date=primary.trigger_date,
        entry_date=primary.entry_date,
        entry_price_ref=primary.entry_price_ref,
        breakout_level=primary.breakout_level,
        stop_reference=primary.stop_reference,
        primary_pattern_family=primary.primary_pattern_family,
        primary_pattern_type=primary.primary_pattern_type,
        primary_pattern_variant=primary.primary_pattern_variant,
        secondary_patterns=tuple(secondary_patterns),
        ranking_score=primary.ranking_score,
        quality_score=primary.quality_score,
        setup_score=primary.setup_score,
        rs_score=primary.rs_score,
        normalized_rs_score=primary.normalized_rs_score,
    )


def day_cache_path(cache_dir: str | Path, day: str | date | datetime) -> Path:
    normalized_day = _normalize_day(day)
    return Path(cache_dir) / f'{normalized_day}.json'


def load_cached_day_signals(cache_dir: str | Path, day: str | date | datetime) -> DaySignalCache:
    cache_path = day_cache_path(cache_dir, day)
    payload = json.loads(cache_path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'invalid scanner cache payload in {cache_path}')
    signals_payload = payload.get('signals')
    warnings_payload = payload.get('warnings', [])
    if not isinstance(signals_payload, list) or not isinstance(warnings_payload, list):
        raise ValueError(f'invalid scanner cache content in {cache_path}')
    return DaySignalCache(
        date=str(payload.get('date') or _normalize_day(day)),
        signals=tuple(_signal_from_dict(item) for item in signals_payload),
        warnings=tuple(str(item) for item in warnings_payload),
    )


def write_cached_day_signals(
    cache_dir: str | Path,
    day: str | date | datetime,
    signals: Iterable[ScannerBacktestSignal],
    *,
    warnings: Iterable[str] | None = None,
) -> Path:
    cache_path = day_cache_path(cache_dir, day)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'date': _normalize_day(day),
        'signals': [_signal_to_dict(signal) for signal in signals],
        'warnings': list(warnings or []),
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return cache_path


def load_or_build_day_signals(
    *,
    cache_dir: str | Path,
    day: str | date | datetime,
    frames_by_symbol: Mapping[str, pd.DataFrame],
    refresh: bool = False,
    detector_registry: Mapping[str, DetectorFn] | None = None,
    detector_families: Iterable[str] | None = None,
    pattern_types: Iterable[str] | None = None,
    preprocess_frame: Callable[..., pd.DataFrame] = add_shared_preprocessing,
    trend_filter_fn: Callable[..., object] = evaluate_trend_filters,
    min_price: float = 10.0,
    min_avg_dollar_volume: float = 10_000_000.0,
    benchmark_frame: pd.DataFrame | None = None,
) -> DaySignalCache:
    normalized_day = _normalize_day(day)
    if not refresh:
        try:
            return load_cached_day_signals(cache_dir, normalized_day)
        except FileNotFoundError:
            pass
        except Exception as exc:
            warnings = [f'Corrupt scanner cache for {normalized_day}; rebuilding. ({exc})']
            rebuilt = _build_day_signals(
                day=normalized_day,
                frames_by_symbol=frames_by_symbol,
                detector_registry=detector_registry,
                detector_families=detector_families,
                pattern_types=pattern_types,
                preprocess_frame=preprocess_frame,
                trend_filter_fn=trend_filter_fn,
                min_price=min_price,
                min_avg_dollar_volume=min_avg_dollar_volume,
                benchmark_frame=benchmark_frame,
                seed_warnings=warnings,
            )
            write_cached_day_signals(cache_dir, normalized_day, rebuilt.signals, warnings=rebuilt.warnings)
            return rebuilt

    built = _build_day_signals(
        day=normalized_day,
        frames_by_symbol=frames_by_symbol,
        detector_registry=detector_registry,
        detector_families=detector_families,
        pattern_types=pattern_types,
        preprocess_frame=preprocess_frame,
        trend_filter_fn=trend_filter_fn,
        min_price=min_price,
        min_avg_dollar_volume=min_avg_dollar_volume,
        benchmark_frame=benchmark_frame,
    )
    write_cached_day_signals(cache_dir, normalized_day, built.signals, warnings=built.warnings)
    return built


def _build_day_signals(
    *,
    day: str,
    frames_by_symbol: Mapping[str, pd.DataFrame],
    detector_registry: Mapping[str, DetectorFn] | None,
    detector_families: Iterable[str] | None,
    pattern_types: Iterable[str] | None,
    preprocess_frame: Callable[..., pd.DataFrame],
    trend_filter_fn: Callable[..., object],
    min_price: float,
    min_avg_dollar_volume: float,
    benchmark_frame: pd.DataFrame | None,
    seed_warnings: Iterable[str] | None = None,
) -> DaySignalCache:
    selected_families = _resolve_detector_families(detector_registry=detector_registry, detector_families=detector_families)
    allowed_pattern_types = set(pattern_types or [])
    warnings = list(seed_warnings or [])
    candidates_by_symbol: dict[str, list[PatternCandidate]] = {}

    for symbol in sorted(frames_by_symbol):
        raw_frame = frames_by_symbol[symbol]
        if raw_frame is None or raw_frame.empty:
            continue
        try:
            day_frame = _slice_frame_through_day(raw_frame, day)
            if day_frame.empty:
                continue

            enriched = preprocess_frame(day_frame, benchmark=benchmark_frame)
            trend_filters = trend_filter_fn(enriched)
            trend_template_pass = bool(getattr(trend_filters, 'trend_template_pass', getattr(trend_filters, 'passes', False)))
            if not bool(getattr(trend_filters, 'passes', False)):
                continue

            symbol_context = _build_symbol_context(symbol, enriched)
            for family_name in selected_families:
                try:
                    eligibility = evaluate_eligibility(
                        enriched,
                        detector_family=family_name,
                        min_price=min_price,
                        min_avg_dollar_volume=min_avg_dollar_volume,
                    )
                    if not eligibility.passes:
                        continue
                    detector = selected_families[family_name]
                    for candidate in detector(
                        enriched,
                        symbol=symbol,
                        trend_template_pass=trend_template_pass,
                        symbol_context=symbol_context,
                    ):
                        if candidate.trigger_date != day:
                            continue
                        if allowed_pattern_types and candidate.pattern_type not in allowed_pattern_types:
                            continue
                        candidates_by_symbol.setdefault(symbol, []).append(candidate)
                except Exception as exc:
                    warnings.append(f'{day} {symbol} {family_name} detector failed: {exc}')
        except Exception as exc:
            warnings.append(f'{day} {symbol} scan failed: {exc}')

    signals = [collapse_candidates_for_day(symbol_candidates) for _, symbol_candidates in sorted(candidates_by_symbol.items())]
    ordered_signals = tuple(sorted(signals, key=_signal_order_key))
    return DaySignalCache(date=day, signals=ordered_signals, warnings=tuple(warnings))


def _resolve_detector_families(
    *,
    detector_registry: Mapping[str, DetectorFn] | None,
    detector_families: Iterable[str] | None,
) -> dict[str, DetectorFn]:
    registry = dict(detector_registry or DETECTOR_REGISTRY)
    families = list(detector_families or SUPPORTED_V1_FAMILIES)
    resolved: dict[str, DetectorFn] = {}
    for family_name in families:
        if family_name not in SUPPORTED_V1_FAMILIES:
            continue
        detector = registry.get(family_name)
        if detector is not None:
            resolved[family_name] = detector
    return resolved


def _signal_to_dict(signal: ScannerBacktestSignal) -> dict[str, object]:
    payload = asdict(signal)
    payload['secondary_patterns'] = list(signal.secondary_patterns)
    return payload


def _signal_from_dict(payload: dict[str, object]) -> ScannerBacktestSignal:
    return ScannerBacktestSignal(
        symbol=str(payload['symbol']),
        trigger_date=_optional_str(payload.get('trigger_date')),
        entry_date=_optional_str(payload.get('entry_date')),
        entry_price_ref=_optional_float(payload.get('entry_price_ref')),
        breakout_level=_optional_float(payload.get('breakout_level')),
        stop_reference=_optional_float(payload.get('stop_reference')),
        primary_pattern_family=str(payload['primary_pattern_family']),
        primary_pattern_type=str(payload['primary_pattern_type']),
        primary_pattern_variant=_optional_str(payload.get('primary_pattern_variant')) or '',
        secondary_patterns=tuple(str(item) for item in (payload.get('secondary_patterns') or [])),
        ranking_score=_optional_float(payload.get('ranking_score')),
        quality_score=_optional_float(payload.get('quality_score')),
        setup_score=_optional_float(payload.get('setup_score')),
        rs_score=_optional_float(payload.get('rs_score')),
        normalized_rs_score=_optional_float(payload.get('normalized_rs_score')),
    )


def _build_symbol_context(symbol: str, frame: pd.DataFrame) -> SymbolContext:
    latest = frame.iloc[-1]
    return SymbolContext(
        symbol=symbol,
        company_name=_optional_str(latest.get('CompanyName')),
        sector=_optional_str(latest.get('Sector')),
        industry=_optional_str(latest.get('Industry')),
        exchange=_optional_str(latest.get('Exchange')),
    )


def _slice_frame_through_day(frame: pd.DataFrame, day: str) -> pd.DataFrame:
    normalized = frame.copy()
    if 'Date' not in normalized.columns:
        raise ValueError('historical scanner frame requires a Date column')
    normalized['Date'] = pd.to_datetime(normalized['Date'])
    cutoff = pd.Timestamp(day)
    sliced = normalized.loc[normalized['Date'] <= cutoff].copy()
    sliced.sort_values('Date', inplace=True)
    sliced.reset_index(drop=True, inplace=True)
    return sliced


def _validate_supported_candidate(candidate: PatternCandidate) -> None:
    if candidate.pattern_family not in SUPPORTED_V1_FAMILIES:
        raise ValueError(f'unsupported scanner family for V1 adapter: {candidate.pattern_family}')

    supported_types = SUPPORTED_V1_PATTERN_TYPES[candidate.pattern_family]
    if candidate.pattern_type not in supported_types:
        raise ValueError(
            'unsupported scanner pattern_type for V1 adapter: '
            f'{candidate.pattern_family}:{candidate.pattern_type}'
        )


def _secondary_pattern_label(signal: ScannerBacktestSignal) -> str:
    label = f'{signal.primary_pattern_family}:{signal.primary_pattern_type}'
    if signal.primary_pattern_variant:
        label = f'{label}:{signal.primary_pattern_variant}'
    return label


def _compute_ranking_score(
    *,
    setup_score: float | None,
    quality_score: float | None,
    normalized_rs_score: float | None,
) -> float | None:
    components = {
        'setup_score': _clamp_score(setup_score),
        'quality_score': _clamp_score(quality_score),
        'normalized_rs_score': _clamp_score(normalized_rs_score),
    }
    available_weights = sum(weight for name, weight in _RANKING_WEIGHTS.items() if components[name] is not None)
    if available_weights == 0:
        return None

    weighted_total = sum(_RANKING_WEIGHTS[name] * value for name, value in components.items() if value is not None)
    return round(weighted_total / available_weights, 4)


def _normalize_rs_score(rs_score: float | None) -> float | None:
    return _clamp_score(rs_score)


def _clamp_score(value: float | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(100.0, float(value)))


def _next_trading_day_placeholder(trigger_date: str | None) -> str | None:
    if not trigger_date:
        return None
    try:
        parsed = date.fromisoformat(trigger_date)
    except ValueError:
        return None

    next_business_day = parsed + timedelta(days=1)
    while next_business_day.weekday() >= 5:
        next_business_day += timedelta(days=1)
    return next_business_day.isoformat()


def _signal_order_key(signal: ScannerBacktestSignal) -> tuple[float, float, float, float, str, str, str]:
    return (
        -_sort_score(signal.ranking_score),
        -_sort_score(signal.setup_score),
        -_sort_score(signal.quality_score),
        -_sort_score(signal.normalized_rs_score),
        signal.primary_pattern_family,
        signal.primary_pattern_type,
        signal.primary_pattern_variant,
    )


def _sort_score(value: float | None) -> float:
    if value is None:
        return float('-inf')
    return value


def _normalize_day(value: str | date | datetime) -> str:
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


__all__ = [
    'SUPPORTED_V1_FAMILIES',
    'SUPPORTED_V1_PATTERN_TYPES',
    'DaySignalCache',
    'ScannerBacktestSignal',
    'candidate_to_signal',
    'collapse_candidates_for_day',
    'day_cache_path',
    'load_cached_day_signals',
    'load_or_build_day_signals',
    'write_cached_day_signals',
]
