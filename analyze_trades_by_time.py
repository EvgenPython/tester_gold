import pandas as pd


TRADES_FILE = "results/trades.csv"


def detect_column(df, possible_names):
    for name in possible_names:
        if name in df.columns:
            return name
    return None


def add_session(hour: int) -> str:
    if 0 <= hour < 8:
        return "ASIA"
    if 8 <= hour < 18:
        return "LONDON_NY"
    return "EVENING"


def profit_factor(series: pd.Series) -> float:
    gross_profit = series[series > 0].sum()
    gross_loss = abs(series[series < 0].sum())

    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0

    return gross_profit / gross_loss


def main():
    df = pd.read_csv(TRADES_FILE)

    print("\nAVAILABLE COLUMNS")
    print("-" * 50)
    print(list(df.columns))

    time_col = detect_column(
        df,
        ["entry_time", "open_time", "time", "datetime", "date"]
    )

    direction_col = detect_column(
        df,
        ["direction", "side", "action", "type"]
    )

    result_col = detect_column(
        df,
        ["result_percent", "profit_percent", "pnl_percent", "rr", "result", "profit"]
    )

    if time_col is None:
        raise ValueError("Не нашел колонку времени входа. Нужна entry_time/open_time/time/datetime/date.")

    if direction_col is None:
        raise ValueError("Не нашел колонку направления. Нужна direction/side/action/type.")

    if result_col is None:
        raise ValueError("Не нашел колонку результата. Нужна result_percent/profit_percent/pnl_percent/rr/result/profit.")

    df[time_col] = pd.to_datetime(df[time_col])
    df["hour"] = df[time_col].dt.hour
    df["weekday"] = df[time_col].dt.day_name()
    df["session"] = df["hour"].apply(add_session)

    df[direction_col] = df[direction_col].astype(str).str.upper()
    df[result_col] = pd.to_numeric(df[result_col], errors="coerce")

    df = df.dropna(subset=[result_col])

    print("\nBY DIRECTION")
    print("-" * 50)
    print(
        df.groupby(direction_col)[result_col]
        .agg(
            trades="count",
            total_result="sum",
            avg_result="mean",
            median_result="median",
            wins=lambda x: (x > 0).sum(),
            losses=lambda x: (x < 0).sum(),
            breakevens=lambda x: (x == 0).sum(),
            profit_factor=profit_factor,
        )
        .round(4)
    )

    print("\nBY SESSION AND DIRECTION")
    print("-" * 50)
    print(
        df.groupby(["session", direction_col])[result_col]
        .agg(
            trades="count",
            total_result="sum",
            avg_result="mean",
            median_result="median",
            wins=lambda x: (x > 0).sum(),
            losses=lambda x: (x < 0).sum(),
            breakevens=lambda x: (x == 0).sum(),
            profit_factor=profit_factor,
        )
        .round(4)
    )

    print("\nBY HOUR AND DIRECTION")
    print("-" * 50)
    print(
        df.groupby(["hour", direction_col])[result_col]
        .agg(
            trades="count",
            total_result="sum",
            avg_result="mean",
            wins=lambda x: (x > 0).sum(),
            losses=lambda x: (x < 0).sum(),
            profit_factor=profit_factor,
        )
        .round(4)
    )

    print("\nSELL ONLY BY HOUR")
    print("-" * 50)
    sell_df = df[df[direction_col] == "SELL"]

    if sell_df.empty:
        print("SELL сделок нет.")
    else:
        print(
            sell_df.groupby("hour")[result_col]
            .agg(
                trades="count",
                total_result="sum",
                avg_result="mean",
                wins=lambda x: (x > 0).sum(),
                losses=lambda x: (x < 0).sum(),
                profit_factor=profit_factor,
            )
            .round(4)
        )

    print("\nSELL ONLY BY SESSION")
    print("-" * 50)

    if sell_df.empty:
        print("SELL сделок нет.")
    else:
        print(
            sell_df.groupby("session")[result_col]
            .agg(
                trades="count",
                total_result="sum",
                avg_result="mean",
                median_result="median",
                wins=lambda x: (x > 0).sum(),
                losses=lambda x: (x < 0).sum(),
                breakevens=lambda x: (x == 0).sum(),
                profit_factor=profit_factor,
            )
            .round(4)
        )


if __name__ == "__main__":
    main()