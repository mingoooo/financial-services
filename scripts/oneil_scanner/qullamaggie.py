from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

from scripts.oneil_scanner.models import PatternCandidate

QULLAMAGGIE_PROFILE = 'qullamaggie'
DEFAULT_ALLOWED_FAMILIES: set[str] = {'qullamaggie_breakout_family', 'qullamaggie_ep_family'}


@dataclass(frozen=True)
class QullamaggieProfileSettings:
    name: str
    min_strength_1m: float = 0.25
    min_strength_3m: float = 0.50
    min_strength_6m: float = 0.75


@dataclass(frozen=True)
class QullamaggieLeaderPrefilterResult:
    passes: bool
    reasons: list[str]
    metrics: dict[str, float | None]


PROFILE_SETTINGS: dict[str, QullamaggieProfileSettings] = {
    QULLAMAGGIE_PROFILE: QullamaggieProfileSettings(name=QULLAMAGGIE_PROFILE),
}

QULLAMAGGIE_PROFILE_SETTINGS = PROFILE_SETTINGS[QULLAMAGGIE_PROFILE]


def is_qullamaggie_profile(strategy_profile: str) -> bool:
    return strategy_profile in PROFILE_SETTINGS


def allowed_detector_families_for_qullamaggie(strategy_profile: str) -> set[str] | None:
    if is_qullamaggie_profile(strategy_profile):
        return set(DEFAULT_ALLOWED_FAMILIES)
    return None


def evaluate_qullamaggie_leader_prefilter(
    *,
    strength_1m: float | None,
    strength_3m: float | None,
    strength_6m: float | None,
    strategy_profile: str = QULLAMAGGIE_PROFILE,
) -> QullamaggieLeaderPrefilterResult:
    settings = PROFILE_SETTINGS[strategy_profile]
    metrics = {
        'strength_1m': strength_1m,
        'strength_3m': strength_3m,
        'strength_6m': strength_6m,
    }
    checks = {
        'strength_1m_below_threshold': strength_1m is None or strength_1m < settings.min_strength_1m,
        'strength_3m_below_threshold': strength_3m is None or strength_3m < settings.min_strength_3m,
        'strength_6m_below_threshold': strength_6m is None or strength_6m < settings.min_strength_6m,
    }
    reasons = [reason for reason, failed in checks.items() if failed]
    return QullamaggieLeaderPrefilterResult(passes=not reasons, reasons=reasons, metrics=metrics)


def resolve_qullamaggie_entry_trigger(
    candidate: PatternCandidate,
    *,
    execution_metadata: Mapping[str, object] | None = None,
) -> dict[str, float | int | str | None]:
    metadata = dict(execution_metadata or {})
    orh_high = _optional_float(metadata.get('orh_high'))
    orh_low = _optional_float(metadata.get('orh_low'))
    orh_window_minutes = _optional_int(metadata.get('orh_window_minutes'))
    if orh_high is not None:
        label = f'ORH {orh_window_minutes}m high' if orh_window_minutes is not None else 'ORH high'
        return {
            'entry_trigger': 'orh_breakout',
            'entry_label': label,
            'entry_price_reference': orh_high,
            'orh_high': orh_high,
            'orh_low': orh_low,
            'orh_window_minutes': orh_window_minutes,
        }

    fallback_reference = candidate.breakout_level
    fallback_trigger = 'breakout_level'
    fallback_label = 'Breakout level'
    if fallback_reference is None:
        fallback_reference = candidate.entry_zone_low
        fallback_trigger = 'entry_zone_low'
        fallback_label = 'Entry zone low'

    return {
        'entry_trigger': fallback_trigger,
        'entry_label': fallback_label,
        'entry_price_reference': fallback_reference,
        'orh_high': orh_high,
        'orh_low': orh_low,
        'orh_window_minutes': orh_window_minutes,
    }


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    if math.isnan(parsed):
        return None
    return parsed


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


__all__ = [
    'DEFAULT_ALLOWED_FAMILIES',
    'PROFILE_SETTINGS',
    'QULLAMAGGIE_PROFILE',
    'QULLAMAGGIE_PROFILE_SETTINGS',
    'QullamaggieLeaderPrefilterResult',
    'QullamaggieProfileSettings',
    'allowed_detector_families_for_qullamaggie',
    'evaluate_qullamaggie_leader_prefilter',
    'is_qullamaggie_profile',
    'resolve_qullamaggie_entry_trigger',
]
