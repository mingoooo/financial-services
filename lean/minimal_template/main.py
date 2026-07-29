from AlgorithmImports import *


class MinimalMovingAverageTemplate(QCAlgorithm):
    def Initialize(self) -> None:
        self.SetStartDate(*self._parse_date_param("start_date", (2023, 1, 1)))
        self.SetEndDate(*self._parse_date_param("end_date", (2024, 1, 1)))
        self.SetCash(self._parse_float_param("initial_cash", 100000))

        ticker = self.GetParameter("ticker") or "SPY"
        resolution_name = (self.GetParameter("resolution") or "Daily").strip().lower()
        resolution = self._parse_resolution(resolution_name)

        self.fast_period = self._parse_int_param("fast_period", 20, minimum=1)
        self.slow_period = self._parse_int_param("slow_period", 50, minimum=2)
        if self.fast_period >= self.slow_period:
            self.Debug(
                f"Invalid MA configuration fast_period={self.fast_period} slow_period={self.slow_period}; resetting to defaults 20/50"
            )
            self.fast_period = 20
            self.slow_period = 50

        self.position_size = self._parse_float_param("position_size", 1.0, minimum=0.0, maximum=1.0)
        self.symbol = self.AddEquity(ticker, resolution).Symbol

        self.fast_ma = self.SMA(self.symbol, self.fast_period, resolution)
        self.slow_ma = self.SMA(self.symbol, self.slow_period, resolution)
        self.SetWarmUp(self.slow_period)

        self.previous_fast = None
        self.previous_slow = None
        self.logged_warmup_wait = False
        self.logged_no_position = False

        self.Debug(
            "Initialized minimal LEAN template "
            f"ticker={ticker} resolution={resolution_name} fast={self.fast_period} slow={self.slow_period} position_size={self.position_size}"
        )

    def OnData(self, data: Slice) -> None:
        if self.IsWarmingUp or not self.fast_ma.IsReady or not self.slow_ma.IsReady:
            if not self.logged_warmup_wait:
                self.Debug("Indicators not ready yet; waiting for warm-up to complete")
                self.logged_warmup_wait = True
            return

        if not data.Bars.ContainsKey(self.symbol):
            return

        current_fast = float(self.fast_ma.Current.Value)
        current_slow = float(self.slow_ma.Current.Value)

        if self.previous_fast is None or self.previous_slow is None:
            self.previous_fast = current_fast
            self.previous_slow = current_slow
            self.Debug("Indicators ready; starting crossover evaluation")
            return

        crossed_above = self.previous_fast <= self.previous_slow and current_fast > current_slow
        crossed_below = self.previous_fast >= self.previous_slow and current_fast < current_slow
        invested = self.Portfolio[self.symbol].Invested

        if crossed_above and not invested:
            self.SetHoldings(self.symbol, self.position_size)
            self.Debug(
                f"Bullish crossover detected; entering long position at {self.Time.date()} fast={current_fast:.2f} slow={current_slow:.2f}"
            )
            self.logged_no_position = False
        elif crossed_below and invested:
            self.Liquidate(self.symbol, "Bearish crossover exit")
            self.Debug(
                f"Bearish crossover detected; exiting position at {self.Time.date()} fast={current_fast:.2f} slow={current_slow:.2f}"
            )
        elif not invested and not self.logged_no_position:
            self.Debug("No active position; waiting for bullish crossover")
            self.logged_no_position = True

        self.previous_fast = current_fast
        self.previous_slow = current_slow

    def _parse_int_param(self, name: str, default: int, minimum: int | None = None) -> int:
        raw = self.GetParameter(name)
        if raw in (None, ""):
            return default
        try:
            value = int(raw)
        except ValueError:
            self.Debug(f"Invalid integer parameter {name}={raw}; using default {default}")
            return default
        if minimum is not None and value < minimum:
            self.Debug(f"Parameter {name} below minimum {minimum}; using default {default}")
            return default
        return value

    def _parse_float_param(
        self,
        name: str,
        default: float,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float:
        raw = self.GetParameter(name)
        if raw in (None, ""):
            return default
        try:
            value = float(raw)
        except ValueError:
            self.Debug(f"Invalid float parameter {name}={raw}; using default {default}")
            return default
        if minimum is not None and value < minimum:
            self.Debug(f"Parameter {name} below minimum {minimum}; using default {default}")
            return default
        if maximum is not None and value > maximum:
            self.Debug(f"Parameter {name} above maximum {maximum}; using default {default}")
            return default
        return value

    def _parse_date_param(self, name: str, default: tuple[int, int, int]) -> tuple[int, int, int]:
        raw = self.GetParameter(name)
        if raw in (None, ""):
            return default
        try:
            parsed = datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            self.Debug(f"Invalid date parameter {name}={raw}; using default {default[0]}-{default[1]:02d}-{default[2]:02d}")
            return default
        return parsed.year, parsed.month, parsed.day

    def _parse_resolution(self, name: str) -> Resolution:
        mapping = {
            "daily": Resolution.Daily,
            "hour": Resolution.Hour,
            "minute": Resolution.Minute,
        }
        if name not in mapping:
            self.Debug(f"Invalid resolution '{name}'; using Daily")
            return Resolution.Daily
        return mapping[name]
