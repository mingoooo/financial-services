from __future__ import annotations

from scripts.vcp_lib.models import RawCandidate, TrendTemplateResult, VcpDetectionResult
from scripts.vcp_lib.scoring import score_candidate


def test_score_candidate_assigns_watch_or_better() -> None:
    candidate = RawCandidate(symbol='TEST', average_dollar_volume=25_000_000, last_price=50)
    trend = TrendTemplateResult(passes=True, checks={'a': True})
    vcp = VcpDetectionResult(detected=True, prior_uptrend=True, contraction_count=3, base_depth_pct=0.2, pivot_price=52.0, distance_to_pivot_pct=-0.01, final_tightness=True, volume_dry_up=True)
    scored = score_candidate(candidate, trend, vcp)
    assert scored.grade in {'A+', 'A'}
