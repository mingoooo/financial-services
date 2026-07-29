# LEAN Templates

This directory contains LEAN-native strategy templates for future backtesting work.

The first template is intentionally small and self-contained. It is meant to teach the LEAN workflow and provide a copyable baseline for new strategy development.

## Included Template

- `minimal_template/main.py` — single-file moving-average crossover template using `QCAlgorithm`

## Purpose

Use this template when you want to:

- validate a local LEAN setup,
- understand how a LEAN algorithm is structured,
- start a new strategy from a minimal baseline,
- or teach a teammate the LEAN backtest lifecycle.

This template is **not** intended to represent production strategy architecture.

## What The Template Does

The algorithm:

- sets a backtest date range and initial cash,
- subscribes to one equity symbol,
- computes a fast and slow simple moving average,
- enters a long position when the fast MA crosses above the slow MA,
- exits when the fast MA crosses below the slow MA,
- logs key state transitions to make the behavior easier to follow.

## Supported Parameters

The template uses LEAN parameters with safe defaults.

- `ticker` — default `SPY`
- `start_date` — default `2023-01-01`
- `end_date` — default `2024-01-01`
- `initial_cash` — default `100000`
- `resolution` — default `Daily` (`Daily`, `Hour`, or `Minute`)
- `fast_period` — default `20`
- `slow_period` — default `50`
- `position_size` — default `1.0` (fraction from `0.0` to `1.0`)

If a parameter is missing or invalid, the template falls back to a documented default and emits a debug log.


## Example Local Configuration

A sample parameter file is included at:

- `minimal_template/lean.example.json`

Use it as a reference for the algorithm path and parameter names. You may need to adapt it to your local LEAN CLI or Docker-based configuration format.

## Expected Local Workflow

Use your normal LEAN local workflow to point a backtest at:

- algorithm file: `lean/minimal_template/main.py`

The exact command can vary depending on how LEAN is installed locally, so this repository intentionally documents the algorithm path and behavior rather than assuming one specific machine setup.

## Suggested First Experiments

After you get a successful run, try changing one thing at a time:

- change `ticker` from `SPY` to another liquid equity,
- shorten or lengthen the MA windows,
- reduce `position_size`,
- switch `resolution` from `Daily` to `Hour`.

## What To Inspect After A Backtest

Review these first:

- trade list,
- equity curve,
- drawdown,
- debug logs,
- whether the strategy traded when you expected.

If no trades occur, read the logs first. The template logs warm-up and waiting states so the reason should be understandable.

## Design Constraints

This first template deliberately avoids:

- multi-asset logic,
- advanced risk models,
- custom data sources,
- shared helper abstractions,
- integration with `scripts/reversal_lib`.

Those can be added later only after there is evidence that the team needs them.


## Yahoo 日线下载脚本

按回测时间自动下载匹配区间的 LEAN 本地日线数据：

```bash
python3 scripts/download_yahoo_to_lean_daily.py   --lean-project /Users/huangsm43/Documents/mingo/code/backtest/main-strategy-cs
```

显式指定回测窗口：

```bash
python3 scripts/download_yahoo_to_lean_daily.py   --start-date 2020-04-01   --end-date 2021-03-31   --symbols SPY,AAPL,MSFT
```

说明：
- 脚本会自动在回测开始日前额外补 `120` 个自然日，用于 SMA 等 warmup。
- 输出为 LEAN 兼容的 `data/equity/usa/daily/<symbol>.zip` 格式。
- 同时会写出 `yahoo_sp500_download_metadata.json`，记录本次下载对应的回测窗口。
