# 反转形态扫描脚本

`scripts/scan_reversals.py` 用于扫描美股 / ETF 的**已确认反转形态**。

数据源：

- **Finviz / finvizfinance**：预筛选
- **Yahoo Finance**：日线 OHLCV、形态识别、HTML 图表

## 支持的形态

### 看涨

- `Hammer / 锤头线`
- `Inverted Hammer / 倒锤头线`
- `Bullish Engulfing / 看涨吞没`
- `Piercing Pattern / 刺透形态`
- `Morning Star / 启明星`
- `Bullish Harami / 看涨孕线`

### 看跌

- `Shooting Star / 流星线`
- `Hanging Man / 上吊线`
- `Bearish Engulfing / 看跌吞没`
- `Dark Cloud Cover / 乌云盖顶`
- `Evening Star / 黄昏星`
- `Bearish Harami / 看跌孕线`

说明：只有**下一交易日确认**后，脚本才会输出结果。

## 默认行为

默认参数：

- `--preset main`
- `--min-market-cap 2000000000`
- `--min-price 1`
- `--min-avg-volume 750000`
- `--min-last-volume 50000`
- `--require-confirm-volume`
- `--min-r-multiple 2`
- `--require-fresh-sma-cross-up`
- `--sma-cross-mode either`
- `--require-rsi-above 50`
- `--recent-confirm-days 2`
- `--scan-retries 3`

默认会：

- 只显示最近 `2` 个自然日确认的信号
- 对临时错误自动重试
- 按 `score -> market_cap -> avg_dollar_volume_20` 排序

## 常用命令

### 1. 默认扫描正式主策略

```bash
python3 scripts/scan_reversals.py
```

### 2. 只扫描看跌反转

```bash
python3 scripts/scan_reversals.py --side bearish
```

### 3. 扫描 S&P 500

```bash
python3 scripts/scan_reversals.py --universe sp500
```

### 4. 只扫自选股

```bash
python3 scripts/scan_reversals.py --symbols AAPL,NVDA,SPY,TSLA
```

### 5. 生成 HTML 报表

```bash
python3 scripts/scan_reversals.py --html /tmp/reversal_report.html
```

### 6. 禁用缓存重跑

```bash
python3 scripts/scan_reversals.py --no-cache
```

### 7. 生成看跌 HTML 报表

```bash
python3 scripts/scan_reversals.py --side bearish --html /tmp/bearish_reversal_report.html
```

## 结果说明

终端表格主要字段：

- `Pattern`：形态名称
- `Strength`：形态强度
- `Score`：综合评分
- `Candidate`：候选形态日期
- `Confirm`：确认日日期
- `MktCap`：市值
- `Stop / T1 / T2`：止损与目标位

HTML 报表额外包含：

- 蜡烛图
- SMA10 / SMA20 / SMA50 / SMA200（显示当前数值）
- 成交量子图
- 自动支撑位 / 阻力位（S1 / S2 / R1 / R2）
- 确认原因
- 评分明细
- 运行摘要（生成时间、参数、命中数量）

## 主要参数

- `--side {both,bullish,bearish}`：扫描双向、只看涨或只看跌反转
- `--universe {us,sp500,liquid}`：选择扫描范围
- `--symbols`：直接传入股票代码
- `--exclude-etfs`：排除 ETF
- `--top-dollar-volume`：预筛后只保留成交额最高前 N 名
- `--recent-confirm-days`：只保留最近 N 个自然日确认的信号
- `--no-require-confirm-volume`：关闭确认日放量要求
- `--scan-retries`：单只股票失败重试次数
- 网络请求默认超时已调长，降低慢响应导致的失败
- `--no-cache`：本次运行不读写本地缓存
- `--html`：输出 HTML 报表
- `--json`：输出 JSON

## 安装

```bash
. .venv/bin/activate
pip install finvizfinance
```

## 校验

```bash
python3 scripts/check.py
```

## GitHub 定时执行

仓库已提供 GitHub Actions 工作流：

- `.github/workflows/scan-reversals.yml`

功能：

- 支持手动触发
- 支持工作日定时执行
- 生成 HTML 与 JSON 报表
- 作为 artifact 上传到 GitHub Actions

默认执行命令等价于：

```bash
python3 scripts/scan_reversals.py \
  --preset main \
  --recent-confirm-days 2 \
  --workers 8 \
  --no-cache \
  --html reports/site/index.html \
  --json reports/reversal_signals.json
```

## GitHub Pages 查看报告

仓库已配置 GitHub Actions 工作流：

- Workflow: `.github/workflows/scan-reversals.yml`
- 默认上传 artifact：`reports/site/index.html` 与 `reports/reversal_signals.json`
- `push` / `schedule` 默认会更新 GitHub Pages
- 手动触发时可通过 `deploy_pages=false` 跳过 Pages 发布
- 定时运行时间为：**工作日 22:15 UTC**，并在 workflow 内用纽约时间做收盘后窗口判断
- workflow 运行后会尝试发送 Telegram 通知（需配置 GitHub Secrets）

所需 Secrets：

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

说明：如果仓库尚未开启 Pages，workflow 仍会成功生成 artifact；Telegram 通知脚本会在没有 Secrets 时自动跳过。

## GitHub Actions 可调参数

手动运行 `Scan Reversals` workflow 时，可以在 GitHub 页面直接设置这些参数：

- `preset`
- `recent_confirm_days`
- `workers`
- `scan_retries`
- `no_cache`
- `deploy_pages`

## 扩展时段数据验证

如果你要评估“盘后开盘价 / 盘前开盘价”回测是否可行，可以先跑：

```bash
. .venv-backtest/bin/activate
python scripts/check_extended_hours_data.py \
  --symbols AAPL,QQQ,SPY,SMH,GLD \
  --period 5d \
  --interval 1m \
  --output /tmp/extended-hours-check.json
```

这个脚本会用 `yfinance` 的 `prepost=True` 拉取分钟数据，先验证：

- 是否有扩展时段数据
- 返回条数是否稳定
- 时间索引是否符合预期
