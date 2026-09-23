"""Core DCA-alert rule engine.

See config/rules.yaml for the plain-English description of the ladder,
cluster-merge, and drop-cascade rules this implements.
"""
import datetime as dt

from common import period_key, period_start

# Label for a rung anchored at a price the user named rather than at an MA.
START_SOURCE = "your first buy level"


def _cluster_supports(ma_values: list[tuple[str, float]], cluster_merge_pct: float) -> list[dict]:
    """ma_values: [(source_label, value), ...] with non-None values only.

    Group MAs that sit within cluster_merge_pct of each other into a single
    "support level" (their average) -- two MAs a couple percent apart are
    read as the market agreeing on one support, not two separate rungs.
    Returns support levels sorted highest-first, each tagged with which MA
    period(s) it's made of.
    """
    ranked = sorted(ma_values, key=lambda pair: pair[1], reverse=True)
    groups: list[dict] = []
    for source, value in ranked:
        if groups:
            last = groups[-1]
            rep = sum(last["values"]) / len(last["values"])
            gap_pct = (rep - value) / rep * 100 if rep else 0
            if gap_pct < cluster_merge_pct:
                last["sources"].append(source)
                last["values"].append(value)
                continue
        groups.append({"sources": [source], "values": [value]})
    return [{"sources": g["sources"], "level": sum(g["values"]) / len(g["values"])} for g in groups]


def effective_drop_step(rules: dict, overrides: dict | None = None) -> float:
    """Per-stock `ladder.drop_step_pct`, falling back to the global default.

    The user's rule (see README "Your standing ladder preferences"): a stock
    in a clear downtrend at an already-low price should step down further
    between rungs -- 7% rather than the default 5% -- to pull the average
    cost down. It only ever widens a *synthetic* step: rung selection still
    takes whichever is lower of the next real MA support and the drop level,
    so an MA sitting below the 7% level stays the rung.
    """
    step = (overrides or {}).get("drop_step_pct")
    return float(step) if step is not None else float(rules["drop_step_pct"])


def ladder_config(tier_cfg: dict, rules: dict, overrides: dict | None = None) -> dict:
    """The inputs that decide a ladder's *shape*, as a comparable dict.

    Ladders are frozen for the length of a refresh period, so an edit to
    rules.yaml or to a stock's `ladder:` overrides would otherwise sit
    invisible until the period rolled over. evaluate_stock stores this
    alongside the ladder and rebuilds whenever it stops matching.
    """
    overrides = overrides or {}
    return {
        "ma_ladder": list(tier_cfg["ma_ladder"]),
        "step_multipliers": list(rules["step_multipliers"]),
        "cluster_merge_pct": rules["cluster_merge_pct"],
        "drop_step_pct": effective_drop_step(rules, overrides),
        "start_ma": overrides.get("start_ma"),
        "start_level": overrides.get("start_level"),
        "skip_top_rungs": int(overrides.get("skip_top_rungs") or 0),
    }


