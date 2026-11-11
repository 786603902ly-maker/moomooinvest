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
from zoneinfo import ZoneInfo

from common import load_rules, load_state, load_stocks, save_state
from engine import evaluate_custom_targets, evaluate_sell_targets, evaluate_stock
from fetch_prices import get_history
from indicators import moving_averages, recent_low, trend_signals

MA_WINDOWS = [60, 100, 150, 200, 250]


def pct_diff(price: float, ref: float | None) -> float | None:
    """Upside (positive) or downside (negative) from the current price to
    a reference (target/fair value), e.g. price 360 vs fair value 650 is
    +80.6% -- 80.6% upside if it reaches fair value."""
    if ref is None or price == 0:
        return None
    return round((ref - price) / price * 100, 2)


def intraday_snapshot(prev: dict | None) -> tuple[dt.date, float] | None:
    """(New York trade date, price) of the last intraday snapshot, if any."""
    prev = prev or {}
    at, price = prev.get("intraday_price_at"), prev.get("intraday_price")
    if not at or price is None:
        return None
    try:
        ts = dt.datetime.fromisoformat(at)
    except ValueError:
        return None
    return ts.astimezone(ZoneInfo("America/New_York")).date(), float(price)


def fair_value_sell_target(stock: dict, rules: dict) -> dict | None:
    """The standing "price is well above fair value, trim" alert.

    User's rule (2026-11-11): for T1-T3.5, once price is more than
    premium_pct above the stock's fair value, sell 1/5. Built as an ordinary
    sell target, so it behaves like the hand-written ones: fires at or above
    its level, once, and never resets on a period boundary. Its level comes
    from fair_value, so updating fair_value in stocks.yaml gives it a new id
    and re-arms it.
    """
    cfg = rules.get("fair_value_sell") or {}
    fair = stock.get("fair_value")
    if not cfg.get("enabled") or fair is None or stock.get("tier") not in (cfg.get("tiers") or []):
        return None
    premium = float(cfg.get("premium_pct", 30))
    return {
        "level": round(float(fair) * (1 + premium / 100), 2),
        # Not the user's own wording, so it carries its reason with it.
        "action": f'{cfg.get("action", "sell 1/5")} ({premium:g}% above fair value {float(fair):g})',
    }


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
            overrides=stock.get("ladder") or {},
            trend=trend_signals(history, rules.get("trend_guard") or {}),
            is_etf=bool(stock.get("is_etf")),
            recent_low=recent_low(
                history,
                int((rules.get("low_zone") or {}).get("lookback", 20)),
                intraday_snapshot(prev_stocks.get(ticker)),
            ),
        )
        result["ticker"] = ticker
        result["name"] = stock.get("name", ticker)
        result["is_etf"] = bool(stock.get("is_etf"))
        result["error"] = err  # None on a clean fetch, else "used cached data" style note
        result["data_stale"] = bool(err)

        custom_result = evaluate_custom_targets(
            price=price,
            price_date=price_date,
            custom_targets_cfg=stock.get("custom_targets") or [],
            default_amount=base_amount,
            prev_fired_custom=(prev_stocks.get(ticker) or {}).get("fired_custom"),
        )
        result.update(custom_result)
        if custom_result.get("new_triggers_custom_today"):
            names = ", ".join(f"{t['source']} @ {t['level']}" for t in custom_result["new_triggers_custom_today"])
            print(f"[{ticker}] NEW CUSTOM TARGET HIT: {names}")

        sell_result = evaluate_sell_targets(
            price=price,
            price_date=price_date,
            sell_targets_cfg=(stock.get("sell_targets") or [])
            + [t for t in [fair_value_sell_target(stock, rules)] if t],
            prev_fired_sell=(prev_stocks.get(ticker) or {}).get("fired_sell"),
        )
        result.update(sell_result)
        if sell_result.get("new_triggers_sell_today"):
            names = ", ".join(f"{t['source']} @ {t['level']}" for t in sell_result["new_triggers_sell_today"])
            print(f"[{ticker}] SELL TARGET REACHED: {names}")

        if not stock.get("is_etf"):
            result["target_price"] = stock.get("target_price")
            result["fair_value"] = stock.get("fair_value")
            result["vs_target_pct"] = pct_diff(price, stock.get("target_price"))
            result["vs_fair_value_pct"] = pct_diff(price, stock.get("fair_value"))

        out_stocks[ticker] = result
        if result.get("new_triggers_today"):
            names = ", ".join(f"{t['source']} x{t['multiplier']}" for t in result["new_triggers_today"])
            print(f"[{ticker}] NEW TRIGGER: {names}")
        guard = result.get("trend_guard") or {}
        new_period = ((prev_stocks.get(ticker) or {}).get("period") or {}).get("key") != result["period"]["key"]
        if guard.get("active") and new_period:
            print(f"[{ticker}] DOWNTREND GUARD: ladder starts at {guard['ceiling']} "
                  f"({guard['drop_step_pct']:g}% below {guard['anchor']}, {guard['anchor_source']})")

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
