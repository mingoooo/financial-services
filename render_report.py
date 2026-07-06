import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import markdown

ET = ZoneInfo("America/New_York")
OUT_EN = Path("reports/premarket_.html")
OUT_ZH = Path("reports/premarket_zh.html")

CSS = """
:root {
  color-scheme: light;
  --bg: #f6f7f9;
  --panel: #ffffff;
  --text: #1f2937;
  --muted: #6b7280;
  --line: #e5e7eb;
  --line-strong: #d1d5db;
  --head: #f3f4f6;
  --stripe: #fafafa;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: Inter, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.7;
}
.container {
  max-width: 900px;
  margin: 0 auto;
  padding: 32px 20px 56px;
}
header {
  margin-bottom: 28px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--line);
}
header h1 {
  margin: 0 0 8px;
  font-size: 2rem;
  line-height: 1.2;
}
header .meta {
  color: var(--muted);
  font-size: 0.98rem;
}
main {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 28px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}
h2, h3 {
  line-height: 1.3;
  margin-top: 1.8em;
  margin-bottom: 0.7em;
}
h2 {
  font-size: 1.35rem;
  border-bottom: 1px solid var(--line);
  padding-bottom: 0.35rem;
}
h3 { font-size: 1.08rem; }
p, li, blockquote { font-size: 1rem; }
ul, ol { padding-left: 1.3rem; }
blockquote {
  margin: 1rem 0;
  padding: 0.8rem 1rem;
  background: #f9fafb;
  border-left: 4px solid var(--line-strong);
  color: var(--text);
}
table {
  width: 100%;
  border-collapse: collapse;
  margin: 1rem 0 1.4rem;
  font-size: 0.95rem;
}
th, td {
  border: 1px solid var(--line);
  padding: 10px 12px;
  text-align: left;
  vertical-align: top;
}
th {
  background: var(--head);
  font-weight: 600;
}
tbody tr:nth-child(even) td { background: var(--stripe); }
code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  background: #f3f4f6;
  padding: 0.1rem 0.3rem;
  border-radius: 6px;
}
pre {
  overflow-x: auto;
  background: #111827;
  color: #f9fafb;
  padding: 14px;
  border-radius: 10px;
}
pre code {
  background: transparent;
  padding: 0;
  color: inherit;
}
hr {
  border: 0;
  border-top: 1px solid var(--line);
  margin: 2rem 0;
}
footer {
  color: var(--muted);
  font-size: 0.92rem;
  text-align: center;
  margin-top: 18px;
}
"""

SECTION_MAP = {
    "Summary": "摘要",
    "📊 Pre-Market Gappers": "📊 盘前异动股",
    "☀️ Day Trading Watchlist": "☀️ 日内观察名单",
    "📈 Notable Swing Watchlist": "📈 值得留意的波段观察名单",
    "📉 Market Trends of the Day": "📉 今日市场趋势",
    "📊 Technical Signals for Today": "📊 今日技术信号",
    "💰 Economic Data, Rates & the Fed": "💰 经济数据、利率和美联储",
    "📅 Coming Up": "📅 接下来",
    "🚫 Skips & Traps": "🚫 放弃项与陷阱",
    "🤖 Where the two brains landed": "🤖 两个脑子最后落点",
}

TABLE_MAP = {
    "Ticker": "代码",
    "Catalyst": "催化",
    "Catalyst (headline)": "催化（标题）",
    "Levels (live)": "关键价位（实时）",
    "Plan (Trend Join)": "计划（顺势跟随）",
    "Trend context": "趋势背景",
    "Idea": "想法",
    "🤖 Codex": "🤖 Codex",
    "Conv.": "信心",
}

