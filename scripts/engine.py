"""Core DCA-alert rule engine.

See config/rules.yaml for the plain-English description of the ladder,
cluster-merge, and drop-cascade rules this implements.
"""
import datetime as dt

from common import period_key, period_start


def _sorted_ladder(ma_values: list[tuple[str, float]], step_multipliers: list[float]) -> list[dict]:
    """ma_values: [(source_label, value), ...] with non-None values only.
    Returns rungs sorted highest-value-first, each tagged with its multiplier.
    """
    ranked = sorted(ma_values, key=lambda pair: pair[1], reverse=True)
    rungs = []
    for i, (source, value) in enumerate(ranked):
        if i >= len(step_multipliers):
            break
        rungs.append(
            {
                "id": f"ma-{source}",
                "source": source,
                "level": round(value, 4),
                "multiplier": step_multipliers[i],
            }
        )
    return rungs


def _has_cluster(rungs: list[dict], cluster_merge_pct: float) -> bool:
    for a, b in zip(rungs, rungs[1:]):
        if a["level"] <= 0:
            continue
        gap_pct = (a["level"] - b["level"]) / a["level"] * 100
        if gap_pct < cluster_merge_pct:
            return True
    return False


def _cascade_ladder(top_value: float, n_rungs: int, step_multipliers: list[float], drop_step_pct: float) -> list[dict]:
    rungs = []
    level = top_value
    for i in range(n_rungs):
        rungs.append(
            {
                "id": f"drop-{i}",
                "source": f"{drop_step_pct:g}% cascade #{i + 1}",
                "level": round(level, 4),
                "multiplier": step_multipliers[i] if i < len(step_multipliers) else step_multipliers[-1],
            }
        )
        level = level * (1 - drop_step_pct / 100)
    return rungs


def build_period_ladder(tier_cfg: dict, mas: dict, rules: dict) -> tuple[list[dict], bool]:
    """Build the ladder snapshot for a fresh period. Returns (rungs, clustered)."""
    ma_periods = tier_cfg["ma_ladder"]
    step_multipliers = rules["step_multipliers"]
    available = [(str(p), mas[str(p)]) for p in ma_periods if mas.get(str(p)) is not None]
    if not available:
        return [], False

    rungs = _sorted_ladder(available, step_multipliers)
    clustered = _has_cluster(rungs, rules["cluster_merge_pct"])
    if clustered:
        top_value = rungs[0]["level"]
        rungs = _cascade_ladder(top_value, len(available), step_multipliers, rules["drop_step_pct"])
    return rungs, clustered


def extend_with_drop_cascade(base_rungs: list[dict], price: float, cap_multiplier: float, drop_step_pct: float) -> list[dict]:
    """Append synthetic 5%-drop rungs below the lowest base rung, as many as
    needed to cover the current price, each capped at cap_multiplier."""
    if not base_rungs:
        return base_rungs
    lowest = base_rungs[-1]["level"]
    extra = []
    level = lowest
    i = 0
    while price < level:
        level = level * (1 - drop_step_pct / 100)
        extra.append(
            {
                "id": f"below-ladder-drop-{i}",
                "source": f"{drop_step_pct:g}% below lowest rung, step {i + 1}",
                "level": round(level, 4),
                "multiplier": cap_multiplier,
            }
        )
        i += 1
        if i > 20:  # sanity guard against a runaway loop on bad data
            break
    return base_rungs + extra


def evaluate_stock(
    tier: str,
    price: float,
    price_date: dt.date,
    mas: dict,
    rules: dict,
    prev_stock_state: dict | None,
    base_amount: float,
) -> dict:
    tier_cfg = rules["tiers"][tier]
    refresh = tier_cfg["refresh"]
    pkey = period_key(refresh, price_date)
    pstart = period_start(refresh, price_date)

    prev_period = (prev_stock_state or {}).get("period", {})
    same_period = prev_period.get("key") == pkey

    if same_period and prev_stock_state.get("ladder"):
        ladder = prev_stock_state["ladder"]
        clustered = prev_stock_state.get("clustered", False)
        fired = list(prev_stock_state.get("fired_this_period", []))
    else:
        ladder, clustered = build_period_ladder(tier_cfg, mas, rules)
        fired = []

    full_ladder = extend_with_drop_cascade(ladder, price, rules["cap_multiplier"], rules["drop_step_pct"])

    fired_ids = {f["id"] for f in fired}
    new_triggers = []
    for rung in full_ladder:
        if price <= rung["level"] and rung["id"] not in fired_ids:
            trigger = {
                **rung,
                "amount": round(base_amount * rung["multiplier"], 2),
                "first_hit_date": price_date.isoformat(),
            }
            fired.append(trigger)
            new_triggers.append(trigger)
            fired_ids.add(rung["id"])

    next_rung = next((r for r in full_ladder if r["id"] not in {f["id"] for f in fired}), None)

    return {
        "tier": tier,
        "price": price,
        "price_date": price_date.isoformat(),
        "mas": mas,
        "period": {"type": refresh, "key": pkey, "start_date": pstart.isoformat()},
        "ladder": ladder,
        "clustered": clustered,
        "full_ladder_today": full_ladder,
        "fired_this_period": fired,
        "new_triggers_today": new_triggers,
        "next_rung": next_rung,
    }
