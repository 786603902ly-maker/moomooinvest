#!/usr/bin/env python3
"""Daily entrypoint: fetch prices, compute MAs, evaluate the tier ladder for
every stock, and write data/state.json.

Run by .github/workflows/daily-price-check.yml (needs real internet access,
which the Claude sandbox that authored this repo does not have -- see
README.md). Safe to run more than once a day: re-evaluating with the same
day's data is a no-op against an unchanged period/ladder.
"""
import datetime as dt
import sys

from common import load_rules, load_state, load_stocks, save_state
from engine import evaluate_stock
from fetch_prices import get_history
from indicators import moving_averages

MA_WINDOWS = [60, 100, 150, 200, 250]


def pct_diff(price: float, ref: float | None) -> float | None:
    if ref is None or ref == 0:
        return None
    return round((price - ref) / ref * 100, 2)


def main() -> int:
    rules = load_rules()
    stocks = load_stocks()
    prev_state = load_state()
    prev_stocks = prev_state.get("stocks", {})

    out_stocks = {}
    any_error = False

    for stock in stocks:
        ticker = stock["ticker"]
        tier = stock["tier"]
        history, err = get_history(ticker)

        if not history:
            any_error = True
            out_stocks[ticker] = {
                **(prev_stocks.get(ticker, {})),
                "tier": tier,
                "error": err,
                "data_stale": True,
            }
            print(f"[{ticker}] ERROR: {err}", file=sys.stderr)
            continue

        price_date, price = history[-1]
        mas = moving_averages(history, MA_WINDOWS)
        base_amount = rules["tiers"][tier]["base_amount"]

        result = evaluate_stock(
            tier=tier,
            price=price,
            price_date=price_date,
            mas=mas,
            rules=rules,
            prev_stock_state=prev_stocks.get(ticker),
            base_amount=base_amount,
        )
        result["ticker"] = ticker
        result["name"] = stock.get("name", ticker)
        result["is_etf"] = bool(stock.get("is_etf"))
        result["error"] = err  # None on a clean fetch, else "used cached data" style note
        result["data_stale"] = bool(err)

        if not stock.get("is_etf"):
            result["target_price"] = stock.get("target_price")
            result["fair_value"] = stock.get("fair_value")
            result["vs_target_pct"] = pct_diff(price, stock.get("target_price"))
            result["vs_fair_value_pct"] = pct_diff(price, stock.get("fair_value"))

        out_stocks[ticker] = result
        if result.get("new_triggers_today"):
            names = ", ".join(f"{t['source']} x{t['multiplier']}" for t in result["new_triggers_today"])
            print(f"[{ticker}] NEW TRIGGER: {names}")

    state = {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "stocks": out_stocks,
    }
    save_state(state)
    print(f"Wrote state.json for {len(out_stocks)} stocks.")
    if any_error:
        print("Some tickers had fetch errors (see stderr above); state.json still written "
              "with best-available data.", file=sys.stderr)
    return 0 if out_stocks else 1


if __name__ == "__main__":
    sys.exit(main())
