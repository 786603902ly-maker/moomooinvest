"""Moving-average helpers."""
import datetime as dt


def moving_averages(history: list[tuple[dt.date, float]], windows: list[int]) -> dict:
    """history: ascending (date, close) list. Returns {window: value or None}."""
    closes = [c for _, c in history]
    out = {}
    for w in windows:
        if len(closes) < w:
            out[str(w)] = None
        else:
            out[str(w)] = sum(closes[-w:]) / w
    return out


def trend_signals(history: list[tuple[dt.date, float]], cfg: dict) -> dict | None:
    """Classify the trend from closing prices, for the downtrend guard.

    Downtrend means all three at once:
      - price below the long MA (MA200): the move has broken the support a
        DCA plan leans on hardest, not just pulled back inside an uptrend;
      - price below the short MA (MA60): still falling now, not already
        bouncing back above it;
      - the short MA itself falling by more than `slope_threshold_pct` over
        `slope_lookback` sessions: a sustained decline, not a one-week dip.
        A flatter MA60 reads as sideways, and sideways goes back to the
        normal rules.

    Any one of them failing ends the downtrend -- reclaiming MA60, MA60
    flattening out, or getting back above MA200 -- so the guard lets go as
    soon as the decline stops, not after a full recovery.
    Returns None when there isn't enough history to judge.
    """
    short_w = int(cfg.get("short_ma", 60))
    long_w = int(cfg.get("long_ma", 200))
    lookback = int(cfg.get("slope_lookback", 10))
    closes = [c for _, c in history]
    if len(closes) < max(long_w, short_w + lookback):
        return None
    price = closes[-1]
    short_ma = sum(closes[-short_w:]) / short_w
    short_ma_then = sum(closes[-short_w - lookback:-lookback]) / short_w
    long_ma = sum(closes[-long_w:]) / long_w
    slope_pct = (short_ma / short_ma_then - 1) * 100
    below_long = price < long_ma
    below_short = price < short_ma
    falling = slope_pct < -float(cfg.get("slope_threshold_pct", 0.5))
    return {
        "downtrend": below_long and below_short and falling,
        "price": round(price, 4),
        "short_ma": short_w,
        "long_ma": long_w,
        "below_long_ma": below_long,
        "below_short_ma": below_short,
        "short_ma_slope_pct": round(slope_pct, 2),
        "slope_lookback": lookback,
        "short_ma_falling": falling,
    }
