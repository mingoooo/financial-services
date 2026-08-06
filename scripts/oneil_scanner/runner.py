from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

from .config import ScannerConfig
from .data import fetch_event_payload, load_daily_ohlcv
from .detectors import DETECTOR_REGISTRY
from .filters import evaluate_eligibility, evaluate_trend_filters
from .minervini import allowed_detector_families, evaluate_minervini_trend_filters, is_minervini_profile
from .models import GroupedCandidateSummary, PatternCandidate, ScanRunSummary, SymbolContext
from .preprocess import add_shared_preprocessing
from .qullamaggie import (
    allowed_detector_families_for_qullamaggie,
    evaluate_qullamaggie_leader_prefilter,
    is_qullamaggie_profile,
)
from .report import build_grouped_candidate_summaries, write_report_bundle
from .scoring import score_and_rank_candidates
from .universe import resolve_universe_symbols

SymbolEventFetcher = Callable[[str], object | None]
UniverseResolverFn = Callable[[ScannerConfig], list[str]]


@dataclass
class RunnerDependencies:
    download_fn: Callable[..., pd.DataFrame | None] | None = None
    history_loader: Callable[..., pd.DataFrame | None] | None = None
    earnings_fetcher: SymbolEventFetcher | None = None
    news_fetcher: SymbolEventFetcher | None = None
    universe_resolver: UniverseResolverFn | None = None


def _resolve_symbols(config: ScannerConfig, *, universe_resolver: UniverseResolverFn | None = None) -> list[str]:
    symbols = [symbol.strip().upper() for symbol in config.symbols if symbol and symbol.strip()]
    if not symbols and config.universe:
        resolver = universe_resolver or (lambda current_config: resolve_universe_symbols(current_config.universe, cache_dir=current_config.cache_dir, refresh=current_config.refresh_cache))
        symbols = [symbol.strip().upper() for symbol in resolver(config) if symbol and str(symbol).strip()]
    if config.limit > 0:
        return symbols[: config.limit]
    return symbols


def _latest_value(frame: pd.DataFrame, column: str) -> Any:
    if frame.empty or column not in frame.columns:
        return None
    return frame.iloc[-1].get(column)


def _build_symbol_context(symbol: str, frame: pd.DataFrame) -> SymbolContext:
    source_tags = ['ohlcv']
    if 'CompanyName' in frame.columns:
        source_tags.append('metadata')
    return SymbolContext(
        symbol=symbol,
        company_name=_latest_value(frame, 'CompanyName'),
        sector=_latest_value(frame, 'Sector'),
        industry=_latest_value(frame, 'Industry'),
        exchange=_latest_value(frame, 'Exchange'),
        source_tags=source_tags,
    )


