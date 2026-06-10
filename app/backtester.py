import csv
from pathlib import Path

from app.models import SignalAction
from app.strategy import generate_signal, should_exit_trade
from app.risk import (
    calculate_rr,
    calculate_result_percent,
)
from app.liquidity import (
    analyze_liquidity,
    describe_liquidity,
    format_liquidity_level,
)


class Backtester:
    TRADE_FIELDNAMES = [
        "direction",
        "open_time",
        "entry_price",
        "initial_stop_loss",
        "stop_loss",
        "tp1",
        "tp2",
        "tp3",
        "risk_percent",
        "score",
        "reasons",

        "nearest_high_above",
        "nearest_high_below",
        "nearest_low_above",
        "nearest_low_below",

        "breakeven_active",
        "breakeven_time",

        "tp1_hit",
        "tp1_time",

        "tp2_hit",
        "tp2_time",

        "tp3_hit",
        "tp3_time",

        "max_profit_lock_level",
        "candles_in_trade",

        "close_time",
        "close_price",
        "close_reason",
        "rr",
        "result_percent",
        "balance_before",
        "balance_after",
    ]

    NUMERIC_FIELDS = {
        "entry_price",
        "initial_stop_loss",
        "stop_loss",
        "tp1",
        "tp2",
        "tp3",
        "risk_percent",
        "score",
        "max_profit_lock_level",
        "candles_in_trade",
        "close_price",
        "rr",
        "result_percent",
        "balance_before",
        "balance_after",
    }

    BOOLEAN_FIELDS = {
        "breakeven_active",
        "tp1_hit",
        "tp2_hit",
        "tp3_hit",
    }

    def __init__(
        self,
        h4,
        h1,
        m15,
        strategy_settings: dict,
        backtest_settings: dict,
    ):
        self.h4 = h4
        self.h1 = h1
        self.m15 = m15

        self.strategy_settings = strategy_settings
        self.backtest_settings = backtest_settings

        self.initial_balance = backtest_settings["initial_balance"]
        self.balance = self.initial_balance

        self.open_trade = None

        self.equity_curve = [self.balance]
        self.max_drawdown = 0

        self.blocked_by_liquidity = 0
        self.blocked_by_stop_distance = 0
        self.blocked_by_max_score = 0

        self.trade_count = 0
        self._trades_cache = None

        self.results_dir = Path(__file__).resolve().parent.parent / "results"
        self.trades_file_path = self.results_dir / "trades.csv"

        self._init_trades_csv()

    @property
    def trades(self):
        """
        Совместимость с main.py.

        Во время теста сделки не хранятся в памяти.
        Если main.py после теста обращается к backtester.trades,
        данные будут прочитаны из CSV.
        """
        if self._trades_cache is None:
            self._trades_cache = self._load_trades_from_csv()

        return self._trades_cache

    def _init_trades_csv(self):
        self.results_dir.mkdir(exist_ok=True)

        with open(
            self.trades_file_path,
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as csvfile:
            writer = csv.DictWriter(
                csvfile,
                fieldnames=self.TRADE_FIELDNAMES,
            )
            writer.writeheader()

        print(f"Trades CSV initialized: {self.trades_file_path}")

    def _append_trade_to_csv(self, trade: dict):
        row = {}

        for field in self.TRADE_FIELDNAMES:
            row[field] = trade.get(field, "")

        with open(
            self.trades_file_path,
            "a",
            newline="",
            encoding="utf-8-sig",
        ) as csvfile:
            writer = csv.DictWriter(
                csvfile,
                fieldnames=self.TRADE_FIELDNAMES,
            )
            writer.writerow(row)

        self.trade_count += 1

    def _load_trades_from_csv(self):
        if not self.trades_file_path.exists():
            return []

        trades = []

        with open(
            self.trades_file_path,
            "r",
            newline="",
            encoding="utf-8-sig",
        ) as csvfile:
            reader = csv.DictReader(csvfile)

            for row in reader:
                trade = {}

                for key, value in row.items():
                    if value == "":
                        trade[key] = None
                        continue

                    if key in self.NUMERIC_FIELDS:
                        try:
                            if key in {"score", "max_profit_lock_level", "candles_in_trade"}:
                                trade[key] = int(float(value))
                            else:
                                trade[key] = float(value)
                        except ValueError:
                            trade[key] = value
                        continue

                    if key in self.BOOLEAN_FIELDS:
                        trade[key] = value == "True"
                        continue

                    trade[key] = value

                trades.append(trade)

        return trades

    def run(self):
        print("\nBACKTEST STARTED\n")

        for i in range(300, len(self.m15)):
            current_m15 = self.m15.iloc[i]
            current_time = current_m15["time"]

            h4_past = self.h4[self.h4["time"] < current_time]
            h1_past = self.h1[self.h1["time"] < current_time]
            m15_past = self.m15.iloc[:i]

            if len(h4_past) < 250:
                continue

            if len(h1_past) < 250:
                continue

            if len(m15_past) < 250:
                continue

            if self.open_trade is not None:
                self.manage_trade(
                    candle=current_m15,
                    m15_past=m15_past,
                )
                continue

            signal = generate_signal(
                h4=h4_past,
                h1=h1_past,
                m15=m15_past,
                settings=self.strategy_settings,
            )

            if signal.action == SignalAction.WAIT:
                continue

            # Experimental max score filter
            if signal.score > 90:
                self.blocked_by_max_score += 1
                continue

            liquidity = analyze_liquidity(
                df=h1_past,
                lookback=150,
            )

            if self._liquidity_filter_blocks_signal(
                signal=signal,
                liquidity=liquidity,
                h1_past=h1_past,
            ):
                self.blocked_by_liquidity += 1
                continue

            if self._stop_distance_filter_blocks_signal(
                signal=signal,
                h1_past=h1_past,
            ):
                self.blocked_by_stop_distance += 1
                continue

            self.open_position(
                signal=signal,
                current_time=current_time,
                liquidity=liquidity,
            )

        if self.open_trade is not None:
            last_candle = self.m15.iloc[-1]

            self.close_trade(
                close_price=last_candle["close"],
                reason="END OF BACKTEST",
                candle=last_candle,
            )

        print("\nBACKTEST FINISHED\n")
        print(f"Blocked by liquidity filter: {self.blocked_by_liquidity}")
        print(f"Blocked by stop distance filter: {self.blocked_by_stop_distance}")
        print(f"Blocked by max score filter: {self.blocked_by_max_score}")
        print(f"Trades exported: {self.trade_count}")
        print(f"Trades CSV path: {self.trades_file_path}")

    def _liquidity_filter_blocks_signal(
        self,
        signal,
        liquidity,
        h1_past,
    ) -> bool:
        if liquidity is None:
            return False

        current_price = float(signal.entry_price)
        atr = float(h1_past["atr"].iloc[-1])

        max_distance_atr = 0.5
        max_distance = atr * max_distance_atr

        if signal.action == SignalAction.SELL:
            level = liquidity.nearest_low_below

            if level is None:
                return False

            distance = current_price - level.zone_high

            if distance < 0:
                return False

            if distance <= max_distance:
                print("=" * 50)
                print("LIQUIDITY FILTER BLOCKED SELL")
                print(f"entry: {current_price}")
                print(f"nearest_low_below: {format_liquidity_level(level)}")
                print(f"distance: {distance:.2f}")
                print(f"max allowed: {max_distance:.2f}")
                return True

        if signal.action == SignalAction.BUY:
            level = liquidity.nearest_high_above

            if level is None:
                return False

            distance = level.zone_low - current_price

            if distance < 0:
                return False

            if distance <= max_distance:
                print("=" * 50)
                print("LIQUIDITY FILTER BLOCKED BUY")
                print(f"entry: {current_price}")
                print(f"nearest_high_above: {format_liquidity_level(level)}")
                print(f"distance: {distance:.2f}")
                print(f"max allowed: {max_distance:.2f}")
                return True

        return False

    def _stop_distance_filter_blocks_signal(
            self,
            signal,
            h1_past,
    ) -> bool:
        entry_price = float(signal.entry_price)
        stop_loss = float(signal.stop_loss)
        atr = float(h1_past["atr"].iloc[-1])

        stop_distance = abs(entry_price - stop_loss)

        min_stop_atr = 0
        min_stop_distance = atr * min_stop_atr

        if stop_distance < min_stop_distance:
            print("=" * 50)
            print("STOP DISTANCE FILTER BLOCKED TRADE")
            print(f"direction: {signal.action.value}")
            print(f"entry: {entry_price}")
            print(f"stop_loss: {stop_loss}")
            print(f"stop_distance: {stop_distance:.2f}")
            print(f"min_stop_distance: {min_stop_distance:.2f}")
            print(f"atr: {atr:.2f}")
            return True

        max_stop_atr = 2.0
        max_stop_distance = atr * max_stop_atr

        if stop_distance > max_stop_distance:
            print("=" * 50)
            print("STOP DISTANCE FILTER BLOCKED TRADE - TOO FAR")
            print(f"direction: {signal.action.value}")
            print(f"entry: {entry_price}")
            print(f"stop_loss: {stop_loss}")
            print(f"stop_distance: {stop_distance:.2f}")
            print(f"max_stop_distance: {max_stop_distance:.2f}")
            print(f"atr: {atr:.2f}")
            print(f"stop/atr: {stop_distance / atr:.2f}")
            return True

        return False

    def open_position(
        self,
        signal,
        current_time,
        liquidity=None,
    ):
        direction = signal.action.value
        entry_price = float(signal.entry_price)
        stop_loss = float(signal.stop_loss)

        if not self._is_valid_signal(
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
        ):
            return

        risk = abs(entry_price - stop_loss)

        tp_settings = self.strategy_settings.get("tp", {})

        tp1_rr = tp_settings.get("tp1_rr", 1.0)
        tp2_rr = tp_settings.get("tp2_rr", 2.0)
        tp3_rr = tp_settings.get("tp3_rr", 3.0)

        if direction == "BUY":
            tp1 = entry_price + risk * tp1_rr
            tp2 = entry_price + risk * tp2_rr
            tp3 = entry_price + risk * tp3_rr
        else:
            tp1 = entry_price - risk * tp1_rr
            tp2 = entry_price - risk * tp2_rr
            tp3 = entry_price - risk * tp3_rr

        if liquidity:
            liquidity_info = describe_liquidity(liquidity)
        else:
            liquidity_info = {
                "nearest_high_above": "None",
                "nearest_high_below": "None",
                "nearest_low_above": "None",
                "nearest_low_below": "None",
            }

        self.open_trade = {
            "direction": direction,
            "open_time": current_time,
            "entry_price": entry_price,
            "initial_stop_loss": stop_loss,
            "stop_loss": stop_loss,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "risk_percent": self.backtest_settings["risk_percent"],
            "score": signal.score,
            "reasons": signal.reasons,

            "nearest_high_above": liquidity_info["nearest_high_above"],
            "nearest_high_below": liquidity_info["nearest_high_below"],
            "nearest_low_above": liquidity_info["nearest_low_above"],
            "nearest_low_below": liquidity_info["nearest_low_below"],

            "breakeven_active": False,
            "breakeven_time": None,

            "tp1_hit": False,
            "tp1_time": None,

            "tp2_hit": False,
            "tp2_time": None,

            "tp3_hit": False,
            "tp3_time": None,

            "max_profit_lock_level": 0,
            "candles_in_trade": 0,
        }

        print("=" * 50)
        print("OPEN TRADE")
        print(f"time: {current_time}")
        print(f"direction: {direction}")
        print(f"entry: {entry_price}")
        print(f"sl: {stop_loss}")
        print(f"tp1: {tp1}")
        print(f"tp2: {tp2}")
        print(f"tp3: {tp3}")
        print(f"score: {signal.score}")
        print(f"nearest_high_above: {liquidity_info['nearest_high_above']}")
        print(f"nearest_high_below: {liquidity_info['nearest_high_below']}")
        print(f"nearest_low_above: {liquidity_info['nearest_low_above']}")
        print(f"nearest_low_below: {liquidity_info['nearest_low_below']}")

    def _is_valid_signal(
        self,
        direction: str,
        entry_price: float,
        stop_loss: float,
    ) -> bool:
        if entry_price <= 0:
            return False

        if stop_loss <= 0:
            return False

        if direction == "BUY" and stop_loss >= entry_price:
            return False

        if direction == "SELL" and stop_loss <= entry_price:
            return False

        risk = abs(entry_price - stop_loss)

        if risk <= 0:
            return False

        return True

    def manage_trade(
        self,
        candle,
        m15_past,
    ):
        if self.open_trade is None:
            return

        trade = self.open_trade
        trade["candles_in_trade"] += 1

        direction = trade["direction"]

        high = candle["high"]
        low = candle["low"]
        close = candle["close"]

        stop_loss = trade["stop_loss"]
        tp1 = trade["tp1"]
        tp2 = trade["tp2"]
        tp3 = trade["tp3"]

        if direction == "BUY":
            if low <= stop_loss:
                self.close_trade(
                    close_price=stop_loss,
                    reason=self._get_stop_close_reason(trade),
                    candle=candle,
                )
                return

            if high >= tp1 and not trade["tp1_hit"]:
                breakeven_offset = self.backtest_settings.get("breakeven_offset", 0)
                trade["stop_loss"] = trade["entry_price"] + breakeven_offset
                trade["breakeven_active"] = True
                trade["breakeven_time"] = candle["time"]
                trade["tp1_hit"] = True
                trade["tp1_time"] = candle["time"]
                trade["max_profit_lock_level"] = max(trade["max_profit_lock_level"], 0)

                print("=" * 50)
                print("TP1 HIT")
                print(f"time: {candle['time']}")
                print(f"direction: {direction}")
                print("SL moved to ENTRY")

            if high >= tp2 and not trade["tp2_hit"]:
                trade["stop_loss"] = tp1
                trade["tp2_hit"] = True
                trade["tp2_time"] = candle["time"]
                trade["max_profit_lock_level"] = max(trade["max_profit_lock_level"], 1)

                print("=" * 50)
                print("TP2 HIT")
                print(f"time: {candle['time']}")
                print(f"direction: {direction}")
                print("SL moved to TP1")

            if high >= tp3 and not trade["tp3_hit"]:
                trade["stop_loss"] = tp2
                trade["tp3_hit"] = True
                trade["tp3_time"] = candle["time"]
                trade["max_profit_lock_level"] = max(trade["max_profit_lock_level"], 2)

                print("=" * 50)
                print("TP3 HIT")
                print(f"time: {candle['time']}")
                print(f"direction: {direction}")
                print("SL moved to TP2")

            if should_exit_trade(
                direction=direction,
                m15=m15_past,
                candles_in_trade=trade["candles_in_trade"],
                breakeven_active=trade["breakeven_active"],
            ):
                self.close_trade(
                    close_price=close,
                    reason="EXIT SIGNAL",
                    candle=candle,
                )
                return

        if direction == "SELL":
            if high >= stop_loss:
                self.close_trade(
                    close_price=stop_loss,
                    reason=self._get_stop_close_reason(trade),
                    candle=candle,
                )
                return

            if low <= tp1 and not trade["tp1_hit"]:
                breakeven_offset = self.backtest_settings.get("breakeven_offset", 0)
                trade["stop_loss"] = trade["entry_price"] - breakeven_offset
                trade["breakeven_active"] = True
                trade["breakeven_time"] = candle["time"]
                trade["tp1_hit"] = True
                trade["tp1_time"] = candle["time"]
                trade["max_profit_lock_level"] = max(trade["max_profit_lock_level"], 0)

                print("=" * 50)
                print("TP1 HIT")
                print(f"time: {candle['time']}")
                print(f"direction: {direction}")
                print("SL moved to ENTRY")

            if low <= tp2 and not trade["tp2_hit"]:
                trade["stop_loss"] = tp1
                trade["tp2_hit"] = True
                trade["tp2_time"] = candle["time"]
                trade["max_profit_lock_level"] = max(trade["max_profit_lock_level"], 1)

                print("=" * 50)
                print("TP2 HIT")
                print(f"time: {candle['time']}")
                print(f"direction: {direction}")
                print("SL moved to TP1")

            if low <= tp3 and not trade["tp3_hit"]:
                trade["stop_loss"] = tp2
                trade["tp3_hit"] = True
                trade["tp3_time"] = candle["time"]
                trade["max_profit_lock_level"] = max(trade["max_profit_lock_level"], 2)

                print("=" * 50)
                print("TP3 HIT")
                print(f"time: {candle['time']}")
                print(f"direction: {direction}")
                print("SL moved to TP2")

            if should_exit_trade(
                direction=direction,
                m15=m15_past,
                candles_in_trade=trade["candles_in_trade"],
                breakeven_active=trade["breakeven_active"],
            ):
                self.close_trade(
                    close_price=close,
                    reason="EXIT SIGNAL",
                    candle=candle,
                )
                return

    def _get_stop_close_reason(
        self,
        trade,
    ) -> str:
        if trade["max_profit_lock_level"] >= 2:
            return "PROFIT LOCK TP2"

        if trade["max_profit_lock_level"] >= 1:
            return "PROFIT LOCK TP1"

        if trade["breakeven_active"]:
            return "BREAKEVEN"

        return "STOP LOSS"

    def close_trade(
        self,
        close_price,
        reason,
        candle,
    ):
        trade = self.open_trade

        rr = calculate_rr(
            direction=trade["direction"],
            entry_price=trade["entry_price"],
            close_price=close_price,
            stop_loss=trade["initial_stop_loss"],
        )

        result_percent = calculate_result_percent(
            rr=rr,
            risk_percent=trade["risk_percent"],
        )

        old_balance = self.balance
        self.balance *= 1 + result_percent / 100

        self.equity_curve.append(self.balance)

        peak_balance = max(self.equity_curve)
        drawdown = ((peak_balance - self.balance) / peak_balance) * 100

        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown

        trade["close_time"] = candle["time"]
        trade["close_price"] = close_price
        trade["close_reason"] = reason
        trade["rr"] = rr
        trade["result_percent"] = result_percent
        trade["balance_before"] = old_balance
        trade["balance_after"] = self.balance

        self._append_trade_to_csv(trade)

        if result_percent > 0:
            print("\nПРИБЫЛЬ:")
        elif result_percent < 0:
            print("\nУБЫТОК:")
        else:
            print("\nБЕЗУБЫТОК:")

        print(trade["close_time"])
        print(trade["direction"])
        print(f"open={trade['entry_price']:.2f}")
        print(f"close={close_price:.2f}")
        print(f"RR={rr:.2f}")

        if result_percent > 0:
            print(f"profit=+{result_percent:.2f}%")
        elif result_percent < 0:
            print(f"loss={result_percent:.2f}%")
        else:
            print("result=0.00%")

        print(f"balance={self.balance:.2f}")
        print(f"reason={reason}")

        self.open_trade = None