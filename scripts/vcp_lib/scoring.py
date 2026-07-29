from __future__ import annotations

from .models import RawCandidate, ScoredCandidate, TrendTemplateResult, VcpDetectionResult


def score_candidate(
    candidate: RawCandidate,
    trend: TrendTemplateResult,
    vcp: VcpDetectionResult,
) -> ScoredCandidate:
    component_scores: dict[str, float] = {}
    component_scores['trend_template_score'] = 25.0 if trend.passes else max(0.0, 4.0 * sum(trend.checks.values()))
    component_scores['uptrend_score'] = 15.0 if vcp.prior_uptrend else 6.0
    component_scores['contraction_score'] = min(20.0, 6.0 * vcp.contraction_count)
    component_scores['volume_dry_up_score'] = 10.0 if vcp.volume_dry_up else 4.0
    if vcp.distance_to_pivot_pct is None:
        component_scores['pivot_proximity_score'] = 0.0
    else:
        distance = abs(vcp.distance_to_pivot_pct)
        component_scores['pivot_proximity_score'] = max(0.0, 12.0 - distance * 80)
    component_scores['liquidity_score'] = 10.0 if (candidate.average_dollar_volume or 0) >= 20_000_000 else 5.0

    critical_defects = {'base-too-deep', 'too-extended-from-pivot'}
    soft_defects = {
        'advance-too-small',
        'no-higher-highs',
        'no-higher-lows',
        'weak-moving-average-structure',
        'contractions-not-shrinking',
        'leg-duration-worsening',
        'volume-not-drying-up',
        'late-stage-not-tight',
        'insufficient-swings',
        'no-prior-uptrend',
    }
    penalty = 0.0
    for defect in vcp.defects:
        if defect in critical_defects:
            penalty -= 8.0
        elif defect in soft_defects:
            penalty -= 3.0
        else:
            penalty -= 4.0
    component_scores['defect_penalty'] = penalty
    overall = sum(component_scores.values())

    has_critical = any(defect in critical_defects for defect in vcp.defects)
    textbook_like = trend.passes and vcp.detected and not has_critical and vcp.contraction_count >= 2
    near_vcp = trend.passes and vcp.contraction_count >= 2 and (vcp.distance_to_pivot_pct is None or abs(vcp.distance_to_pivot_pct) <= 0.12)

    if overall >= 78 and textbook_like:
        grade = 'A+'
    elif overall >= 68 and textbook_like:
        grade = 'A'
    elif overall >= 55 and near_vcp:
        grade = 'B'
    elif overall >= 40:
        grade = 'Watch'
    else:
        grade = 'Reject'

    if textbook_like:
        setup_tier = 'Textbook VCP'
    elif near_vcp:
        setup_tier = 'Near-VCP'
    elif overall >= 40:
        setup_tier = '观察名单'
    else:
        setup_tier = 'Rejected'

    large_cap_like = candidate.symbol in {'AAPL','MSFT','NVDA','AMZN','META','GOOGL','GOOG','TSM','ABNB','C','AXP','BLK'}
    severe = {'base-too-deep', 'too-extended-from-pivot'}
    if setup_tier in {'Textbook VCP', 'Near-VCP'} and large_cap_like and not any(d in severe for d in vcp.defects):
        review_priority = '建议复核'
    elif setup_tier in {'Textbook VCP', 'Near-VCP'}:
        review_priority = '可复核'
    elif grade == 'Watch' and large_cap_like:
        review_priority = '建议复核'
    elif grade == 'Watch':
        review_priority = '仅观察'
    else:
        review_priority = '暂不优先'

    explanation = []
    if trend.passes:
        explanation.append('趋势模板大体通过')
    if vcp.detected:
        explanation.append('形态接近标准 VCP')
    elif near_vcp:
        explanation.append('接近 VCP，但仍有结构瑕疵')
    explanation.extend(vcp.defects)
    return ScoredCandidate(
        symbol=candidate.symbol,
        company_name=candidate.company_name,
        sector=candidate.sector,
        industry=candidate.industry,
        last_price=candidate.last_price,
        trend_template=trend,
        vcp=vcp,
        component_scores=component_scores,
        overall_score=round(overall, 2),
        grade=grade,
        setup_tier=setup_tier,
        review_priority=review_priority,
        explanation=explanation,
    )
