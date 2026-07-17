from __future__ import annotations

import pandas as pd
import pytest

from scripts.oneil_scanner import filters as scanner_filters
from scripts.oneil_scanner.filters import evaluate_eligibility, evaluate_trend_filters
from scripts.oneil_scanner.preprocess import add_shared_preprocessing
from scripts.vcp_lib.models import TrendTemplateResult



def _price_frame(*, periods: int = 260, close_start: float = 100.0, step: float = 1.0, volume: int = 1_000_000) -> pd.DataFrame:
    closes = pd.Series([close_start + step * index for index in range(periods)], dtype='float64')
    return pd.DataFrame(
        {
            'Date': pd.date_range('2025-01-01', periods=periods, freq='D'),
            'Open': closes * 0.99,
            'High': closes * 1.02,
            'Low': closes * 0.98,
            'Close': closes,
            'Volume': [volume] * periods,
        }
    )



def test_shared_preprocessing_adds_moving_averages_and_52_week_metrics() -> None:
    frame = _price_frame()

    enriched = add_shared_preprocessing(frame)
    latest = enriched.iloc[-1]

    assert latest['SMA10'] == pytest.approx(frame['Close'].tail(10).mean())
    assert latest['SMA20'] == pytest.approx(frame['Close'].tail(20).mean())
    assert latest['SMA50'] == pytest.approx(frame['Close'].tail(50).mean())
    assert latest['SMA150'] == pytest.approx(frame['Close'].tail(150).mean())
    assert latest['SMA200'] == pytest.approx(frame['Close'].tail(200).mean())
    assert latest['High52Week'] == pytest.approx(frame['High'].tail(252).max())
    assert latest['Low52Week'] == pytest.approx(frame['Low'].tail(252).min())
    assert latest['ClosePctFrom52WHigh'] == pytest.approx(frame['Close'].iloc[-1] / frame['High'].tail(252).max() - 1.0)



def test_shared_preprocessing_adds_range_liquidity_gap_and_breakout_metrics() -> None:
    frame = _price_frame(step=0.5, volume=2_000_000)

    enriched = add_shared_preprocessing(frame)
    latest = enriched.iloc[-1]

    expected_true_range = max(
        frame['High'].iloc[-1] - frame['Low'].iloc[-1],
        abs(frame['High'].iloc[-1] - frame['Close'].iloc[-2]),
        abs(frame['Low'].iloc[-1] - frame['Close'].iloc[-2]),
    )
    assert latest['TrueRange'] == pytest.approx(expected_true_range)
    assert latest['ATR20'] == pytest.approx(enriched['TrueRange'].tail(20).mean())
    assert latest['AvgVolume20'] == pytest.approx(frame['Volume'].tail(20).mean())
    assert latest['AvgDollarVolume20'] == pytest.approx((frame['Close'] * frame['Volume']).tail(20).mean())
    assert latest['GapPct'] == pytest.approx(frame['Open'].iloc[-1] / frame['Close'].iloc[-2] - 1.0)
    assert latest['BreakoutVolumeRatio'] == pytest.approx(frame['Volume'].iloc[-1] / frame['Volume'].tail(20).mean())



def test_shared_preprocessing_adds_rs_proxy_using_benchmark_relative_performance() -> None:
    frame = _price_frame(close_start=100.0, step=1.0)
    benchmark = _price_frame(close_start=100.0, step=0.4)

    enriched = add_shared_preprocessing(frame, benchmark=benchmark)
    latest = enriched.iloc[-1]

    stock_return = frame['Close'].iloc[-1] / frame['Close'].iloc[-64] - 1.0
    benchmark_return = benchmark['Close'].iloc[-1] / benchmark['Close'].iloc[-64] - 1.0
    expected_rs_proxy = stock_return - benchmark_return

    assert latest['RSProxy'] == pytest.approx(expected_rs_proxy)
    assert latest['RSProxy'] > 0



def test_trend_filters_report_pass_details_and_distance_to_high() -> None:
    frame = _price_frame()
    benchmark = _price_frame(close_start=100.0, step=0.25)

    enriched = add_shared_preprocessing(frame, benchmark=benchmark)
    result = evaluate_trend_filters(enriched, min_rs_proxy=0.05)

    assert result.passes is True
    assert result.trend_template_pass is True
    assert result.rs_pass is True
    assert result.reasons == []
    assert result.distance_to_52w_high == pytest.approx(abs(enriched.iloc[-1]['ClosePctFrom52WHigh']))
    assert result.rs_score == pytest.approx(enriched.iloc[-1]['RSProxy'])



def test_trend_filters_report_fail_reasons() -> None:
    frame = _price_frame(close_start=300.0, step=-0.6, volume=250_000)
    benchmark = _price_frame(close_start=100.0, step=0.1, volume=1_000_000)

    enriched = add_shared_preprocessing(frame, benchmark=benchmark)
    result = evaluate_trend_filters(enriched, min_rs_proxy=0.05)

    assert result.passes is False
    assert result.trend_template_pass is False
    assert result.rs_pass is False
    assert 'trend_template' in result.reasons
    assert 'rs_proxy_below_threshold' in result.reasons
    assert 'price_above_sma150' in result.failed_checks
    assert 'close_to_52w_high' in result.failed_checks



