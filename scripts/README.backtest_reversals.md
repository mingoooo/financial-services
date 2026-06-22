# 反转形态回测脚本

`scripts/backtest_reversals.py` 用于回测基于 `scripts/scan_reversals.py` 规则抽出的反转形态策略。

当前固化推荐版本：

- 股票池：`sp500`
- 预筛条件：沿用扫描脚本默认流动性条件
  - `min_market_cap=2_000_000_000`
  - `min_price=1`
  - `min_avg_volume=750_000`
  - `min_last_volume=50_000`
- 方向：`bullish`
- 确认量能：开启
- 结构空间：至少 `2R`
- 入场方式：确认日收盘入场
- 均线条件：确认日**刚上穿 `20SMA` 或 `50SMA` 任一条**

## 推荐命令

```bash
. .venv-backtest/bin/activate
python scripts/backtest_reversals.py \
  --preset main \
  --json /tmp/reversal-sp500-r2-bullish-smacross.json \
  --csv-dir /tmp/reversal-sp500-r2-bullish-smacross-csv \
  --html /tmp/reversal-sp500-r2-bullish-smacross.html
```

如需更高质量、但更少交易的版本：

```bash
. .venv-backtest/bin/activate
python scripts/backtest_reversals.py \
  --preset high_quality \
  --json /tmp/reversal-high-quality.json \
  --csv-dir /tmp/reversal-high-quality-csv \
  --html /tmp/reversal-high-quality.html
```

## 当前固化版本回测结果（参考）

基于本地一次完整回测结果：

- 样本：`sp500`
- 交易数：`32`
- 胜率：`65.625%`
- 平均单笔收益率：`1.8850%`
- 中位数收益率：`2.0781%`
- 总盈亏：`60356.9948`
- 最大回撤：`9.5317%`
- Profit Factor：`3.1398`

## 输出文件

- JSON：汇总指标、分组统计、参数快照
- CSV：逐笔交易、信号记录
- HTML：回测概览报表

## 缓存

K 线数据会缓存到：

- `.cache/bullish-reversal-scanner`

当前历史日线会做本地缓存；对历史区间回测来说，同类任务复跑会明显提速。

如果使用 5 年历史回测，缓存的目标就是“尽量长期复用历史 K 线”，减少重复拉取。

## preset 预设

为保证扫描、回测、工作流三处逻辑一致，当前统一支持以下预设：

- `main`：主策略版
- `high_quality`：高质量信号版

建议优先使用 `--preset`，而不是在命令行重复拼接大量策略参数。只有在你想做局部实验时，再单独覆盖某个参数。

当前回测脚本默认入场模式也已固化为：

- `entry_mode=confirm_close`

也就是：默认按**确认日收盘价入场**。如果只做常规回测，不需要额外传 `--entry-mode`。

## 最终推荐策略（5年回测结论）

基于 `sp500 + core ETF + bullish-only + 2R + fresh 20/50 SMA cross + 确认量能` 的 5 年回测结果，当前建议固化为两档：

### 1. 主策略版

推荐参数：

- `universe=sp500`
- `include_etfs=true`
- `etf_groups=core`
- `side=bullish`
- `min_r_multiple=2`
- `require_confirm_volume=true`
- `require_fresh_sma_cross_up=true`
- `sma_cross_mode=either`
- `require_rsi_above=50`

结果（5 年）：

- 交易数：`52`
- 胜率：`73.08%`
- 平均单笔收益率：`2.5131%`
- 中位数收益率：`2.4385%`
- 总盈亏：`130983.1060`
- 最大回撤：`7.9466%`
- Profit Factor：`5.8912`

### 2. 高质量信号版

在主策略版基础上，再增加：

- `require_macd_bullish=true`

结果（5 年）：

- 交易数：`38`
- 胜率：`78.95%`
- 平均单笔收益率：`3.0956%`
- 中位数收益率：`3.1165%`
- 总盈亏：`117743.9139`
- 最大回撤：`7.9466%`
- Profit Factor：`7.2234`

### 不建议默认加入的条件

