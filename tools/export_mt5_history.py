import json
from pathlib import Path
from datetime import datetime

import MetaTrader5 as mt5
import pandas as pd


SYMBOL = "GBPUSD"

TIMEFRAMES = {
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
}

START_DATE = datetime(2024, 1, 1)
END_DATE = datetime(2026, 6, 6)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

DATA_DIR.mkdir(exist_ok=True)


def export_timeframe(name: str, timeframe) -> None:
    print(f"\nEXPORTING {name}...")

    rates = mt5.copy_rates_range(
        SYMBOL,
        timeframe,
        START_DATE,
        END_DATE,
    )

    if rates is None:
        print(f"FAILED: {name}")
        return

    df = pd.DataFrame(rates)

    df["time"] = pd.to_datetime(
        df["time"],
        unit="s",
        utc=True,
    )

    records = []

    for _, row in df.iterrows():
        records.append(
            {
                "time": row["time"].strftime("%Y-%m-%d %H:%M:%S"),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["tick_volume"]),
            }
        )

    output_file = DATA_DIR / f"{SYMBOL}_{name}.json"

    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(
            records,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print(f"Saved: {output_file}")
    print(f"Candles: {len(records)}")


def main():
    print("CONNECTING TO MT5...")

    if not mt5.initialize():
        print("MT5 INIT FAILED")
        return

    print("MT5 CONNECTED")

    for tf_name, tf_value in TIMEFRAMES.items():
        export_timeframe(tf_name, tf_value)

    mt5.shutdown()

    print("\nEXPORT FINISHED")


if __name__ == "__main__":
    main()