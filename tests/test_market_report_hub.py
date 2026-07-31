from __future__ import annotations

import json
from pathlib import Path

from scripts.render_market_report_hub import main


def _write_html(path: Path, title: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'<!doctype html><html><head><title>{title}</title></head><body>{title}</body></html>', encoding='utf-8')
    return path


def _iter_pages(manifest: dict[str, object]) -> list[dict[str, object]]:
    return [
        page
        for family in manifest['families']
        for page in family['pages'].values()
    ]


def test_manifest_driven_render_creates_hub_and_preserves_expected_metadata(tmp_path: Path) -> None:
    sources_dir = tmp_path / 'sources'
    premarket_zh = _write_html(sources_dir / 'premarket_zh.html', '盘前报告')
    premarket_en = _write_html(sources_dir / 'premarket_en.html', 'Premarket Report')
    oneil = _write_html(sources_dir / 'oneil_live.html', "O'Neil Live Scanner")

    manifest_path = tmp_path / 'fixture_manifest.json'
    manifest_payload = {
        'manifest_version': 'market-report-hub/v1',
        'generated_at': '2026-07-29T10:30:00Z',
        'families': [
            {
                'slug': 'premarket',
                'titles': {'zh': '盘前报告', 'en': 'Premarket Report'},
                'pages': {
                    'zh': {'title': '盘前报告（中文）', 'source_path': str(premarket_zh.relative_to(tmp_path))},
                    'en': {'title': 'Premarket Report', 'source_path': str(premarket_en.relative_to(tmp_path))},
                },
            },
            {
                'slug': 'oneil',
                'titles': {'zh': "O'Neil 实时扫描", 'en': "O'Neil Live Scanner"},
                'pages': {
                    'default': {'title': "O'Neil Live Scanner", 'source_path': str(oneil.relative_to(tmp_path))},
                },
            },
            {
                'slug': 'oneil-backtest',
                'titles': {'zh': "O'Neil 回测总览", 'en': "O'Neil Backtest Overview"},
                'pages': {
                    'default': {'title': "O'Neil Backtest Overview", 'available': False},
                },
            },
            {
                'slug': 'reversal-archive',
                'archived': True,
                'titles': {'zh': '已归档反转报告', 'en': 'Archived Reversal'},
                'pages': {},
            },
        ],
    }
    manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False), encoding='utf-8')

    output_dir = tmp_path / 'site'
    exit_code = main(['--manifest', str(manifest_path), '--output-dir', str(output_dir)])

    assert exit_code == 0
    assert (output_dir / 'index.html').exists()
    assert (output_dir / 'index_en.html').exists()
    assert (output_dir / 'premarket' / 'index.html').exists()
    assert (output_dir / 'premarket' / 'index_en.html').exists()
    assert (output_dir / 'oneil' / 'index.html').exists()
    assert not (output_dir / 'oneil-backtest' / 'index.html').exists()

    zh_wrapper = (output_dir / 'premarket' / 'index.html').read_text(encoding='utf-8')
    en_wrapper = (output_dir / 'premarket' / 'index_en.html').read_text(encoding='utf-8')
    assert '返回首页' in zh_wrapper
    assert '../index.html' in zh_wrapper
    assert '打开原报告' in zh_wrapper
    assert '../premarket_zh.html' in zh_wrapper
    assert 'Back to hub' in en_wrapper
    assert '../index_en.html' in en_wrapper
    assert 'Open source report' in en_wrapper
    assert '../premarket_en.html' in en_wrapper or '../premarket_.html' in en_wrapper
    assert '<html lang="en">' in en_wrapper
    assert '返回首页' not in en_wrapper
    assert '打开原报告' not in en_wrapper

    rendered_manifest = json.loads((output_dir / 'site_manifest.json').read_text(encoding='utf-8'))
    assert [family['slug'] for family in rendered_manifest['families']] == ['premarket', 'oneil', 'oneil-backtest']
    assert rendered_manifest['families'][0]['pages']['zh']['href'] == 'premarket/index.html'
    assert rendered_manifest['families'][0]['pages']['en']['href'] == 'premarket/index_en.html'
    assert rendered_manifest['families'][0]['pages']['zh']['source_file'] == 'premarket_zh.html'
    assert all('source_path' not in page for page in _iter_pages(rendered_manifest))
    assert rendered_manifest['families'][2]['available'] is False

    zh_hub = (output_dir / 'index.html').read_text(encoding='utf-8')
    en_hub = (output_dir / 'index_en.html').read_text(encoding='utf-8')
    assert '盘前报告' in zh_hub
    assert 'Premarket Report' in en_hub
    assert "O&#x27;Neil 实时扫描" in zh_hub or "O'Neil 实时扫描" in zh_hub
    assert "O&#x27;Neil Live Scanner" in en_hub or "O'Neil Live Scanner" in en_hub
    assert 'premarket/index.html' in zh_hub
    assert 'premarket/index_en.html' in en_hub
    assert 'Unavailable' in en_hub
    assert 'Archived Reversal' not in en_hub


