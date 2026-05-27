import json
from pathlib import Path

from app.backtester import Backtester
from app.data_loader import (
    load_json_data,
    filter_date_range,
)
from app.indicators import add_indicators
from app.report import print_report, export_equity_curve


BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
CONFIG_DIR = BASE_DIR / "config"


def load_config(file_name: str) -> dict:
    with open(CONFIG_DIR / file_name, "r", encoding="utf-8") as file:
        return json.load(file)


def main() -> None:
    print("LOADING CONFIGS...")

    strategy_settings = load_config("strategy_settings.json")
    backtest_settings = load_config("backtest_settings.json")

    initial_balance = float(backtest_settings["initial_balance"])

    print("LOADING DATA...")

    h4 = load_json_data(DATA_DIR / "XAUUSD_H4.json")
    h1 = load_json_data(DATA_DIR / "XAUUSD_H1.json")
    m15 = load_json_data(DATA_DIR / "XAUUSD_M15.json")

    print("FILTERING DATE RANGE...")

    h4 = filter_date_range(
        h4,
        backtest_settings["start_date"],
        backtest_settings["end_date"],
    )

    h1 = filter_date_range(
        h1,
        backtest_settings["start_date"],
        backtest_settings["end_date"],
    )

    m15 = filter_date_range(
        m15,
        backtest_settings["start_date"],
        backtest_settings["end_date"],
    )

    print("CALCULATING INDICATORS...")

    h4 = add_indicators(h4, strategy_settings)
    h1 = add_indicators(h1, strategy_settings)
    m15 = add_indicators(m15, strategy_settings)

    print("\nDATA READY")
    print(f"H4 candles: {len(h4)}")
    print(f"H1 candles: {len(h1)}")
    print(f"M15 candles: {len(m15)}")

    backtester = Backtester(
        h4=h4,
        h1=h1,
        m15=m15,
        strategy_settings=strategy_settings,
        backtest_settings=backtest_settings,
    )

    backtester.run()
    print_report(
        trades=backtester.trades,
        initial_balance=initial_balance,
        final_balance=backtester.balance,
        max_drawdown=backtester.max_drawdown,
    )

    export_equity_curve(
        getattr(backtester, "equity_curve", [])
    )


if __name__ == "__main__":
    main()