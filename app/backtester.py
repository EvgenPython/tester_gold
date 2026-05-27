import csv
from pathlib import Path

from app.models import SignalAction
from app.strategy import generate_signal, should_exit_trade
from app.risk import (
    calculate_rr,
    calculate_result_percent,
)


class Backtester:
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

        self.trades = []
        self.open_trade = None

        self.equity_curve = [self.balance]
        self.max_drawdown = 0

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

            self.open_position(
                signal=signal,
                current_time=current_time,
            )

        if self.open_trade is not None:
            last_candle = self.m15.iloc[-1]

            self.close_trade(
                close_price=last_candle["close"],
                reason="END OF BACKTEST",
                candle=last_candle,
            )

        print("\nBACKTEST FINISHED\n")

        self.export_trades_csv()

    def open_position(
        self,
        signal,
        current_time,
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

        if direction == "BUY":
            tp1 = entry_price + risk
            tp2 = entry_price + risk * 2
        else:
            tp1 = entry_price - risk
            tp2 = entry_price - risk * 2

        self.open_trade = {
            "direction": direction,
            "open_time": current_time,
            "entry_price": entry_price,
            "initial_stop_loss": stop_loss,
            "stop_loss": stop_loss,
            "tp1": tp1,
            "tp2": tp2,
            "risk_percent": self.backtest_settings["risk_percent"],
            "score": signal.score,
            "reasons": signal.reasons,
            "breakeven_active": False,
            "breakeven_time": None,
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
        print(f"score: {signal.score}")

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

        if direction == "BUY":
            if low <= stop_loss:
                self.close_trade(
                    close_price=stop_loss,
                    reason="BREAKEVEN" if trade["breakeven_active"] else "STOP LOSS",
                    candle=candle,
                )
                return

            if high >= tp1 and not trade["breakeven_active"]:
                trade["stop_loss"] = trade["entry_price"]
                trade["breakeven_active"] = True
                trade["breakeven_time"] = candle["time"]

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

            if high >= tp2:
                self.close_trade(
                    close_price=tp2,
                    reason="TP2",
                    candle=candle,
                )
                return

        if direction == "SELL":
            if high >= stop_loss:
                self.close_trade(
                    close_price=stop_loss,
                    reason="BREAKEVEN" if trade["breakeven_active"] else "STOP LOSS",
                    candle=candle,
                )
                return

            if low <= tp1 and not trade["breakeven_active"]:
                trade["stop_loss"] = trade["entry_price"]
                trade["breakeven_active"] = True
                trade["breakeven_time"] = candle["time"]

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

            if low <= tp2:
                self.close_trade(
                    close_price=tp2,
                    reason="TP2",
                    candle=candle,
                )
                return

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

        self.trades.append(trade)

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

    def export_trades_csv(self):
        results_dir = Path("results")
        results_dir.mkdir(exist_ok=True)

        file_path = results_dir / "trades.csv"

        if not self.trades:
            return

        fieldnames = list(self.trades[0].keys())

        with open(
            file_path,
            "w",
            newline="",
            encoding="utf-8",
        ) as csvfile:
            writer = csv.DictWriter(
                csvfile,
                fieldnames=fieldnames,
            )

            writer.writeheader()

            for trade in self.trades:
                writer.writerow(trade)

        print(f"\nTrades exported: {file_path}")