def test_explicit_sources_render_with_fallback_shape_and_optional_backtest(tmp_path: Path) -> None:
    source_root = tmp_path / 'reports'
    premarket_zh = _write_html(source_root / 'premarket_zh.html', '盘前报告')
    premarket_en = _write_html(source_root / 'premarket_.html', 'Premarket Report')
    oneil = _write_html(source_root / 'oneil-live' / 'live-full-latest.html', "O'Neil Live Scanner")

    output_dir = tmp_path / 'assembled-site'
    exit_code = main(
        [
            '--output-dir',
            str(output_dir),
            '--generated-at',
            '2026-07-29T11:00:00Z',
            '--premarket-zh-source',
            str(premarket_zh),
            '--premarket-en-source',
            str(premarket_en),
            '--oneil-source',
            str(oneil),
            '--oneil-backtest-source',
            str(source_root / 'missing-backtest.html'),
        ]
    )

    assert exit_code == 0
    assert (output_dir / 'index.html').exists()
    assert (output_dir / 'index_en.html').exists()
    assert (output_dir / 'premarket' / 'index.html').exists()
    assert (output_dir / 'premarket' / 'index_en.html').exists()
    assert (output_dir / 'oneil' / 'index.html').exists()
    assert not (output_dir / 'oneil-backtest' / 'index.html').exists()

    zh_wrapper = (output_dir / 'premarket' / 'index.html').read_text(encoding='utf-8')
    en_wrapper = (output_dir / 'premarket' / 'index_en.html').read_text(encoding='utf-8')
    oneil_wrapper = (output_dir / 'oneil' / 'index.html').read_text(encoding='utf-8')
    assert '返回首页' in zh_wrapper
    assert '../index.html' in zh_wrapper
    assert '打开原报告' in zh_wrapper
    assert '../premarket_zh.html' in zh_wrapper
    assert 'Back to hub' in en_wrapper
    assert '../index_en.html' in en_wrapper
    assert 'Open source report' in en_wrapper
    assert '../premarket_.html' in en_wrapper
    assert '<html lang="en">' in en_wrapper
    assert '返回首页' not in en_wrapper
    assert '打开原报告' not in en_wrapper
    assert '../oneil-live/live-full-latest.html' in oneil_wrapper
    assert (output_dir / 'premarket_zh.html').exists()
    assert (output_dir / 'premarket_.html').exists()
    assert (output_dir / 'oneil-live' / 'live-full-latest.html').exists()

    manifest = json.loads((output_dir / 'site_manifest.json').read_text(encoding='utf-8'))
    premarket_family = next(family for family in manifest['families'] if family['slug'] == 'premarket')
    backtest_family = next(family for family in manifest['families'] if family['slug'] == 'oneil-backtest')
    assert premarket_family['pages']['zh']['source_file'] == 'premarket_zh.html'
    assert premarket_family['pages']['en']['source_file'] == 'premarket_.html'
    assert all('source_path' not in page for page in _iter_pages(manifest))
    assert backtest_family['available'] is False
    assert backtest_family['pages']['default']['available'] is False