def build_period_ladder(
    tier_cfg: dict, mas: dict, rules: dict, overrides: dict | None = None
) -> tuple[list[dict], bool]:
    """Build the ladder snapshot for a fresh period. Returns (rungs, merged).

    Each rung is either a real support level (see _cluster_supports) or,
    when the next real support isn't at least drop_step_pct below the prior
    rung, a synthetic drop_step_pct-below-prior-rung level instead -- i.e.
    at every step we take whichever is LOWER of "next real support" and
    "prior rung minus drop_step_pct", so consecutive rungs are never too
    close together and each one is a genuine next support down, not a
    same-ish MA a percent or two away.

    Tiers configured with only a single MA period (T5/T9 -- deliberately
    single-trigger tiers, not a multi-rung ladder) are capped at exactly one
    rung here; any further downside for them still comes from the caller's
    separate extend_with_drop_cascade, dynamically, once price actually
    falls that far -- unlike multi-MA tiers, they don't get 2nd/3rd rungs
    pre-planned with escalating multipliers.

    `overrides` is the stock's optional `ladder:` block in stocks.yaml:

      drop_step_pct   widen (or narrow) this stock's synthetic step.
      start_ma        anchor the ladder at this MA period and ignore every
                      shallower one -- "start with ma250 directly", for a
                      stock whose MAs are bunched and whose price has
                      already fallen well past the shallow ones.
      start_level     anchor the ladder at this PRICE, ignoring every MA
                      support above it -- "don't start buying until 920".
                      Unlike start_ma this needn't coincide with any MA, so
                      it works when the level you want is nowhere near one.
      skip_top_rungs  build as usual, then discard the N shallowest rungs.
                      For the same intent when no MA sits low enough to
                      anchor on: the wanted level is a drop step or two
                      below the top MA, not an MA at all.

    Multipliers are assigned *after* skipping, so the surviving first rung
    is always x1 and the ladder still steps x1 -> x1.5 -> x2 below it.
    """
    tier_periods = tier_cfg["ma_ladder"]
    overrides = overrides or {}
    start_ma = overrides.get("start_ma")
    ma_periods = tier_periods
    if start_ma is not None:
        # Deeper = longer period. Falling back to the deepest configured MA
        # keeps a too-aggressive start_ma from emptying the ladder entirely.
        ma_periods = [p for p in tier_periods if p >= start_ma] or [max(tier_periods)]
    skip_top = int(overrides.get("skip_top_rungs") or 0)
    step_multipliers = rules["step_multipliers"]
    drop_step_pct = effective_drop_step(rules, overrides)
    cluster_pct = rules["cluster_merge_pct"]

    available = [(str(p), mas[str(p)]) for p in ma_periods if mas.get(str(p)) is not None]
    if not available:
        return [], False

    supports = _cluster_supports(available, cluster_pct)

    start_level = overrides.get("start_level")
    if start_level is not None:
        # Your own first buy price replaces rung 1 and suppresses every MA
        # above it; MAs below it still form the deeper rungs as usual.
        supports = [sup for sup in supports if sup["level"] < float(start_level)]
        supports.insert(0, {"sources": [START_SOURCE], "level": float(start_level)})

    merged = any(len(s["sources"]) > 1 and s["sources"] != [START_SOURCE] for s in supports)
    # Single-trigger tiers are decided by how the *tier* is configured, not
    # by what start_ma narrowed the list down to -- filtering T1 down to one
    # MA must still produce a full ladder below that MA.
    max_rungs = len(step_multipliers) if len(tier_periods) > 1 else 1

    levels: list[tuple[float, str]] = []
    idx = 0
    prev_level = None
    for _ in range(max_rungs + skip_top):
        while idx < len(supports) and prev_level is not None and supports[idx]["level"] >= prev_level:
            idx += 1  # already passed/merged into where we are -- irrelevant now
        support = supports[idx] if idx < len(supports) else None
        drop_level = prev_level * (1 - drop_step_pct / 100) if prev_level is not None else None

        if prev_level is None:
            level, source = support["level"], "+".join(support["sources"])
            idx += 1
        elif support is not None and (drop_level is None or support["level"] <= drop_level):
            level, source = support["level"], "+".join(support["sources"])
            idx += 1
        elif drop_level is not None:
            level, source = drop_level, f"{drop_step_pct:g}% drop"
        else:
            break

        levels.append((level, source))
        prev_level = level

    rungs: list[dict] = []
    for i, ((level, source), mult) in enumerate(zip(levels[skip_top:], step_multipliers)):
        if source == START_SOURCE:
            rung_id = "start-level"
        elif "drop" in source:
            rung_id = f"rung-drop-{i}"
        else:
            rung_id = f"ma-{source}"
        rungs.append(
            {
                "id": rung_id,
                "source": source,
                "level": round(level, 4),
                "multiplier": mult,
            }
        )

    return rungs, merged


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
                "source": f"{drop_step_pct:g}% drop #{i + 1}",
                "level": round(level, 4),
                "multiplier": cap_multiplier,
            }
        )
        i += 1
        if i > 20:  # sanity guard against a runaway loop on bad data
            break
    return base_rungs + extra


