from __future__ import annotations

import argparse
import copy
import json
import os
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any, Iterable, Sequence
from zoneinfo import ZoneInfo


DEFAULT_OUTPUT_DIR = Path('reports/site')
DEFAULT_PREMARKET_ZH_SOURCE = Path('reports/premarket_zh.html')
DEFAULT_PREMARKET_EN_SOURCE = Path('reports/premarket_.html')
DEFAULT_ONEIL_SOURCE = Path('reports/oneil-live/live-full-latest.html')
DEFAULT_MINERVINI_SOURCE = Path('reports/minervini-live/live-full-latest.html')
DEFAULT_QULLAMAGGIE_SOURCE = Path('reports/qullamaggie-live/live-full-latest.html')
DEFAULT_ONEIL_BACKTEST_SOURCE = Path('reports/oneil_backtest_overview.html')
CHINA_TZ = ZoneInfo('Asia/Shanghai')

MANIFEST_VERSION = 'market-report-hub/v1'

FAMILY_DEFAULTS: dict[str, dict[str, Any]] = {
    'premarket': {
        'order': 10,
        'titles': {
            'zh': '盘前报告',
            'en': 'Premarket Report',
        },
        'descriptions': {
            'zh': '盘前异动、观察名单与市场背景。',
            'en': 'Pre-market gaps, watchlists, and tape context.',
        },
    },
    'oneil': {
        'order': 20,
        'titles': {
            'zh': "O'Neil 实时扫描",
            'en': "O'Neil Live Scanner",
        },
        'descriptions': {
            'zh': "O'Neil 风格活跃形态扫描与候选列表。",
            'en': "Active O'Neil-style setup scan and candidate list.",
        },
    },
    'minervini': {
        'order': 25,
        'titles': {
            'zh': 'Minervini 实时扫描',
            'en': 'Minervini Live Scanner',
        },
        'descriptions': {
            'zh': 'Mark Minervini 风格强势股形态扫描与候选列表。',
            'en': 'Mark Minervini-style setup scan and candidate list.',
        },
    },
    'qullamaggie': {
        'order': 27,
        'titles': {
            'zh': 'Qullamaggie 实时扫描',
            'en': 'Qullamaggie Live Scanner',
        },
        'descriptions': {
            'zh': 'Kristian Qullamaggie 风格强势突破与 EP 扫描。',
            'en': 'Kristian Qullamaggie-style breakout and episodic pivot scan.',
        },
    },
    'oneil-backtest': {
        'order': 30,
        'titles': {
            'zh': "O'Neil 回测总览",
            'en': "O'Neil Backtest Overview",
        },
        'descriptions': {
            'zh': '统一回测流程输出的总览页面。',
            'en': 'Overview page for the unified backtest workflow.',
        },
    },
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def isoformat_z(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip().replace('Z', '+00:00')
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def format_timestamp_for_display(value: str | None, *, language: str) -> str:
    parsed = parse_timestamp(value)
    if parsed is None:
        return '时间未知' if language == 'zh' else 'n/a'
    localized = parsed.astimezone(CHINA_TZ)
    suffix = '北京时间' if language == 'zh' else 'China Time (UTC+8)'
    return f"{localized.strftime('%Y-%m-%d %H:%M')} {suffix}"


def file_timestamp(path: Path) -> str:
    return isoformat_z(datetime.fromtimestamp(path.stat().st_mtime, tz=UTC))


def compute_freshness(timestamp: str | None, generated_at: str) -> dict[str, Any]:
    published = parse_timestamp(timestamp)
    generated = parse_timestamp(generated_at) or utc_now()
    if published is None:
        return {
            'status': 'unknown',
            'seconds': None,
            'label_zh': '时间未知',
            'label_en': 'Timestamp unavailable',
        }

    seconds = max(0, int((generated - published).total_seconds()))
    if seconds < 3600:
        minutes = max(1, seconds // 60)
        zh = f'{minutes} 分钟前'
        en = f'{minutes} min ago'
    elif seconds < 86400:
        hours = max(1, seconds // 3600)
        zh = f'{hours} 小时前'
        en = f'{hours}h ago'
    else:
        days = max(1, seconds // 86400)
        zh = f'{days} 天前'
        en = f'{days}d ago'

    status = 'fresh' if seconds <= 6 * 3600 else 'recent' if seconds <= 24 * 3600 else 'stale'
    return {
        'status': status,
        'seconds': seconds,
        'label_zh': zh,
        'label_en': en,
    }


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def resolve_optional_path(value: str | None, base_dir: Path) -> Path | None:
    if not value:
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return candidate.resolve()


def relative_href(from_path: Path, to_path: Path) -> str:
    return Path(os.path.relpath(to_path, start=from_path.parent)).as_posix()


def stable_page_href(slug: str, lang: str) -> str:
    if slug == 'premarket':
        return 'premarket/index.html' if lang == 'zh' else 'premarket/index_en.html'
    return f'{slug}/index.html'


def stable_source_href(source_path: Path) -> str:
    if source_path.parent.name in {'oneil-live', 'minervini-live', 'qullamaggie-live'}:
        return f'{source_path.parent.name}/{source_path.name}'
    return source_path.name


def page_record(
    *,
    slug: str,
    lang: str,
    title: str,
    source_path: Path | None,
    output_dir: Path,
    source_href_value: str | None = None,
    published_at: str | None = None,
    available: bool | None = None,
) -> dict[str, Any]:
    href = stable_page_href(slug, lang)
    page: dict[str, Any] = {
        'lang': lang,
        'title': title,
        'href': href,
        'available': False,
    }

    resolved_source = source_path
    if available is None:
        page['available'] = bool(resolved_source and resolved_source.exists())
    else:
        page['available'] = bool(available)

    if resolved_source is not None:
        page['source_path'] = str(resolved_source)
        page['source_file'] = resolved_source.name
    if source_href_value:
        page['source_href'] = source_href_value
    elif resolved_source is not None:
        target_output = output_dir / href
        page['source_href'] = relative_href(target_output, output_dir / stable_source_href(resolved_source))

    if published_at:
        page['published_at'] = published_at
    elif resolved_source is not None and resolved_source.exists():
        page['published_at'] = file_timestamp(resolved_source)

    return page


def build_manifest_from_sources(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output_dir).resolve()
    generated_at = args.generated_at or isoformat_z(utc_now())
    cwd = Path.cwd()

    def explicit_or_default(value: str | None, fallback: Path) -> Path | None:
        raw = value if value is not None else str(fallback)
        return resolve_optional_path(raw, cwd)

    premarket_zh_source = explicit_or_default(args.premarket_zh_source, DEFAULT_PREMARKET_ZH_SOURCE)
    premarket_en_source = explicit_or_default(args.premarket_en_source, DEFAULT_PREMARKET_EN_SOURCE)
    oneil_source = explicit_or_default(args.oneil_source, DEFAULT_ONEIL_SOURCE)
    minervini_source = explicit_or_default(args.minervini_source, DEFAULT_MINERVINI_SOURCE)
    qullamaggie_source = explicit_or_default(args.qullamaggie_source, DEFAULT_QULLAMAGGIE_SOURCE)
    oneil_backtest_source = explicit_or_default(args.oneil_backtest_source, DEFAULT_ONEIL_BACKTEST_SOURCE)

    families = [
        {
            'slug': 'premarket',
            'active': True,
            'archived': False,
            **copy.deepcopy(FAMILY_DEFAULTS['premarket']),
            'pages': {
                'zh': page_record(
                    slug='premarket',
                    lang='zh',
                    title='盘前报告（中文）',
                    source_path=premarket_zh_source,
                    output_dir=output_dir,
                ),
                'en': page_record(
                    slug='premarket',
                    lang='en',
                    title='Premarket Report',
                    source_path=premarket_en_source,
                    output_dir=output_dir,
                ),
            },
        },
        {
            'slug': 'oneil',
            'active': True,
            'archived': False,
            **copy.deepcopy(FAMILY_DEFAULTS['oneil']),
            'pages': {
                'default': page_record(
                    slug='oneil',
                    lang='default',
                    title="O'Neil Live Scanner",
                    source_path=oneil_source,
                    output_dir=output_dir,
                ),
            },
        },
        {
            'slug': 'minervini',
            'active': True,
            'archived': False,
            **copy.deepcopy(FAMILY_DEFAULTS['minervini']),
            'pages': {
                'default': page_record(
                    slug='minervini',
                    lang='default',
                    title='Minervini Live Scanner',
                    source_path=minervini_source,
                    output_dir=output_dir,
                ),
            },
        },
        {
            'slug': 'qullamaggie',
            'active': True,
            'archived': False,
            **copy.deepcopy(FAMILY_DEFAULTS['qullamaggie']),
            'pages': {
                'default': page_record(
                    slug='qullamaggie',
                    lang='default',
                    title='Qullamaggie Live Scanner',
                    source_path=qullamaggie_source,
                    output_dir=output_dir,
                ),
            },
        },
        {
            'slug': 'oneil-backtest',
            'active': True,
            'archived': False,
            **copy.deepcopy(FAMILY_DEFAULTS['oneil-backtest']),
            'pages': {
                'default': page_record(
                    slug='oneil-backtest',
                    lang='default',
                    title="O'Neil Backtest Overview",
                    source_path=oneil_backtest_source,
                    output_dir=output_dir,
                ),
            },
        },
    ]

    return finalize_manifest(
        {
            'manifest_version': MANIFEST_VERSION,
            'generated_at': generated_at,
            'output_dir': str(output_dir),
            'families': families,
        },
        output_dir=output_dir,
        base_dir=cwd,
    )


def normalize_pages(
    *,
    slug: str,
    pages: dict[str, Any],
    output_dir: Path,
    base_dir: Path,
) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for lang, raw_page in pages.items():
        source_path = resolve_optional_path(raw_page.get('source_path'), base_dir)
        source_href_value = raw_page.get('source_href')
        title = raw_page.get('title') or raw_page.get('label') or stable_page_href(slug, lang)
        normalized[lang] = page_record(
            slug=slug,
            lang=lang,
            title=title,
            source_path=source_path,
            output_dir=output_dir,
            source_href_value=source_href_value,
            published_at=raw_page.get('published_at'),
            available=raw_page.get('available'),
        )
    return normalized


def portable_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    published = copy.deepcopy(manifest)
    for family in published.get('families', []):
        for page in family.get('pages', {}).values():
            page.pop('source_path', None)
    return published


def finalize_manifest(raw_manifest: dict[str, Any], *, output_dir: Path, base_dir: Path) -> dict[str, Any]:
    generated_at = raw_manifest.get('generated_at') or isoformat_z(utc_now())
    normalized_families: list[dict[str, Any]] = []
    for raw_family in raw_manifest.get('families', []):
        slug = raw_family['slug']
        if raw_family.get('archived') or raw_family.get('active') is False:
            continue
        defaults = copy.deepcopy(FAMILY_DEFAULTS.get(slug, {}))
        titles = {**defaults.get('titles', {}), **raw_family.get('titles', {})}
        descriptions = {**defaults.get('descriptions', {}), **raw_family.get('descriptions', {})}
        pages = normalize_pages(
            slug=slug,
            pages=raw_family.get('pages', {}),
            output_dir=output_dir,
            base_dir=base_dir,
        )
        published_candidates = [page.get('published_at') for page in pages.values() if page.get('available') and page.get('published_at')]
        latest_published_at = raw_family.get('published_at')
        if not latest_published_at and published_candidates:
            latest_published_at = max(published_candidates)
        family = {
            'slug': slug,
            'order': raw_family.get('order', defaults.get('order', 100)),
            'titles': titles,
            'descriptions': descriptions,
            'pages': pages,
            'active': True,
            'archived': False,
            'published_at': latest_published_at,
            'available': any(page.get('available') for page in pages.values()),
        }
        family['freshness'] = compute_freshness(latest_published_at, generated_at)
        normalized_families.append(family)

    normalized_families.sort(key=lambda family: (family.get('order', 100), family['slug']))
    return {
        'manifest_version': raw_manifest.get('manifest_version', MANIFEST_VERSION),
        'generated_at': generated_at,
        'output_dir': str(output_dir),
        'families': normalized_families,
    }


def load_manifest(path: Path, *, output_dir: Path) -> dict[str, Any]:
    raw_manifest = json.loads(path.read_text(encoding='utf-8'))
    return finalize_manifest(raw_manifest, output_dir=output_dir, base_dir=path.parent.resolve())


def render_wrapper_page(
    *,
    page: dict[str, Any],
    family: dict[str, Any],
    output_path: Path,
    language: str,
) -> None:
    ensure_parent(output_path)
    family_title = family['titles'].get(language) or family['titles'].get('en') or family['slug']
    description = family['descriptions'].get(language) or family['descriptions'].get('en') or ''
    open_label = '打开原报告' if language == 'zh' else 'Open source report'
    back_label = '返回首页' if language == 'zh' else 'Back to hub'
    updated_label = '更新时间' if language == 'zh' else 'Updated'
    title = page.get('title') or family_title
    source_href = page.get('source_href', '')
    published_at = page.get('published_at') or 'n/a'
    published_at_display = format_timestamp_for_display(page.get('published_at'), language=language)
    html = f"""<!doctype html>
<html lang="{'zh-CN' if language == 'zh' else 'en'}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <style>
    :root {{ color-scheme: light; --bg: #f8fafc; --panel: #ffffff; --text: #0f172a; --muted: #64748b; --line: #e2e8f0; --accent: #2563eb; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif; }}
    .page {{ max-width: 1200px; margin: 0 auto; padding: 24px 18px 28px; }}
    .header {{ margin-bottom: 16px; }}
    .header h1 {{ margin: 0 0 8px; font-size: 1.9rem; }}
    .meta {{ color: var(--muted); margin-bottom: 12px; }}
    .actions {{ display: flex; gap: 12px; flex-wrap: wrap; }}
    .actions a {{ color: white; background: var(--accent); padding: 10px 14px; border-radius: 999px; text-decoration: none; font-weight: 600; }}
    .actions a.secondary {{ background: white; color: var(--accent); border: 1px solid var(--line); }}
    .frame {{ margin-top: 18px; border: 1px solid var(--line); border-radius: 16px; background: white; overflow: hidden; box-shadow: 0 12px 28px rgba(15, 23, 42, 0.06); }}
    iframe {{ display: block; width: 100%; min-height: 78vh; border: 0; background: white; }}
    p {{ margin: 0; line-height: 1.6; }}
  </style>
</head>
<body>
  <div class="page">
    <div class="header">
      <h1>{escape(family_title)}</h1>
      <div class="meta">{escape(description)}</div>
      <div class="meta">{escape(updated_label)}: {escape(published_at_display)}</div>
      <div class="actions">
        <a href="{escape(source_href)}">{escape(open_label)}</a>
        <a class="secondary" href="{'../index.html' if language == 'zh' else '../index_en.html'}">{escape(back_label)}</a>
      </div>
    </div>
    <div class="frame">
      <iframe src="{escape(source_href)}" title="{escape(title)}"></iframe>
    </div>
  </div>
</body>
</html>
"""
    output_path.write_text(html, encoding='utf-8')


def page_links_for_family(family: dict[str, Any], *, language: str) -> list[tuple[str, str]]:
    pages = family['pages']
    links: list[tuple[str, str]] = []
    if 'zh' in pages and pages['zh'].get('available'):
        links.append(('中文', pages['zh']['href']))
    if 'en' in pages and pages['en'].get('available'):
        links.append(('English', pages['en']['href']))
    if 'default' in pages and pages['default'].get('available'):
        links.append((('打开报告' if language == 'zh' else 'Open report'), pages['default']['href']))
    return links


def render_hub_page(manifest: dict[str, Any], *, language: str, output_path: Path) -> None:
    ensure_parent(output_path)
    page_title = '市场报告导航' if language == 'zh' else 'Market Report Hub'
    page_subtitle = (
        '活跃报告入口，统一汇总盘前、O\'Neil 扫描与可用回测页面。'
        if language == 'zh'
        else 'Landing surface for active report families across premarket, O\'Neil, and available backtests.'
    )
    lang_switch_href = 'index_en.html' if language == 'zh' else 'index.html'
    lang_switch_label = 'English' if language == 'zh' else '中文'
    updated_label = '站点生成时间' if language == 'zh' else 'Site generated'
    generated_at_display = format_timestamp_for_display(manifest.get('generated_at'), language=language)
    families_html: list[str] = []
    for family in manifest['families']:
        title = family['titles'].get(language) or family['titles'].get('en') or family['slug']
        description = family['descriptions'].get(language) or family['descriptions'].get('en') or ''
        freshness = family['freshness'][f'label_{language}']
        published_at = format_timestamp_for_display(family.get('published_at'), language=language)
        links = page_links_for_family(family, language=language)
        if links:
            link_html = ''.join(
                f'<a class="pill" href="{escape(href)}">{escape(label)}</a>'
                for label, href in links
            )
        else:
            link_html = (
                '<span class="pill disabled">暂不可用</span>'
                if language == 'zh'
                else '<span class="pill disabled">Unavailable</span>'
            )
        families_html.append(
            f"""
      <section class="card {'unavailable' if not family['available'] else ''}">
        <div class="card-head">
          <h2>{escape(title)}</h2>
          <span class="badge">{escape(freshness)}</span>
        </div>
        <p>{escape(description)}</p>
        <div class="meta">{'更新时间' if language == 'zh' else 'Updated'}: {escape(published_at)}</div>
        <div class="actions">{link_html}</div>
      </section>
            """.strip()
        )
    html = f"""<!doctype html>
<html lang="{'zh-CN' if language == 'zh' else 'en'}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(page_title)}</title>
  <style>
    :root {{ color-scheme: light; --bg: #0f172a; --panel: #ffffff; --text: #0f172a; --muted: #475569; --line: #dbe3ef; --accent: #2563eb; --badge: #eff6ff; --badge-text: #1d4ed8; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: linear-gradient(180deg, #0f172a 0%, #172554 100%); font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif; color: var(--text); }}
    .page {{ max-width: 1080px; margin: 0 auto; padding: 34px 18px 42px; }}
    .hero {{ color: white; margin-bottom: 22px; }}
    .hero h1 {{ margin: 0 0 8px; font-size: 2.2rem; }}
    .hero p {{ margin: 0; max-width: 760px; line-height: 1.7; color: rgba(255,255,255,0.86); }}
    .toolbar {{ margin-top: 14px; display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }}
    .toolbar a {{ color: white; text-decoration: none; border: 1px solid rgba(255,255,255,0.24); padding: 9px 12px; border-radius: 999px; }}
    .toolbar .meta {{ color: rgba(255,255,255,0.72); }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
    .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 18px; padding: 18px; box-shadow: 0 16px 32px rgba(15, 23, 42, 0.14); }}
    .card.unavailable {{ opacity: 0.82; }}
    .card-head {{ display: flex; gap: 10px; justify-content: space-between; align-items: flex-start; }}
    .card h2 {{ margin: 0; font-size: 1.25rem; }}
    .card p {{ margin: 12px 0; line-height: 1.65; color: var(--muted); min-height: 3.2em; }}
    .meta {{ color: var(--muted); font-size: 0.95rem; }}
    .badge {{ background: var(--badge); color: var(--badge-text); padding: 6px 10px; border-radius: 999px; font-size: 0.88rem; white-space: nowrap; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }}
    .pill {{ display: inline-flex; align-items: center; gap: 6px; text-decoration: none; padding: 9px 12px; border-radius: 999px; background: var(--accent); color: white; font-weight: 600; }}
    .pill.disabled {{ background: #e2e8f0; color: #475569; }}
  </style>
</head>
<body>
  <div class="page">
    <header class="hero">
      <h1>{escape(page_title)}</h1>
      <p>{escape(page_subtitle)}</p>
      <div class="toolbar">
        <a href="{escape(lang_switch_href)}">{escape(lang_switch_label)}</a>
        <span class="meta">{escape(updated_label)}: {escape(generated_at_display)}</span>
      </div>
    </header>
    <main class="grid">
      {''.join(families_html)}
    </main>
  </div>
</body>
</html>
"""
    output_path.write_text(html, encoding='utf-8')


def write_manifest(output_dir: Path, manifest: dict[str, Any]) -> Path:
    path = output_dir / 'site_manifest.json'
    ensure_parent(path)
    path.write_text(json.dumps(portable_manifest(manifest), indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return path


def cleanup_unavailable_wrapper(output_dir: Path, page: dict[str, Any]) -> None:
    target = output_dir / page['href']
    if target.exists():
        target.unlink()


def sync_local_source_preview(output_dir: Path, page: dict[str, Any]) -> None:
    source_path_raw = page.get('source_path')
    if not source_path_raw or not page.get('available'):
        return
    source_path = Path(source_path_raw)
    if not source_path.exists():
        return
    preview_target = output_dir / stable_source_href(source_path)
    ensure_parent(preview_target)
    preview_target.write_bytes(source_path.read_bytes())


def render_site(manifest: dict[str, Any], *, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    manifest_path = write_manifest(output_dir, manifest)
    written['manifest'] = manifest_path

    zh_index = output_dir / 'index.html'
    en_index = output_dir / 'index_en.html'
    render_hub_page(manifest, language='zh', output_path=zh_index)
    render_hub_page(manifest, language='en', output_path=en_index)
    written['index_zh'] = zh_index
    written['index_en'] = en_index

    for family in manifest['families']:
        for page in family['pages'].values():
            language = page['lang'] if page.get('lang') in {'zh', 'en'} else 'en'
            target = output_dir / page['href']
            if page.get('available'):
                sync_local_source_preview(output_dir, page)
                render_wrapper_page(page=page, family=family, output_path=target, language=language)
                written[f"{family['slug']}:{page['lang']}"] = target
            else:
                cleanup_unavailable_wrapper(output_dir, page)
    return written


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Render the active market report hub and stable site shell.',
    )
    parser.add_argument('--manifest', help='Existing manifest JSON to render from.')
    parser.add_argument('--output-dir', default=str(DEFAULT_OUTPUT_DIR), help='Output site directory. Default: reports/site')
    parser.add_argument('--generated-at', help='Override generated-at timestamp (ISO-8601).')
    parser.add_argument('--premarket-zh-source', help='Source HTML for the Chinese premarket report.')
    parser.add_argument('--premarket-en-source', help='Source HTML for the English premarket report.')
    parser.add_argument('--oneil-source', help="Source HTML for the O'Neil live report.")
    parser.add_argument('--minervini-source', help='Source HTML for the Minervini live report.')
    parser.add_argument('--qullamaggie-source', help='Source HTML for the Qullamaggie live report.')
    parser.add_argument('--oneil-backtest-source', help="Source HTML for the O'Neil backtest overview.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = Path(args.output_dir).resolve()
    if args.manifest:
        manifest = load_manifest(Path(args.manifest).resolve(), output_dir=output_dir)
    else:
        manifest = build_manifest_from_sources(args)
    written = render_site(manifest, output_dir=output_dir)
    for key in ('index_zh', 'index_en', 'manifest'):
        print(written[key])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
