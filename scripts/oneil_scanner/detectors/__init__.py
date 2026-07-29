from __future__ import annotations

from collections.abc import Callable

from scripts.oneil_scanner.models import PatternCandidate, SymbolContext

from .event_driven_family import detect_event_driven_family
from .ibd_base_family import detect_ibd_base_family
from .momentum_continuation_family import detect_momentum_continuation_family
from .vcp_breakout_family import detect_vcp_breakout_family

DetectorFn = Callable[..., list[PatternCandidate]]

DETECTOR_REGISTRY: dict[str, DetectorFn] = {
    'vcp_breakout_family': detect_vcp_breakout_family,
    'ibd_base_family': detect_ibd_base_family,
    'momentum_continuation_family': detect_momentum_continuation_family,
    'event_driven_family': detect_event_driven_family,
}

__all__ = [
    'DETECTOR_REGISTRY',
    'DetectorFn',
    'PatternCandidate',
    'SymbolContext',
    'detect_event_driven_family',
    'detect_ibd_base_family',
    'detect_momentum_continuation_family',
    'detect_vcp_breakout_family',
]
