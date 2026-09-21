#!/usr/bin/env python3
"""Live snapshot during the NYSE session, merged into data/state.json as
intraday_price / intraday_price_at on top of (not instead of) the daily
close-based price/ladder state that run_check.py owns.

Run by .github/workflows/market-open-price-check.yml, which aims at ~15
minutes after each of NYSE's two possible open times in Singapore local time
(9:30pm during EDT, 10:30pm during EST). The cron can't pick the right one
by itself, so this script re-derives from the real America/New_York clock
whether the market is actually open and no-ops otherwise -- the firing that
is wrong for the current DST regime does nothing, and nobody hand-edits the
cron at the March/November DST flips.

The accepted window is the whole session, not just the first 25 minutes.
GitHub runs these scheduled crons hours late under load -- measured at
3.5-5h for this repo through September 2026 -- and a window that only
accepted 09:30-09:55 ET meant every single firing landed outside it and
skipped, so no intraday_price was ever written. A quote from midday is
worth far more than no quote at all.
"""
import datetime as dt
import sys
from zoneinfo import ZoneInfo

from common import load_state, load_stocks, save_state
from fetch_prices import get_intraday_quote

NY = ZoneInfo("America/New_York")
OPEN_TIME = dt.time(9, 30)
CLOSE_TIME = dt.time(16, 0)


def in_session(now_ny: dt.datetime) -> bool:
    """Weekday, between the opening and closing bell in New York.

    Market holidays aren't tracked: on one the fetch simply returns the
    previous session's last tick, which is the same thing the dashboard
    would show anyway.
    """
    return now_ny.weekday() < 5 and OPEN_TIME <= now_ny.time() <= CLOSE_TIME


def main() -> int:
    now_ny = dt.datetime.now(NY)
    if not in_session(now_ny):
        print(f"Market is closed (NY time {now_ny.strftime('%a %H:%M %Z')}); skipping.")
        return 0

    stocks = load_stocks()
    state = load_state()
    stocks_state = state.setdefault("stocks", {})

    fetched = 0
    for stock in stocks:
        ticker = stock["ticker"]
        try:
            ts, price = get_intraday_quote(ticker)
        except Exception as exc:  # noqa: BLE001
            print(f"[{ticker}] intraday fetch failed: {exc}", file=sys.stderr)
            continue
        entry = stocks_state.setdefault(ticker, {})
        entry["intraday_price"] = price
        entry["intraday_price_at"] = ts.isoformat()
        fetched += 1

    if fetched:
        save_state(state)
        print(f"Wrote intraday snapshot for {fetched}/{len(stocks)} stocks (NY time {now_ny.strftime('%H:%M %Z')}).")
    else:
        print("No intraday quotes fetched; state.json left unchanged.", file=sys.stderr)
    return 0 if fetched else 1


if __name__ == "__main__":
    sys.exit(main())
