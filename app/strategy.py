from app.models import Signal, SignalAction
from app.risk import calculate_tp
from app.structure import (
    get_market_structure,
    get_last_swing_low,
    get_last_swing_high,
)


def is_h4_bullish(h4) -> bool:
    return h4["ema_fast"].iloc[-1] > h4["ema_slow"].iloc[-1]


def is_h4_bearish(h4) -> bool:
    return h4["ema_fast"].iloc[-1] < h4["ema_slow"].iloc[-1]


def is_h1_bullish(h1) -> bool:
    return h1["ema_fast"].iloc[-1] > h1["ema_slow"].iloc[-1]


def is_h1_bearish(h1) -> bool:
    return h1["ema_fast"].iloc[-1] < h1["ema_slow"].iloc[-1]


def is_m15_buy_timing(m15) -> bool:
    candle = m15.iloc[-1]

    return (
        candle["close"] > candle["ema_fast"]
        and candle["macd"] > candle["macd_signal"]
    )


def is_m15_sell_timing(m15) -> bool:
    candle = m15.iloc[-1]

    return (
        candle["close"] < candle["ema_fast"]
        and candle["macd"] < candle["macd_signal"]
    )


def distance_filter_ok(
    m15,
    h1,
    multiplier: float,
) -> bool:
    current_price = m15["close"].iloc[-1]
    ema = m15["ema_fast"].iloc[-1]
    atr = h1["atr"].iloc[-1]

    distance = abs(current_price - ema)

    return distance <= atr * multiplier


def should_exit_trade(
    direction: str,
    m15,
    candles_in_trade: int,
    breakeven_active: bool,
) -> bool:
    """
    Exit logic.

    BUY:
    - close below EMA50
    - MACD bearish

    SELL:
    - close above EMA50
    - MACD bullish

    Protection:
    - do not exit too early
    - exit allowed only after breakeven OR after 3 closed M15 candles
    """

    if len(m15) < 3:
        return False

    if not breakeven_active and candles_in_trade < 3:
        return False

    candle = m15.iloc[-1]

    close_price = candle["close"]
    ema_fast = candle["ema_fast"]
    macd = candle["macd"]
    macd_signal = candle["macd_signal"]

    if direction == "BUY":
        return (
            close_price < ema_fast
            and macd < macd_signal
        )

    if direction == "SELL":
        return (
            close_price > ema_fast
            and macd > macd_signal
        )

    return False


def generate_signal(
    h4,
    h1,
    m15,
    settings: dict,
) -> Signal:
    buy_score = 0
    sell_score = 0

    buy_reasons = []
    sell_reasons = []

    scoring = settings["scoring"]

    # H4 context

    if is_h4_bullish(h4):
        buy_score += 20
        buy_reasons.append("H4 bullish context")

    if is_h4_bearish(h4):
        sell_score += 20
        sell_reasons.append("H4 bearish context")

    # H1 trend

    if is_h1_bullish(h1):
        buy_score += 30
        buy_reasons.append("H1 bullish trend")

    if is_h1_bearish(h1):
        sell_score += 30
        sell_reasons.append("H1 bearish trend")

    # H1 structure

    structure = get_market_structure(h1)

    if structure == "BULLISH":
        buy_score += 10
        buy_reasons.append("H1 bullish structure")

    if structure == "BEARISH":
        sell_score += 10
        sell_reasons.append("H1 bearish structure")

    # M15 timing

    if is_m15_buy_timing(m15):
        buy_score += 25
        buy_reasons.append("M15 bullish timing")

    if is_m15_sell_timing(m15):
        sell_score += 25
        sell_reasons.append("M15 bearish timing")

    # Distance filter

    if distance_filter_ok(
        m15,
        h1,
        settings["filters"]["distance_from_ema_atr_multiplier"],
    ):
        buy_score += 15
        sell_score += 15

        buy_reasons.append("Distance filter OK")
        sell_reasons.append("Distance filter OK")

    min_score = scoring["min_score"]

    # BUY

    if buy_score >= min_score and buy_score > sell_score:
        entry = float(m15["close"].iloc[-1])
        swing_low = get_last_swing_low(h1)

        if swing_low is None:
            return Signal(
                action=SignalAction.WAIT,
                score=buy_score,
                reasons=["No swing low"],
            )

        tp1 = calculate_tp(
            direction="BUY",
            entry_price=entry,
            stop_loss=swing_low,
            rr_multiplier=settings["tp"]["tp1_rr"],
        )

        tp2 = calculate_tp(
            direction="BUY",
            entry_price=entry,
            stop_loss=swing_low,
            rr_multiplier=settings["tp"]["tp2_rr"],
        )

        return Signal(
            action=SignalAction.BUY,
            score=buy_score,
            reasons=buy_reasons,
            entry_price=entry,
            stop_loss=swing_low,
            tp1=tp1,
            tp2=tp2,
        )

    # SELL

    if sell_score >= min_score and sell_score > buy_score:
        entry = float(m15["close"].iloc[-1])
        swing_high = get_last_swing_high(h1)

        if swing_high is None:
            return Signal(
                action=SignalAction.WAIT,
                score=sell_score,
                reasons=["No swing high"],
            )

        tp1 = calculate_tp(
            direction="SELL",
            entry_price=entry,
            stop_loss=swing_high,
            rr_multiplier=settings["tp"]["tp1_rr"],
        )

        tp2 = calculate_tp(
            direction="SELL",
            entry_price=entry,
            stop_loss=swing_high,
            rr_multiplier=settings["tp"]["tp2_rr"],
        )

        return Signal(
            action=SignalAction.SELL,
            score=sell_score,
            reasons=sell_reasons,
            entry_price=entry,
            stop_loss=swing_high,
            tp1=tp1,
            tp2=tp2,
        )

    return Signal(
        action=SignalAction.WAIT,
        score=max(buy_score, sell_score),
        reasons=[
            f"BUY score={buy_score}",
            f"SELL score={sell_score}",
        ],
    )