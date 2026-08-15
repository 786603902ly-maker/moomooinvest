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
