from __future__ import annotations

import argparse
import json
from pathlib import Path

import yfinance as yf


def main() -> int:
    parser = argparse.ArgumentParser(description='验证扩展时段分钟数据是否可用')
    parser.add_argument('--symbols', default='AAPL,QQQ,SPY,SMH,GLD')
    parser.add_argument('--period', default='5d')
    parser.add_argument('--interval', default='1m')
    parser.add_argument('--output')
    args = parser.parse_args()

    results = []
    for symbol in [s.strip() for s in args.symbols.split(',') if s.strip()]:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=args.period, interval=args.interval, prepost=True, auto_adjust=False)
        has_data = not df.empty
        index_preview = []
        if has_data:
            index_preview = [str(v) for v in df.index[:5].tolist()]
        results.append({
            'symbol': symbol,
            'rows': int(len(df)),
            'has_data': has_data,
            'index_preview': index_preview,
        })

    payload = {
        'period': args.period,
        'interval': args.interval,
        'prepost': True,
        'results': results,
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text, encoding='utf-8')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
