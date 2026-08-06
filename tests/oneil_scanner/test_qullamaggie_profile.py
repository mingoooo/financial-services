from __future__ import annotations

from scripts.oneil_scanner.models import PatternCandidate, ScannerConfig
from scripts.oneil_scanner.qullamaggie import (
    DEFAULT_ALLOWED_FAMILIES,
    allowed_detector_families_for_qullamaggie,
    evaluate_qullamaggie_leader_prefilter,
    is_qullamaggie_profile,
    resolve_qullamaggie_entry_trigger,
)
from scripts.scan_oneil_setups import build_config, build_parser


def _candidate(*, breakout_level: float | None = 104.5) -> PatternCandidate:
    return PatternCandidate(
        symbol='AAPL',
        pattern_family='momentum_continuation_family',
        pattern_type='inside-day',
        pattern_variant='test',
        trigger_date='2026-07-16',
        breakout_level=breakout_level,
        entry_zone_low=103.0,
        entry_zone_high=106.0,
        stop_reference=99.0,
        trend_template_pass=True,
        rs_score=95.0,
        distance_to_52w_high=0.01,
        volume_confirmation='confirmed',
        catalyst_type='technical_breakout',
        catalyst_confidence=0.0,
        quality_score=88.0,
        setup_score=86.0,
        report_rank=None,
    )


def test_qullamaggie_config_default_profile_remains_oneil() -> None:
    config = build_config(build_parser().parse_args([]))

    assert config.strategy_profile == 'oneil'



def test_qullamaggie_config_parser_accepts_profile_option() -> None:
    args = build_parser().parse_args(['--strategy-profile', 'qullamaggie'])

    assert args.strategy_profile == 'qullamaggie'



def test_qullamaggie_config_build_sets_scanner_profile() -> None:
    config = build_config(build_parser().parse_args(['--strategy-profile', 'qullamaggie']))

    assert isinstance(config, ScannerConfig)
    assert config.strategy_profile == 'qullamaggie'



def test_qullamaggie_helper_identifies_profile_name() -> None:
    assert is_qullamaggie_profile('qullamaggie') is True
    assert is_qullamaggie_profile('oneil') is False



def test_qullamaggie_helper_leader_prefilter_passes_for_strong_multi_horizon_momentum() -> None:
    result = evaluate_qullamaggie_leader_prefilter(
        strength_1m=0.35,
        strength_3m=0.60,
        strength_6m=0.90,
    )

    assert result.passes is True
    assert result.reasons == []
    assert result.metrics == {
        'strength_1m': 0.35,
        'strength_3m': 0.60,
        'strength_6m': 0.90,
    }



def test_qullamaggie_helper_leader_prefilter_fails_when_short_term_strength_breaks() -> None:
    result = evaluate_qullamaggie_leader_prefilter(
        strength_1m=0.10,
        strength_3m=0.60,
        strength_6m=0.90,
    )

    assert result.passes is False
    assert result.reasons == ['strength_1m_below_threshold']



def test_qullamaggie_helper_allowed_family_filter_is_limited_to_v1_set() -> None:
    assert allowed_detector_families_for_qullamaggie('qullamaggie') == DEFAULT_ALLOWED_FAMILIES
    assert allowed_detector_families_for_qullamaggie('oneil') is None
    assert DEFAULT_ALLOWED_FAMILIES == {'qullamaggie_breakout_family', 'qullamaggie_ep_family'}



def test_qullamaggie_helper_entry_trigger_falls_back_without_orh_metadata() -> None:
    resolved = resolve_qullamaggie_entry_trigger(
        _candidate(breakout_level=104.5),
        execution_metadata={'orh_low': 101.0},
    )

    assert resolved == {
        'entry_trigger': 'breakout_level',
        'entry_label': 'Breakout level',
        'entry_price_reference': 104.5,
        'orh_high': None,
        'orh_low': 101.0,
        'orh_window_minutes': None,
    }


def test_qullamaggie_helper_entry_trigger_prefers_orh_when_present() -> None:
    resolved = resolve_qullamaggie_entry_trigger(
        _candidate(breakout_level=104.5),
        execution_metadata={'orh_high': 105.25, 'orh_low': 101.0, 'orh_window_minutes': 30},
    )

    assert resolved == {
        'entry_trigger': 'orh_breakout',
        'entry_label': 'ORH 30m high',
        'entry_price_reference': 105.25,
        'orh_high': 105.25,
        'orh_low': 101.0,
        'orh_window_minutes': 30,
    }


def test_qullamaggie_helper_entry_trigger_uses_entry_zone_low_when_breakout_level_missing() -> None:
    resolved = resolve_qullamaggie_entry_trigger(
        _candidate(breakout_level=None),
        execution_metadata={'orh_low': 101.0},
    )

    assert resolved == {
        'entry_trigger': 'entry_zone_low',
        'entry_label': 'Entry zone low',
        'entry_price_reference': 103.0,
        'orh_high': None,
        'orh_low': 101.0,
        'orh_window_minutes': None,
    }


def test_qullamaggie_helper_ignores_nan_orh_high_and_falls_back() -> None:
    resolved = resolve_qullamaggie_entry_trigger(
        _candidate(breakout_level=104.5),
        execution_metadata={'orh_high': float('nan'), 'orh_low': 101.0, 'orh_window_minutes': 30},
    )

    assert resolved == {
        'entry_trigger': 'breakout_level',
        'entry_label': 'Breakout level',
        'entry_price_reference': 104.5,
        'orh_high': None,
        'orh_low': 101.0,
        'orh_window_minutes': 30,
    }
