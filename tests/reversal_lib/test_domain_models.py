from __future__ import annotations

from dataclasses import asdict

import pytest

from reversal_lib.domain.models import (
    BacktestResult,
    IndicatorContext,
    PatternHit,
    SignalCandidate,
    TradePlan,
)
from reversal_lib.domain.requests import UniverseRequest
from reversal_lib.models import BacktestResult as LegacyBacktestResult
from reversal_lib.models import PatternHit as LegacyPatternHit
from reversal_lib.models import UniverseRequest as LegacyUniverseRequest


def test_pattern_hit_requires_core_fields() -> None:
    hit = PatternHit(
        symbol="AAPL",
        pattern="bullish_engulfing",
        candidate_index=12,
        candidate_date="2026-06-20",
    )

    assert hit.symbol == "AAPL"
    assert hit.pattern == "bullish_engulfing"
    assert hit.candidate_index == 12
    assert hit.candidate_date == "2026-06-20"


def test_pattern_hit_missing_required_fields_raises_type_error() -> None:
    with pytest.raises(TypeError):
        PatternHit(  # type: ignore[call-arg]
            symbol="AAPL",
            pattern="bullish_engulfing",
            candidate_index=12,
        )


def test_indicator_context_supports_optional_indicator_values() -> None:
    context = IndicatorContext(
        trend_context="uptrend",
        location_context="near_support",
        sma_cross_context="fresh_bull_cross",
        rsi_value=54.2,
        above_sma200=True,
        macd_context="bullish",
    )

    assert asdict(context) == {
        "trend_context": "uptrend",
        "location_context": "near_support",
        "sma_cross_context": "fresh_bull_cross",
        "rsi_value": 54.2,
        "above_sma200": True,
        "macd_context": "bullish",
    }


def test_signal_candidate_requires_pattern_hit_and_risk_fields() -> None:
    hit = PatternHit(
        symbol="MSFT",
        pattern="hammer",
        candidate_index=5,
        candidate_date="2026-06-18",
        confirm_index=6,
        confirm_date="2026-06-19",
    )
    context = IndicatorContext(rsi_value=51.0)

    signal = SignalCandidate(
        hit=hit,
        side="long",
        confirm_close=410.5,
        planned_entry_price=411.0,
        stop_loss=402.0,
        first_target=420.0,
        second_target=428.0,
        confirm_volume=1200000,
        avg_volume_20=900000,
        avg_dollar_volume_20=370000000,
        indicator_context=context,
    )

    assert signal.hit.symbol == "MSFT"
    assert signal.indicator_context.rsi_value == 51.0
    assert signal.stop_loss == pytest.approx(402.0)


def test_signal_candidate_missing_required_fields_raises_type_error() -> None:
    hit = PatternHit(
        symbol="MSFT",
        pattern="hammer",
        candidate_index=5,
        candidate_date="2026-06-18",
    )

    with pytest.raises(TypeError):
        SignalCandidate(  # type: ignore[call-arg]
            hit=hit,
            side="long",
            confirm_close=410.5,
            planned_entry_price=411.0,
            stop_loss=402.0,
            first_target=420.0,
            second_target=428.0,
            confirm_volume=1200000,
            avg_volume_20=900000,
        )


def test_trade_plan_requires_signal_and_execution_plan_fields() -> None:
    hit = PatternHit(
        symbol="NVDA",
        pattern="morning_star",
        candidate_index=20,
        candidate_date="2026-06-17",
    )
    signal = SignalCandidate(
        hit=hit,
        side="long",
        confirm_close=150.0,
        planned_entry_price=151.0,
        stop_loss=145.0,
        first_target=160.0,
        second_target=166.0,
        confirm_volume=30000000,
        avg_volume_20=25000000,
        avg_dollar_volume_20=4500000000,
    )

    plan = TradePlan(
        signal=signal,
        entry_date="2026-06-20",
        entry_price=151.0,
        stop_loss=145.0,
        target_price=160.0,
    )

    assert plan.signal.hit.pattern == "morning_star"
    assert plan.target_price == pytest.approx(160.0)


def test_trade_plan_missing_required_fields_raises_type_error() -> None:
    hit = PatternHit(
        symbol="NVDA",
        pattern="morning_star",
        candidate_index=20,
        candidate_date="2026-06-17",
    )
    signal = SignalCandidate(
        hit=hit,
        side="long",
        confirm_close=150.0,
        planned_entry_price=151.0,
        stop_loss=145.0,
        first_target=160.0,
        second_target=166.0,
        confirm_volume=30000000,
        avg_volume_20=25000000,
        avg_dollar_volume_20=4500000000,
    )

    with pytest.raises(TypeError):
        TradePlan(  # type: ignore[call-arg]
            signal=signal,
            entry_date="2026-06-20",
            entry_price=151.0,
            stop_loss=145.0,
        )


def test_backtest_result_groups_pipeline_outputs() -> None:
    hit = PatternHit(
        symbol="TSLA",
        pattern="piercing_line",
        candidate_index=9,
        candidate_date="2026-06-15",
    )
    signal = SignalCandidate(
        hit=hit,
        side="long",
        confirm_close=200.0,
        planned_entry_price=201.0,
        stop_loss=193.0,
        first_target=210.0,
        second_target=218.0,
        confirm_volume=15000000,
        avg_volume_20=11000000,
        avg_dollar_volume_20=2200000000,
    )
    plan = TradePlan(
        signal=signal,
        entry_date="2026-06-16",
        entry_price=201.0,
        stop_loss=193.0,
        target_price=210.0,
    )

    result = BacktestResult(
        signals=[signal],
        trade_plans=[plan],
        trades=[],
        summary={"total_trades": 0},
    )

    assert result.signals == [signal]
    assert result.trade_plans == [plan]
    assert result.trades == []
    assert result.summary == {"total_trades": 0}


def test_universe_request_requires_scan_identity() -> None:
    request = UniverseRequest(universe="sp500")

    assert request.universe == "sp500"
    assert request.limit is None
    assert request.as_of_date is None


def test_universe_request_missing_universe_raises_type_error() -> None:
    with pytest.raises(TypeError):
        UniverseRequest()  # type: ignore[call-arg]


def test_legacy_models_module_reexports_staged_models() -> None:
    assert LegacyPatternHit is PatternHit
    assert LegacyBacktestResult is BacktestResult
    assert LegacyUniverseRequest is UniverseRequest
