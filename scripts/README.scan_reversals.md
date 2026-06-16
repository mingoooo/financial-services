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

- `--universe us`
- `--include-etfs`
- `--side both`
- `--min-market-cap 2000000000`
- `--min-price 1`
- `--min-avg-volume 750000`
- `--min-last-volume 50000`
- `--require-confirm-volume`
- `--recent-confirm-days 2`
- `--scan-retries 3`

默认会：

- 只显示最近 `2` 个自然日确认的信号
- 对临时错误自动重试
- 按 `score -> market_cap -> avg_dollar_volume_20` 排序

## 常用命令

### 1. 默认同时扫描看涨与看跌反转

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

## 主要参数

- `--side {both,bullish,bearish}`：扫描双向、只看涨或只看跌反转
- `--universe {us,sp500,liquid}`：选择扫描范围
- `--symbols`：直接传入股票代码
- `--exclude-etfs`：排除 ETF
- `--top-dollar-volume`：预筛后只保留成交额最高前 N 名
- `--recent-confirm-days`：只保留最近 N 个自然日确认的信号
- `--no-require-confirm-volume`：关闭确认日放量要求
- `--scan-retries`：单只股票失败重试次数
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