PHRASE_MAP = [
    ("No clean catalyst headline found", "没有找到干净的催化标题"),
    ("No codex_view.md provided. Packet only.", "未提供 codex_view.md。这里只是 packet 整理结果。"),
    ("No clean day setup passed the hard rules in this packet", "这份 packet 里没有日内 setup 通过硬规则"),
    ("No swing name passed the hard rules in this packet", "这份 packet 里没有波段名字通过硬规则"),
    ("Stand aside and wait for cleaner confirmation", "先站一边，等更干净的确认"),
    ("Starter idea only. Swing entries and exits are still not finalized.", "这里只是起步观察想法。波段入场和出场规则还没最终定稿。"),
    ("light data day", "数据面偏轻的一天"),
    ("Econ feed unavailable.", "经济日历源当前不可用。"),
    ("Rates snapshot:", "利率快照："),
    ("Candidate source:", "候选来源："),
    ("Hard-screened gappers in packet:", "packet 里通过初筛的跳空名单数量："),
    ("This is still raw data first. Quality judgment is limited because no separate view files were supplied.", "这份内容本质上还是原始数据整理，因为没有单独的视角文件，所以质量判断能力有限。"),
    ("Trend Join names need a clean push through premarket high and then a fresh high of day.", "顺势跟随类型的名字，必须先干净突破盘前高，然后再打出新的日内高点。"),
    ("If a gapper cannot stay above prior-day high, the setup gets a lot less interesting fast.", "如果一个跳空名字连前一日高点都站不住，这个 setup 的吸引力会很快下降。"),
    ("RVOL here is a keyless stand-in based on full-day relative volume, not a true premarket feed.", "这里的 RVOL 只是基于全天相对成交量的无 key 近似值，不是真正的盘前 feed。"),
    ("No high-impact USD event listed for tomorrow in the cached/live feed.", "缓存或实时 feed 里没有列出明天的美元高影响事件。"),
    ("Notable earnings dates from gappers were limited or unavailable.", "跳空名单里的重要财报日期信息有限，或者当前拿不到。"),
    ("Failed day screen:", "未通过日内筛选："),
    ("Failed swing screen:", "未通过波段筛选："),
    ("Weak catalyst match:", "催化匹配偏弱："),
    ("Usually missing RVOL, prior-high reclaim, or clean structure.", "通常是缺 RVOL、没有重新站上前高，或者结构不够干净。"),
    ("Usually missing real catalyst, 200d context, or valid open rules.", "通常是缺真实催化、200 日线背景不够，或者开盘条件不成立。"),
    ("The headline match filter stayed strict on purpose.", "标题匹配过滤器是故意保持严格的。"),
    ("Agreement: unavailable because no separate Claude or Codex view files were provided.", "共同结论：当前不可用，因为没有单独提供 Claude 或 Codex 视角文件。"),
    ("Rules vs discretion: no separate discretion layer was provided, so this report sticks to deterministic packet facts only.", "规则派 vs 自由裁量派：当前没有额外的自由裁量层，所以这份报告只基于确定性的 packet 事实。"),
    ("Claude's sharp catch the other missed: unavailable.", "Claude 抓到而另一边没抓到的尖锐点：当前不可用。"),
    ("Codex's sharp catch the other missed: unavailable.", "Codex 抓到而另一边没抓到的尖锐点：当前不可用。"),
    ("trade where they agree; where they disagree, stand down or size down; never average.", "只做两边都同意的地方；有分歧就别硬上，或者降仓位；永远不要平均。"),
    ("Packet only.", "仅基于 packet。"),
    ("live levels unavailable", "实时关键位暂不可用"),
    ("trend context limited", "趋势背景信息有限"),
    ("Tape backdrop:", "盘面背景："),
    ("The catch we are watching:", "今天最该盯的那个点："),
    ("Two-brain verdict:", "双脑结论："),
    ("Full catalyst headline:", "完整催化标题："),
    ("Price:", "价格："),
    ("Gap:", "跳空幅度："),
    ("Market cap:", "市值："),
    ("Live levels:", "实时关键位："),
    ("Flags:", "标记："),
    ("Wait for Trend Join confirmation above PMH and fresh HOD. No chase if it cannot hold.", "等价格在盘前高上方给出顺势跟随确认，并且继续打出新的日内高点。站不住就别追。"),
    ("No starter idea today from the hard screen", "今天硬筛选没有给出合格的起步观察想法"),
    ("Tape backdrop", "盘面背景"),
    ("gappers", "跳空名字"),
    ("gapper", "跳空名字"),
    ("priced-in", "已经被交易得比较满了"),
    ("starter idea", "起步观察想法"),
    ("trend context", "趋势背景"),
    ("Trend Join", "顺势跟随"),
    ("None", "无"),
    ("HIGH", "高"),
    ("MED", "中"),
    ("LOW/skip", "低 / 跳过"),
]


