def calculate_tp(
    direction: str,
    entry_price: float,
    stop_loss: float,
    rr_multiplier: float,
) -> float:
    risk = abs(entry_price - stop_loss)

    if direction == "BUY":
        return entry_price + risk * rr_multiplier

    if direction == "SELL":
        return entry_price - risk * rr_multiplier

    raise ValueError(f"Unknown direction: {direction}")


def calculate_rr(
    direction: str,
    entry_price: float,
    close_price: float,
    stop_loss: float,
) -> float:
    risk = abs(entry_price - stop_loss)

    if risk == 0:
        return 0.0

    if direction == "BUY":
        return (close_price - entry_price) / risk

    if direction == "SELL":
        return (entry_price - close_price) / risk

    raise ValueError(f"Unknown direction: {direction}")


def calculate_result_percent(
    rr: float,
    risk_percent: float,
) -> float:
    return rr * risk_percent