def _custom_rung_id(level: float, note: str | None) -> str:
    note_part = (note or "").strip().lower().replace(" ", "-")
    return f"custom-{round(float(level), 4)}-{note_part}" if note_part else f"custom-{round(float(level), 4)}"


def evaluate_custom_targets(
    price: float,
    price_date: dt.date,
    custom_targets_cfg: list[dict],
    default_amount: float,
    prev_fired_custom: list[dict] | None,
) -> dict:
    """User-set buy levels, layered on top of the MA ladder.

    Unlike the MA ladder, these do NOT reset each period -- once a level
    fires it stays fired until the user edits/removes that entry from
    config/stocks.yaml (which changes its id and makes it "new" again).
    Any previously-fired entry whose id no longer appears in the current
    config is dropped, so removing an entry cleans up its history too.
    """
    custom_targets_cfg = custom_targets_cfg or []
    current_ids = set()
    rungs = []
    for ct in custom_targets_cfg:
        level = ct.get("level")
        if level is None:
            continue
        rid = _custom_rung_id(level, ct.get("note"))
        current_ids.add(rid)
        rungs.append(
            {
                "id": rid,
                "source": ct.get("note") or "your target",
                "level": round(float(level), 4),
                "amount": round(float(ct.get("amount") or default_amount), 2),
                "note": ct.get("note"),
                "is_custom": True,
            }
        )
    rungs.sort(key=lambda r: r["level"], reverse=True)

    prev_fired_custom = prev_fired_custom or []
    fired = [f for f in prev_fired_custom if f["id"] in current_ids]
    fired_ids = {f["id"] for f in fired}

    new_triggers = []
    for rung in rungs:
        if price <= rung["level"] and rung["id"] not in fired_ids:
            trigger = {**rung, "first_hit_date": price_date.isoformat()}
            fired.append(trigger)
            new_triggers.append(trigger)
            fired_ids.add(rung["id"])

    return {
        "custom_rungs_today": rungs,
        "fired_custom": fired,
        "new_triggers_custom_today": new_triggers,
    }


def _sell_rung_id(level: float, action: str | None) -> str:
    action_part = (action or "").strip().lower().replace(" ", "-")
    return f"sell-{round(float(level), 4)}-{action_part}" if action_part else f"sell-{round(float(level), 4)}"


def evaluate_sell_targets(
    price: float,
    price_date: dt.date,
    sell_targets_cfg: list[dict],
    prev_fired_sell: list[dict] | None,
) -> dict:
    """Price levels to sell into, the mirror image of the buy ladder.

    Fires when price rises to or ABOVE the level, where a buy rung fires at
    or below. Like custom targets and unlike the MA ladder these never reset
    on a period boundary: a sell is a one-off decision about a position, not
    a recurring accumulation rule, so once it fires it stays fired until the
    entry is edited or removed from stocks.yaml (which changes its id and
    makes it new again).

    The `action` text is the user's own wording -- "sell half", "sell all",
    "sell a covered call" -- and is shown verbatim rather than interpreted.
    Nothing here sizes or places an order; it is an alert.
    """
    sell_targets_cfg = sell_targets_cfg or []
    current_ids = set()
    rungs = []
    for target in sell_targets_cfg:
        level = target.get("level")
        if level is None:
            continue
        rid = _sell_rung_id(level, target.get("action"))
        current_ids.add(rid)
        rungs.append(
            {
                "id": rid,
                "source": target.get("action") or "sell",
                "level": round(float(level), 4),
                "note": target.get("note"),
                "is_sell": True,
            }
        )
    rungs.sort(key=lambda r: r["level"])  # nearest sell first

    prev_fired_sell = prev_fired_sell or []
    fired = [f for f in prev_fired_sell if f["id"] in current_ids]
    fired_ids = {f["id"] for f in fired}

    new_triggers = []
    for rung in rungs:
        if price >= rung["level"] and rung["id"] not in fired_ids:
            trigger = {**rung, "first_hit_date": price_date.isoformat()}
            fired.append(trigger)
            new_triggers.append(trigger)
            fired_ids.add(rung["id"])

    return {
        "sell_rungs_today": rungs,
        "fired_sell": fired,
        "new_triggers_sell_today": new_triggers,
    }


