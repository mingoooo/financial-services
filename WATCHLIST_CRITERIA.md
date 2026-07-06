# Watchlist Criteria

这份文件是盘前扫描器的规则源文件。
先用这些规则筛名单，再让后面的分析层去判断质量。
如果后续 prompt、scanner、report 有冲突，以这里为准。

## 1. Day Trading Watchlist

### Setup: Trend Join Long

**这套东西是干嘛的**
- 这是追随强势趋势、等突破再上的日内 long setup。
- 不是抄底，不是猜顶，就是等市场自己证明它还想往上走。

**回测表现**
- 胜率：54.6%
- Profit Factor：1.59
- 样本数：280 trades

**盘前筛选条件**
> 全部必需，同时满足。

- Gap % vs previous close > 3%
- Price > $3
- Market cap > $1B
- Premarket relative volume (RVOL) > 1.5
- Price breaks above yesterday's high

**盘中执行计划**
- 观察时间窗：10:00am 到 3:30pm ET
- 触发条件：价格 > premarket high，并且 > 当日此前 high-of-day
- 初始止损：放在 premarket high 下方 1%，或 LOD，以更低的那个为准
- 风险定义：从入场到止损这段距离记作 1R
- 止盈分批：+1R 出 1/3，+2R 再出 1/3
- 尾仓管理：最后 1/3 用 21-EMA 跟踪
- 收盘处理：最晚 3:51pm ET 全部平仓

**怎么理解这套 setup**
- 重点不是它涨了多少，而是它有没有真强到能过盘前高，还能继续打出当日新高。
- 如果只是高开以后横着磨，或者冲一下又掉回去，那就不是这套东西最想要的样子。

## 2. Swing Watchlist

**这套东西是干嘛的**
- 这是给波段观察名单用的强催化 gap setup。
- 核心不是追一根大阳线本身，而是找那种有真实事件推动、可能继续走出一段趋势的名字。

**回测表现**
- News catalysts：57.6% 胜率 / PF 5.34
- Earnings catalysts：44.7% 胜率 / PF 2.57

**盘前筛选条件**
> 全部必需，同时满足。

- Gap % >= 8%
- Price > $3
- Open > yesterday's high
- Open > 200-day SMA
- Market cap >= $800M
- 必须有真实催化
  - 要么是 gap 当天的 earnings
  - 要么是没有 earnings 的 news catalyst

**执行备注**
- 这套目前只用于生成 swing starter ideas。
- Swing 的正式入场、加仓、止损、止盈管理还在开发中。
- 所以这里先不编假的 stops，也不编假的 price targets。
- 看到名字进名单，不等于立刻能做，只代表它值得继续盯。

## 3. Scanner Implementation Notes

- Scanner 先严格编码这些硬规则，不要先加主观判断。
- 先解决有没有入围，再解决值不值得做。
- Day trading 和 swing 是两套不同名单，不要混成一个评分池。
- Swing 名单里的 catalyst 字段必须明确标注是 `earnings` 还是 `news`。
- 如果缺少必要字段，默认不入选，不要脑补。

## 4. Voice And Usage Notes

- 后续 analyst prompt、merge prompt、report 都以这份规则为 source of truth。
- 写法保持简洁、直白、讲人话。
- 语气偏 casual，接近 Humbled Trader 那种盘前沟通方式。
- 不要用 em dash。