def extract_title(md_text: str) -> str:
    for line in md_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "Premarket Report"


def first_date_line(md_text: str) -> str | None:
    for line in md_text.splitlines():
        if line.startswith("### "):
            return line[4:].strip()
    return None


def normalize_date(date_arg: str | None) -> str:
    if date_arg:
        return date_arg
    return datetime.now(ET).strftime("%Y-%m-%d")


def localize_title(title: str) -> str:
    if title == "🧠 AI PREMARKET REPORT — Humbled Trader":
        return "🧠 AI 盘前报告 | Humbled Trader 风格"
    return title.replace("—", "|")


def localize_meta(report_date: str) -> str:
    dt = datetime.strptime(report_date, "%Y-%m-%d")
    return f"{dt.year}年{dt.month:02d}月{dt.day:02d}日 | Claude + Codex（GPT-5.5）独立两遍扫描"


def localize_line(line: str) -> str:
    if line.startswith("### Watchlists built by the rules:"):
        return "### 观察名单先由规则生成：Day = 顺势跟随 · Swing = 跳空上涨 + 真实催化"
    if line.startswith("> Disclaimer:"):
        return "> 免责声明：是否入选先由确定性规则决定，AI 只负责后续质量判断。若涉及盘中 RVOL，这里有 keyless 数据限制。全文仅供学习参考，不构成任何投资建议。"
    return line


def translate_phrases(text: str) -> str:
    out = text
    for old, new in PHRASE_MAP:
        out = out.replace(old, new)
    return out


def localize_sections(md_text: str) -> str:
    lines = []
    for raw in md_text.splitlines():
        line = localize_line(raw)
        if line.startswith("## "):
            key = line[3:].strip()
            line = f"## {SECTION_MAP.get(key, key)}"
        elif line.startswith("| ") and "|" in line:
            parts = [p.strip() for p in line.strip().split("|")[1:-1]]
            if parts:
                mapped = [TABLE_MAP.get(p, p) for p in parts]
                line = "| " + " | ".join(mapped) + " |"
        line = translate_phrases(line)
        lines.append(line)
    return "\n".join(lines)


def build_html(md_text: str, report_date: str, footer_text: str, zh: bool) -> str:
    title = extract_title(md_text)
    if zh:
        md_text = localize_sections(md_text)
        title = localize_title(title)
        meta = localize_meta(report_date)
    else:
        meta = first_date_line(md_text) or report_date
    body_html = markdown.markdown(md_text, extensions=["tables", "fenced_code", "sane_lists"])
    return f"""<!doctype html>
<html lang=\"{'zh-CN' if zh else 'en'}\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{title}</title>
  <style>{CSS}</style>
</head>
<body>
  <div class=\"container\">
    <header>
      <h1>{title}</h1>
      <div class=\"meta\">{meta}</div>
    </header>
    <main>
      {body_html}
    </main>
    <footer>{footer_text}</footer>
  </div>
</body>
</html>
"""


def render_pair(report_path: Path, report_date: str):
    md_text = report_path.read_text()
    html_en = build_html(md_text, report_date, "Generated · Built by Claude + Codex · Educational only, not financial advice", zh=False)
    html_zh = build_html(md_text, report_date, "生成时间 · 由 Claude + Codex 构建 · 仅供学习参考，不构成任何投资建议", zh=True)
    OUT_EN.parent.mkdir(parents=True, exist_ok=True)
    OUT_EN.write_text(html_en)
    OUT_ZH.write_text(html_zh)
    print(OUT_EN)
    print(OUT_ZH)


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python render_report.py REPORT.md [YYYY-MM-DD]")
    report_path = Path(sys.argv[1])
    report_date = normalize_date(sys.argv[2] if len(sys.argv) > 2 else None)
    render_pair(report_path, report_date)


if __name__ == "__main__":
    main()
