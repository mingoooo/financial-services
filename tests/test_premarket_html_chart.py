from scripts.build_premarket_report import build_report
from render_report import build_html


def test_premarket_report_renders_inline_svg_chart(monkeypatch):
    monkeypatch.setattr(
        'scripts.build_premarket_report.build_daily_chart_svg',
        lambda ticker: '<div class="chart-card"><svg class="chart-svg" viewBox="0 0 10 10"></svg></div>',
    )

    packet = {
        'candidate_source': 'unit-test',
        'market_snapshot': [],
        'econ_calendar': {},
        'warnings': [],
        'gappers': [
            {
                'ticker': 'NVDA',
                'company_name': 'NVIDIA',
                'price': 170.0,
                'gap_pct': 3.2,
                'market_cap': 4_000_000_000_000,
                'premarket_high': 171.5,
                'premarket_low': 168.8,
                'prior_day_high': 169.5,
                'prior_day_low': 164.2,
                'premarket_volume': 1_500_000,
                'day_eligible': True,
                'swing_eligible': True,
                'catalyst_found': True,
                'catalyst_headlines': [{'title': 'Strong earnings reaction'}],
            }
        ],
    }

    markdown_report = build_report(packet)
    html_report = build_html(markdown_report, '2026-08-19', 'footer', zh=False)

    assert '<svg class="chart-svg"' in html_report
    assert 'chart-card' in html_report
    assert '<img' not in html_report