- `require_above_sma200`

原因：在当前策略结构下，`SMA200` 过滤会显著压缩样本，同时降低胜率、平均收益率与 Profit Factor，并未带来额外回撤改善。


## 现成命令

### 主策略版

```bash
. .venv-backtest/bin/activate
python scripts/backtest_reversals.py \
  --range 5y \
  --preset main \
  --json /tmp/reversal-main-strategy.json \
  --csv-dir /tmp/reversal-main-strategy-csv \
  --html /tmp/reversal-main-strategy.html
```

### 高质量信号版

```bash
. .venv-backtest/bin/activate
python scripts/backtest_reversals.py \
  --range 5y \
  --preset high_quality \
  --json /tmp/reversal-high-quality.json \
  --csv-dir /tmp/reversal-high-quality-csv \
  --html /tmp/reversal-high-quality.html
```


## scan_reversals 默认行为（已同步）

当前 `scripts/scan_reversals.py` 默认不再是原始通用 reversal 扫描器，而是默认按正式主策略扫描：

- `universe=sp500`
- `include_etfs=true`
- `etf_groups=core`
- `side=bullish`
- `scan_mode=strategy`
- `require_confirm_volume=true`
- `min_r_multiple=2`
- `require_fresh_sma_cross_up=true`
- `sma_cross_mode=either`
- `require_rsi_above=50`

同时仍保留：

- `--scan-mode raw`

用于回退到更宽松的原始 reversal 信号视角。

## GitHub Action（已同步）

GitHub Action 现在也支持用 `preset` 驱动扫描：

- 默认 `preset=main`
- 可手动切换到 `high_quality`
- 已配置 `push` 触发：当策略脚本、共享库、ETF 白名单或该 workflow 本身发生变更时自动跑一次

当前 `workflow_dispatch` 仅保留以下输入，和现版本 workflow 完全一致：

- `preset`：策略预设，支持 `main` / `high_quality`
- `recent_confirm_days`：仅保留最近 N 天确认信号
- `workers`：并发 worker 数
- `scan_retries`：单股票重试次数
- `no_cache`：是否禁用本地缓存
- `deploy_pages`：若启用 Pages，是否部署 HTML 报告

也就是说，GitHub Action 现在是明确的 **preset-first** 设计：

- 策略参数不再在 workflow 里逐项暴露
- 扫描逻辑默认跟随 `preset`
- 如果要改策略本身，应优先改 `preset` 或共享策略代码，而不是改 workflow 输入

## 参数实验工作流

现在支持通过配置文件批量运行多组策略回测：

- 配置文件：`scripts/reversal_experiments.yaml`
- 实验入口：`scripts/run_reversal_experiments.py`

示例：

```bash
python3 scripts/run_reversal_experiments.py
python3 scripts/run_reversal_experiments.py --experiments main_current,main_relaxed_combo
```

输出目录默认位于：

- `reports/reversal-experiments/<run_id>/`

其中包含：

- 每个实验单独的 `summary.json` / `csv/` / `report.html`
- 总榜 `leaderboard.json` / `leaderboard.csv` / `index.html`

回测汇总已新增：

- `sharpe_ratio`
- `sharpe_basis`（当前为 `trade_returns`）

## Regression fixtures

Deterministic regression fixtures live under `tests/fixtures/reversal/` and are used by `tests/reversal_lib/test_backtest_pipeline.py`.

- `main_preset_fixture.json`: frozen `META` 5y candles, currently expected to backtest to 2 trades, `win_rate=100.0`, `average_return_pct=3.6092`, `total_pnl=7297.7603` under `preset=main`.
- `high_quality_fixture.json`: frozen `APLE` 5y candles, currently expected to backtest to 1 trade, `win_rate=100.0`, `average_return_pct=2.095`, `total_pnl=2094.9013` under `preset=high_quality`.
- `no_signal_fixture.json`: frozen `AAPL` 5y candles, expected to backtest to 0 trades.

These fixtures intentionally avoid live Yahoo / Finviz dependencies during test runs.

