from __future__ import annotations

import json
from pathlib import Path

from scripts import render_backtest_overview_html as overview


def test_render_overview_includes_pattern_summary_tables(tmp_path: Path, monkeypatch) -> None:
    result_path = tmp_path / 'scanner.json'
    output_path = tmp_path / 'overview.html'
    result_path.write_text(
        json.dumps(
            {
                'signal_source': 'scanner',
                'universe_mode': 'static',
                'start': '2025-08-01',
                'end': '2025-08-20',
                'final_equity': 110000.0,
                'total_return_pct': 10.0,
                'max_drawdown_pct': 5.0,
                'win_rate_pct': 50.0,
                'executed_trade_count': 2,
                'profit_factor': 1.5,
                'warnings': ['Missing next-day entry bar for XYZ on 2025-08-05; skipping signal.'],
                'trades': [
                    {
                        'symbol': 'AAPL',
                        'trigger_date': '2025-08-01',
                        'entry_date': '2025-08-04',
                        'entry_price': 100.0,
                        'stop_price': 95.0,
                        'exit_date': '2025-08-10',
                        'exit_price': 110.0,
                        'shares': 10,
                        'allocated_capital': 1000.0,
                        'pnl': 100.0,
                        'return_pct': 10.0,
                        'breakout_strength_pct': 2.5,
                        'volume_ratio': 1.4,
                        'exit_reason': 'eod',
                        'universe_score': 98.0,
                        'primary_pattern_family': 'ibd_base_family',
                        'primary_pattern_type': 'cup-with-handle',
                        'primary_pattern_variant': 'standard',
                        'secondary_patterns': ['vcp_breakout_family:vcp:textbook'],
                        'breakout_level': 99.0,
                        'stop_reference': 95.0,
                    },
                    {
                        'symbol': 'MSFT',
                        'trigger_date': '2025-08-03',
                        'entry_date': '2025-08-04',
                        'entry_price': 200.0,
                        'stop_price': 190.0,
                        'exit_date': '2025-08-12',
                        'exit_price': 190.0,
                        'shares': 10,
                        'allocated_capital': 2000.0,
                        'pnl': -100.0,
                        'return_pct': -5.0,
                        'breakout_strength_pct': 1.8,
                        'volume_ratio': 1.2,
                        'exit_reason': 'stop',
                        'universe_score': 92.0,
                        'primary_pattern_family': 'vcp_breakout_family',
                        'primary_pattern_type': 'vcp',
                        'primary_pattern_variant': 'textbook',
                        'secondary_patterns': ['ibd_base_family:flat-base:tight'],
                        'breakout_level': 198.0,
                        'stop_reference': 190.0,
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )

    monkeypatch.setattr(overview, 'build_symbol_block', lambda symbol, trades: {'symbol': symbol, 'dates': [], 'ohlc': [], 'volumes': [], 'markers': [], 'trades': trades, 'sma': {f'SMA{n}': [] for n in [10, 20, 50, 100, 200]}})

    assert overview.main(['--result-json', str(result_path), '--output-html', str(output_path)]) == 0
    html = output_path.read_text(encoding='utf-8')

    assert '形态汇总' in html
    assert '次级形态重叠' in html
    assert '运行告警' in html
    assert 'cup-with-handle' in html
    assert 'vcp_breakout_family:vcp:textbook' in html
    assert 'Missing next-day entry bar for XYZ on 2025-08-05; skipping signal.' in html


def test_render_overview_uses_unique_mode_keys_and_escapes_html(tmp_path: Path, monkeypatch) -> None:
    legacy_path = tmp_path / 'legacy.json'
    scanner_path = tmp_path / 'scanner.json'
    output_path = tmp_path / 'overview.html'

    payload = {
        'universe_mode': 'static',
        'start': '2025-08-01',
        'end': '2025-08-20',
        'final_equity': 100000.0,
        'total_return_pct': 0.0,
        'max_drawdown_pct': 0.0,
        'win_rate_pct': 0.0,
        'executed_trade_count': 1,
        'profit_factor': 1.0,
        'warnings': ['warn <b>bold</b>'],
        'trades': [
            {
                'symbol': '<AAPL>',
                'trigger_date': '2025-08-01',
                'entry_date': '2025-08-04',
                'entry_price': 100.0,
                'stop_price': 95.0,
                'exit_date': '2025-08-10',
                'exit_price': 101.0,
                'shares': 10,
                'allocated_capital': 1000.0,
                'pnl': 10.0,
                'return_pct': 1.0,
                'breakout_strength_pct': 2.0,
                'volume_ratio': 1.2,
                'exit_reason': 'stop <script>alert(1)</script>',
                'universe_score': 90.0,
                'primary_pattern_family': 'ibd_base_family',
                'primary_pattern_type': '<cup>',
                'primary_pattern_variant': 'standard',
                'secondary_patterns': ['vcp:<tag>'],
                'breakout_level': 99.0,
                'stop_reference': 95.0,
            }
        ],
    }
    legacy_path.write_text(json.dumps({'signal_source': 'legacy', **payload}, ensure_ascii=False), encoding='utf-8')
    scanner_path.write_text(json.dumps({'signal_source': 'scanner', **payload}, ensure_ascii=False), encoding='utf-8')

    monkeypatch.setattr(overview, 'build_symbol_block', lambda symbol, trades: {'symbol': symbol, 'dates': [], 'ohlc': [], 'volumes': [], 'markers': [], 'trades': trades, 'sma': {f'SMA{n}': [] for n in [10, 20, 50, 100, 200]}})

    assert overview.main(['--result-json', str(legacy_path), '--result-json', str(scanner_path), '--output-html', str(output_path)]) == 0
    html = output_path.read_text(encoding='utf-8')

    assert 'legacy:static' in html
    assert 'scanner:static' in html
    assert 'static (legacy)' in html
    assert 'static (scanner)' in html
    assert 'function esc(value)' in html
    assert '&lt;/script&gt;' not in html
    assert '<\\/script>' in html
