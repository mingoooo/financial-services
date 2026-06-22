# Reversal regression fixtures

These fixtures freeze candle inputs for the current reversal scan/backtest behavior so tests do not depend on live Yahoo or Finviz responses.

## Selected targets

- Bullish symbol/date range that produces signals: `META` 5y fixture, with `preset=main`, produces 2 bullish signals confirmed on `2021-10-28` and `2023-07-27`.
- Symbol/date range that produces no signals: `AAPL` 5y fixture, with `preset=main` and `preset=high_quality`, produces 0 signals.
- Fixed fixture for `preset=main`: `tests/fixtures/reversal/main_preset_fixture.json` copied from cached `META` 5y candles.
- Fixed fixture for `preset=high_quality`: `tests/fixtures/reversal/high_quality_fixture.json` copied from cached `APLE` 5y candles.

## Fixture inventory

- `aapl_bullish_fixture.json`: fixed 5y candles for `META`; despite the historical filename example, this fixture intentionally captures a bullish symbol with current stable `main` signals.
- `no_signal_fixture.json`: fixed 5y candles for `AAPL`.
- `main_preset_fixture.json`: fixed 5y candles for `META` used to lock `preset=main` scan and backtest metrics.
- `high_quality_fixture.json`: fixed 5y candles for `APLE` used to lock `preset=high_quality` scan and backtest metrics.

## Source

All four files were exported from `.cache/bullish-reversal-scanner/ohlcv_*_5y.json` captured in this repository before refactoring.