def evaluate_stock(
    tier: str,
    price: float,
    price_date: dt.date,
    mas: dict,
    rules: dict,
    prev_stock_state: dict | None,
    base_amount: float,
    overrides: dict | None = None,
) -> dict:
    tier_cfg = rules["tiers"][tier]
    refresh = tier_cfg["refresh"]
    buy_enabled = tier_cfg.get("buy_enabled", True)
    pkey = period_key(refresh, price_date)
    pstart = period_start(refresh, price_date)

    prev_period = (prev_stock_state or {}).get("period", {})
    same_period = prev_period.get("key") == pkey
    cfg = ladder_config(tier_cfg, rules, overrides)

    if not buy_enabled:
        # A tier held only to sell out of: no ladder, no buy triggers. Its
        # sell targets are evaluated separately by the caller.
        return {
            "tier": tier,
            "price": price,
            "price_date": price_date.isoformat(),
            "mas": mas,
            "period": {"type": refresh, "key": pkey, "start_date": pstart.isoformat()},
            "ladder": [],
            "ladder_config": cfg,
            "clustered": False,
            "full_ladder_today": [],
            "fired_this_period": [],
            "new_triggers_today": [],
            "next_rung": None,
            "buy_enabled": False,
        }

    # Reuse this period's frozen ladder only while the config that shaped it
    # is unchanged -- editing rules.yaml or a stock's `ladder:` overrides
    # takes effect on the next run instead of waiting out the period.
    if same_period and prev_stock_state.get("ladder") and prev_stock_state.get("ladder_config") == cfg:
        ladder = prev_stock_state["ladder"]
        clustered = prev_stock_state.get("clustered", False)
        fired = list(prev_stock_state.get("fired_this_period", []))
    else:
        ladder, clustered = build_period_ladder(tier_cfg, mas, rules, overrides)
        # A rebuild mid-period must not resurrect rungs that already fired:
        # the user may well have placed that order, and re-offering it would
        # read as a second buy. Carry a surviving rung's fired record over,
        # re-stated at its new level but keeping the date it first hit (tick
        # ids embed that date, so this is also what keeps a ✓ attached).
        # Rungs the rebuild removed outright are gone, history included.
        #
        # An id surviving isn't enough: re-anchoring a ladder can leave
        # "rung-drop-1" pointing at a much deeper level than the one that
        # actually fired. Carry the record over only when the new level is
        # at or above the fired one -- price provably traded at or below
        # that old level, so it reached the new one too. A deeper new level
        # may never have been touched, and marking it fired would hide a
        # rung the user hasn't bought yet.
        prev_fired = {f["id"]: f for f in (prev_stock_state or {}).get("fired_this_period", []) or []} if same_period else {}
        fired = []
        for rung in ladder:
            prev_hit = prev_fired.get(rung["id"])
            if not prev_hit or prev_hit.get("level") is None or rung["level"] < prev_hit["level"]:
                continue
            fired.append(
                {
                    **rung,
                    "amount": round(base_amount * rung["multiplier"], 2),
                    "first_hit_date": prev_hit.get("first_hit_date") or price_date.isoformat(),
                }
            )

    full_ladder = extend_with_drop_cascade(
        ladder, price, rules["cap_multiplier"], effective_drop_step(rules, overrides)
    )

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
        "ladder_config": cfg,
        "clustered": clustered,
        "full_ladder_today": full_ladder,
        "fired_this_period": fired,
        "new_triggers_today": new_triggers,
        "next_rung": next_rung,
        "buy_enabled": True,
    }
