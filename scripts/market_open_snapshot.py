#!/usr/bin/env python3
"""Live snapshot shortly after NYSE open, merged into data/state.json as
intraday_price / intraday_price_at on top of (not instead of) the daily
close-based price/ladder state that run_check.py owns.

Run by .github/workflows/market-open-price-check.yml, which fires on two
schedules 15 minutes after each of NYSE's two possible open times in
Singapore local time (9:30pm during EDT, 10:30pm during EST). Rather than
trust the cron schedule to pick the right one, this script re-derives "is it
actually ~15 minutes after today's open" from the real America/New_York
clock and no-ops otherwise -- so whichever of the two cron firings is wrong
for the current DST regime does nothing, and nobody has to hand-edit the
cron twice a year at the March/November DST flips.
"""
import datetime as dt
import sys
from zoneinfo import ZoneInfo

from common import load_state, load_stocks, save_state
from fetch_prices import get_intraday_quote

NY = ZoneInfo("America/New_York")
OPEN_TIME = dt.time(9, 30)
WINDOW_END = dt.time(9, 55)  # 25 min slack either side of the two cron firings


def in_open_window(now_ny: dt.datetime) -> bool:
    return now_ny.weekday() < 5 and OPEN_TIME <= now_ny.time() <= WINDOW_END


def main() -> int:
    now_ny = dt.datetime.now(NY)
    if not in_open_window(now_ny):
        print(f"Not within the post-open window (NY time {now_ny.strftime('%a %H:%M %Z')}); skipping.")
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
