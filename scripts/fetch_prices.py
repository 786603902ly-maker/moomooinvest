"""Fetch daily close-price history for a ticker.

Runs on GitHub Actions (which has normal internet access) rather than in the
Claude sandbox, which blocks egress to arbitrary hosts. Tries stooq.com first
(simple CSV, no key, rarely rate-limited), falls back to Yahoo Finance's
public chart endpoint.

Caches the merged history to data/prices/<TICKER>.csv so re-runs are cheap
and so a transient fetch failure can fall back to the last known-good data
instead of crashing the whole pipeline.
"""
import csv
import datetime as dt
import io
import json
import urllib.request

from common import PRICES_DIR

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; moomooinvest-dca-bot/1.0)"}


class FetchError(Exception):
    pass


def _fetch_stooq(ticker: str) -> list[tuple[dt.date, float]]:
    url = f"https://stooq.com/q/d/l/?s={ticker.lower()}.us&i=d"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8")
    if "No data" in raw or not raw.strip():
        raise FetchError(f"stooq: no data for {ticker}")
    reader = csv.DictReader(io.StringIO(raw))
    out = []
    for row in reader:
        try:
            d = dt.datetime.strptime(row["Date"], "%Y-%m-%d").date()
            c = float(row["Close"])
        except (KeyError, ValueError):
            continue
        out.append((d, c))
    if not out:
        raise FetchError(f"stooq: parsed 0 rows for {ticker}")
    return sorted(out)


def _fetch_yahoo(ticker: str) -> list[tuple[dt.date, float]]:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{ticker}?range=2y&interval=1d"
    )
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.load(resp)
    result = payload["chart"]["result"][0]
    timestamps = result["timestamp"]
    closes = result["indicators"]["quote"][0]["close"]
    out = []
    for ts, c in zip(timestamps, closes):
        if c is None:
            continue
        d = dt.datetime.utcfromtimestamp(ts).date()
        out.append((d, float(c)))
    if not out:
        raise FetchError(f"yahoo: parsed 0 rows for {ticker}")
    return sorted(out)


def _cache_path(ticker: str):
    return PRICES_DIR / f"{ticker}.csv"


def _load_cache(ticker: str) -> list[tuple[dt.date, float]]:
    path = _cache_path(ticker)
    if not path.exists():
        return []
    out = []
    with open(path, "r") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) != 2:
                continue
            out.append((dt.date.fromisoformat(row[0]), float(row[1])))
    return sorted(out)


def _save_cache(ticker: str, history: list[tuple[dt.date, float]]) -> None:
    PRICES_DIR.mkdir(parents=True, exist_ok=True)
    with open(_cache_path(ticker), "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "close"])
        for d, c in history:
            writer.writerow([d.isoformat(), c])


def get_history(ticker: str) -> tuple[list[tuple[dt.date, float]], str | None]:
    """Return (history, error). history is sorted ascending by date.

    Falls back to the last cached copy (and reports the error) if every live
    source fails, so a bad network day degrades to "stale data" rather than
    a crash.
    """
    errors = []
    for fetcher, name in ((_fetch_stooq, "stooq"), (_fetch_yahoo, "yahoo")):
        try:
            history = fetcher(ticker)
            _save_cache(ticker, history)
            return history, None
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")
    cached = _load_cache(ticker)
    if cached:
        return cached, "live fetch failed (" + "; ".join(errors) + "), using cached data"
    return [], "live fetch failed (" + "; ".join(errors) + ") and no cached data available"