def _normalize_news_items(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    items: list[dict[str, Any]] = []
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        content = raw.get('content') if isinstance(raw.get('content'), dict) else raw
        pub_date = content.get('pubDate') or content.get('providerPublishTime') or content.get('date')
        if isinstance(pub_date, (int, float)):
            published_at = datetime.fromtimestamp(float(pub_date), UTC).date().isoformat()
        else:
            published_at = str(pub_date)[:10] if pub_date else None
        items.append(
            {
                'date': published_at,
                'headline': content.get('title') or content.get('headline') or raw.get('title') or '',
                'source': content.get('provider', {}).get('displayName') if isinstance(content.get('provider'), dict) else content.get('source') or raw.get('source') or '',
            }
        )
    return items


def _default_news_fetcher(symbol: str) -> object | None:
    try:
        payload = yf.Ticker(symbol).news or []
    except Exception:
        return []
    return {'items': _normalize_news_items(payload)}


def _default_earnings_fetcher(symbol: str) -> object | None:
    try:
        dates = yf.Ticker(symbol).get_earnings_dates(limit=4)
    except Exception:
        return []
    if dates is None or getattr(dates, 'empty', True):
        return []
    events: list[dict[str, Any]] = []
    for index, row in dates.head(4).iterrows():
        event_date = pd.Timestamp(index).date().isoformat()
        events.append(
            {
                'date': event_date,
                'reported': True,
                'confirmed': True,
                'headline': 'Scheduled earnings event',
                'eps_surprise_pct': row.get('Surprise(%)') if hasattr(row, 'get') else None,
            }
        )
    return {'events': events}


def _fetch_symbol_events(
    symbol: str,
    *,
    config: ScannerConfig,
    dependencies: RunnerDependencies,
    window_key: str,
    warnings: list[str],
) -> tuple[object | None, object | None]:
    earnings_payload: object | None = None
    news_payload: object | None = None

    if config.include_earnings:
        fetcher = dependencies.earnings_fetcher or _default_earnings_fetcher
        earnings_payload, _ = fetch_event_payload(
            f'earnings:{symbol}',
            fetcher=lambda: fetcher(symbol),
            cache_dir=config.cache_dir,
            window_key=window_key,
            retries=config.retries,
            warnings=warnings,
            refresh=config.refresh_cache,
        )

    if config.include_news:
        fetcher = dependencies.news_fetcher or _default_news_fetcher
        news_payload, _ = fetch_event_payload(
            f'news:{symbol}',
            fetcher=lambda: fetcher(symbol),
            cache_dir=config.cache_dir,
            window_key=window_key,
            retries=config.retries,
            warnings=warnings,
            refresh=config.refresh_cache,
        )

    return earnings_payload, news_payload


def _run_family_detectors(
    symbol: str,
    frame: pd.DataFrame,
    *,
    symbol_context: SymbolContext,
    trend_template_pass: bool,
    earnings_payload: object | None,
    news_payload: object | None,
    config: ScannerConfig,
) -> list[PatternCandidate]:
    candidates: list[PatternCandidate] = []
    qullamaggie_families = allowed_detector_families_for_qullamaggie('qullamaggie') or set()
    allowed_families = allowed_detector_families(config.strategy_profile)
    if allowed_families is None:
        allowed_families = allowed_detector_families_for_qullamaggie(config.strategy_profile)
    if allowed_families is None:
        allowed_families = set(DETECTOR_REGISTRY) - qullamaggie_families
    for family_name, detector in DETECTOR_REGISTRY.items():
        if allowed_families is not None and family_name not in allowed_families:
            continue
        eligibility = evaluate_eligibility(
            frame,
            detector_family=family_name,
            min_price=config.min_price,
            min_avg_dollar_volume=config.min_avg_dollar_volume,
        )
        if not eligibility.passes:
            continue

        kwargs: dict[str, Any] = {
            'symbol': symbol,
            'trend_template_pass': trend_template_pass,
            'symbol_context': symbol_context,
        }
        if family_name in {'event_driven_family', 'qullamaggie_ep_family'}:
            kwargs['earnings_payload'] = earnings_payload
            kwargs['news_payload'] = news_payload
        candidates.extend(detector(frame, **kwargs))
    return candidates


def _passes_leader_prefilter(frame: pd.DataFrame, *, config: ScannerConfig) -> bool:
    if not is_qullamaggie_profile(config.strategy_profile):
        return True
    result = evaluate_qullamaggie_leader_prefilter(
        strength_1m=_latest_value(frame, 'strength_1m'),
        strength_3m=_latest_value(frame, 'strength_3m'),
        strength_6m=_latest_value(frame, 'strength_6m'),
        strategy_profile=config.strategy_profile,
    )
    return result.passes


def _build_summary(
    *,
    config: ScannerConfig,
    scanned_symbols: list[str],
    candidates: list[PatternCandidate],
    warnings: list[str],
) -> ScanRunSummary:
    summary = ScanRunSummary.empty(
        run_timestamp=datetime.now(UTC).isoformat(timespec='seconds'),
        universe=config.universe,
        symbols=scanned_symbols,
        limit=config.limit,
        as_of=config.as_of,
        include_news=config.include_news,
        include_earnings=config.include_earnings,
        strategy_profile=config.strategy_profile,
        report_name=config.report_name,
        out_dir=config.out_dir,
        warnings=warnings,
    )
    summary.candidates = candidates[: config.limit] if config.limit > 0 else candidates
    summary.grouped_candidate_summaries = build_grouped_candidate_summaries(summary.candidates)
    return summary


def run_scan(
    config: ScannerConfig,
    *,
    dependencies: RunnerDependencies | None = None,
    write_reports: bool = True,
) -> ScanRunSummary:
    deps = dependencies or RunnerDependencies()
    scanned_symbols = _resolve_symbols(config, universe_resolver=deps.universe_resolver)
    data_result = load_daily_ohlcv(
        scanned_symbols,
        cache_dir=config.cache_dir,
        as_of=config.as_of,
        period=config.period,
        interval=config.interval,
        batch_size=config.batch_size,
        timeout=config.timeout,
        retries=config.retries,
        refresh=config.refresh_cache,
        download_fn=deps.download_fn,
        history_loader=deps.history_loader,
    )

    warnings = list(data_result.warnings)
    window_key = data_result.metadata.get('run_metadata', {}).get('window_key', f'{config.as_of or "latest"}_{config.period}_{config.interval}')
    candidates: list[PatternCandidate] = []

    for symbol in scanned_symbols:
        raw_frame = data_result.frames.get(symbol)
        if raw_frame is None or raw_frame.empty:
            continue

        enriched = add_shared_preprocessing(raw_frame)
        if is_minervini_profile(config.strategy_profile):
            trend_filters = evaluate_minervini_trend_filters(enriched, strategy_profile=config.strategy_profile)
        else:
            trend_filters = evaluate_trend_filters(enriched, min_rs_proxy=config.min_rs_proxy)
        if not trend_filters.passes:
            continue
        if not _passes_leader_prefilter(enriched, config=config):
            continue

        symbol_context = _build_symbol_context(symbol, enriched)
        earnings_payload, news_payload = _fetch_symbol_events(
            symbol,
            config=config,
            dependencies=deps,
            window_key=window_key,
            warnings=warnings,
        )
        candidates.extend(
            _run_family_detectors(
                symbol,
                enriched,
                symbol_context=symbol_context,
                trend_template_pass=trend_filters.trend_template_pass,
                earnings_payload=earnings_payload,
                news_payload=news_payload,
                config=config,
            )
        )

    ranked = score_and_rank_candidates(
        candidates,
        as_of=config.as_of,
        trigger_window_days=config.trigger_window_days,
        strategy_profile=config.strategy_profile,
    )
    summary = _build_summary(config=config, scanned_symbols=scanned_symbols, candidates=ranked, warnings=warnings)
    if write_reports:
        write_report_bundle(config, summary)
    return summary


__all__ = ['RunnerDependencies', 'run_scan']