def test_trend_filters_use_vcp_trend_template_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = add_shared_preprocessing(_price_frame())
    called: dict[str, object] = {}

    def fake_evaluate_trend_template(candidate_frame: pd.DataFrame) -> TrendTemplateResult:
        called['frame'] = candidate_frame
        return TrendTemplateResult(
            passes=False,
            checks={'price_above_sma150': False, 'close_to_52w_high': True},
            reasons=['price_above_sma150'],
        )

    monkeypatch.setattr(scanner_filters.vcp_trend_template, 'evaluate_trend_template', fake_evaluate_trend_template)
    result = scanner_filters.evaluate_trend_filters(frame, min_rs_proxy=-1.0)

    assert called['frame'] is frame
    assert result.trend_template is not None
    assert result.trend_template.reasons == ['price_above_sma150']
    assert result.reasons == ['trend_template']
    assert result.failed_checks == ['price_above_sma150']



def test_trend_filters_match_reused_vcp_trend_template_behavior() -> None:
    frame = add_shared_preprocessing(
        _price_frame(close_start=120.0, step=0.8),
        benchmark=_price_frame(close_start=100.0, step=0.25),
    )

    direct = scanner_filters.vcp_trend_template.evaluate_trend_template(frame)
    adapted = evaluate_trend_filters(frame, min_rs_proxy=0.05)

    assert adapted.trend_template is not None
    assert adapted.trend_template.passes is direct.passes
    assert adapted.trend_template.checks == direct.checks
    assert adapted.trend_template.reasons == direct.reasons
    assert adapted.trend_template_pass is direct.passes



def test_eligibility_filters_report_explicit_fail_reasons() -> None:
    frame = _price_frame(periods=150, close_start=8.0, step=0.01, volume=50_000)
    enriched = add_shared_preprocessing(frame)

    result = evaluate_eligibility(enriched, min_history=200, min_price=10.0, min_avg_dollar_volume=10_000_000.0)

    assert result.passes is False
    assert 'insufficient_history' in result.reasons
    assert 'price_below_threshold' in result.reasons
    assert 'avg_dollar_volume_below_threshold' in result.reasons



def test_eligibility_filters_check_detector_family_specific_bars() -> None:
    frame = add_shared_preprocessing(_price_frame(periods=90, close_start=20.0, step=0.2, volume=1_500_000))

    result = evaluate_eligibility(
        frame,
        detector_family='momentum_continuation_family',
        min_price=10.0,
        min_avg_dollar_volume=10_000_000.0,
    )

    assert result.passes is False
    assert result.metrics['required_bars'] == 120
    assert result.metrics['effective_min_history'] == 120
    assert 'insufficient_bars_for_momentum_continuation_family' in result.reasons
    assert 'insufficient_history' not in result.reasons


def test_eligibility_filters_respect_explicit_min_history_with_detector_family() -> None:
    frame = add_shared_preprocessing(_price_frame(periods=150, close_start=20.0, step=0.2, volume=1_500_000))

    result = evaluate_eligibility(
        frame,
        detector_family='momentum_continuation_family',
        min_history=180,
        min_price=10.0,
        min_avg_dollar_volume=10_000_000.0,
    )

    assert result.passes is False
    assert result.metrics['required_bars'] == 120
    assert result.metrics['effective_min_history'] == 180
    assert 'insufficient_history' in result.reasons
    assert 'insufficient_bars_for_momentum_continuation_family' not in result.reasons



def test_eligibility_filters_exclude_identifiable_non_target_instruments() -> None:
    frame = add_shared_preprocessing(_price_frame(close_start=25.0, step=0.05, volume=2_000_000))
    frame['QuoteType'] = 'ETF'
    frame['CompanyName'] = 'Sample ETF Trust'

    result = evaluate_eligibility(frame, min_history=200, min_price=10.0, min_avg_dollar_volume=10_000_000.0)

    assert result.passes is False
    assert 'non_target_instrument:etf' in result.reasons


@pytest.mark.parametrize('flag_value', ['False', '0', 'N', 'no', '', 0])
def test_eligibility_filters_ignore_false_like_non_target_flags(flag_value: object) -> None:
    frame = add_shared_preprocessing(_price_frame(close_start=25.0, step=0.05, volume=2_000_000))
    frame['IsETF'] = flag_value
    frame['IsFund'] = flag_value
    frame['IsADR'] = flag_value
    frame['CompanyName'] = 'Sample Operating Company'
    frame['QuoteType'] = 'EQUITY'

    result = evaluate_eligibility(frame, min_price=10.0, min_avg_dollar_volume=10_000_000.0)

    assert all(not reason.startswith('non_target_instrument:') for reason in result.reasons)
