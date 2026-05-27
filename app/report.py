from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any


def _get(trade: dict[str, Any], key: str, default: Any = None) -> Any:
    return trade.get(key, default)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    return None


def export_equity_curve(
    equity_points: list,
    filename: str = "results/equity_curve.csv",
) -> None:
    if not equity_points:
        return

    output_path = Path(filename)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    first_item = equity_points[0]

    if isinstance(first_item, dict):
        fieldnames = list(first_item.keys())

        rows = equity_points
    else:
        fieldnames = ["index", "balance"]

        rows = [
            {
                "index": index,
                "balance": balance,
            }
            for index, balance in enumerate(equity_points, start=1)
        ]

    with open(output_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_report(
    trades: list[dict[str, Any]],
    initial_balance: float,
    final_balance: float,
    max_drawdown: float,
) -> None:
    total_trades = len(trades)

    wins = [
        t for t in trades
        if float(_get(t, "result_percent", 0)) > 0
    ]

    losses = [
        t for t in trades
        if float(_get(t, "result_percent", 0)) < 0
    ]

    breakevens = [
        t for t in trades
        if float(_get(t, "result_percent", 0)) == 0
    ]

    buy_trades = [
        t for t in trades
        if _get(t, "direction") == "BUY"
    ]

    sell_trades = [
        t for t in trades
        if _get(t, "direction") == "SELL"
    ]

    tp2_closes = [
        t for t in trades
        if _get(t, "close_reason") == "TP2"
    ]

    exit_closes = [
        t for t in trades
        if _get(t, "close_reason") == "EXIT SIGNAL"
    ]

    sl_closes = [
        t for t in trades
        if _get(t, "close_reason") == "STOP LOSS"
    ]

    be_closes = [
        t for t in trades
        if _get(t, "close_reason") == "BREAKEVEN"
    ]

    winrate = (
        (len(wins) / total_trades) * 100
        if total_trades
        else 0
    )

    rr_values = [
        float(_get(t, "rr", 0))
        for t in trades
    ]

    pnl_values = [
        float(_get(t, "result_percent", 0))
        for t in trades
    ]

    avg_rr = mean(rr_values) if rr_values else 0

    avg_win = mean([
        float(_get(t, "result_percent", 0))
        for t in wins
    ]) if wins else 0

    avg_loss = mean([
        float(_get(t, "result_percent", 0))
        for t in losses
    ]) if losses else 0

    median_win = median([
        float(_get(t, "result_percent", 0))
        for t in wins
    ]) if wins else 0

    median_loss = median([
        float(_get(t, "result_percent", 0))
        for t in losses
    ]) if losses else 0

    gross_profit = sum([
        float(_get(t, "result_percent", 0))
        for t in wins
    ])

    gross_loss = abs(sum([
        float(_get(t, "result_percent", 0))
        for t in losses
    ]))

    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0
        else 0
    )

    expectancy = (
        (len(wins) / total_trades) * avg_win
        +
        (len(losses) / total_trades) * avg_loss
    ) if total_trades else 0

    total_result = (
        (final_balance - initial_balance)
        / initial_balance
    ) * 100

    best_trade = max(pnl_values, default=0)
    worst_trade = min(pnl_values, default=0)

    monthly_stats = defaultdict(float)

    for trade in trades:
        entry_time = _parse_datetime(
            _get(trade, "open_time")
        )

        if entry_time is None:
            continue

        month = entry_time.strftime("%Y-%m")

        monthly_stats[month] += float(
            _get(trade, "result_percent", 0)
        )

    print("\n" + "=" * 50)
    print("FINAL REPORT")
    print("=" * 50)

    print(f"Initial balance: {initial_balance:.2f}")
    print(f"Final balance: {final_balance:.2f}")

    print(f"Total trades: {total_trades}")

    print(f"Wins: {len(wins)}")
    print(f"Losses: {len(losses)}")
    print(f"Breakevens: {len(breakevens)}")

    print(f"BUY trades: {len(buy_trades)}")
    print(f"SELL trades: {len(sell_trades)}")

    print(f"TP2 closes: {len(tp2_closes)}")
    print(f"Exit signal closes: {len(exit_closes)}")
    print(f"Stop loss closes: {len(sl_closes)}")
    print(f"Breakeven closes: {len(be_closes)}")

    print(f"Winrate: {winrate:.2f}%")
    print(f"Average RR: {avg_rr:.2f}")

    print(f"Average winner: {avg_win:.2f}%")
    print(f"Average loser: {avg_loss:.2f}%")

    print(f"Median winner: {median_win:.2f}%")
    print(f"Median loser: {median_loss:.2f}%")

    print(f"Profit factor: {profit_factor:.2f}")
    print(f"Expectancy per trade: {expectancy:.2f}%")

    print(f"Total result: {total_result:.2f}%")
    print(f"Max drawdown: {max_drawdown:.2f}%")

    print(f"Best trade: {best_trade:.2f}%")
    print(f"Worst trade: {worst_trade:.2f}%")

    print("\nMONTHLY PERFORMANCE")
    print("-" * 50)

    for month, pnl in sorted(monthly_stats.items()):
        print(f"{month}: {pnl:.2f}%")