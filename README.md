# moomooinvest — DCA Alert System

Codifies your tiered, moving-average-based dollar-cost-averaging rules into
an automated pipeline: prices refresh daily, thresholds are evaluated
against your ladder rules, and a dashboard (published as a Claude Artifact)
shows what's hit and lets you tick off what you've actually invested in.

## How it works

1. **Daily** (GitHub Actions, `.github/workflows/daily-price-check.yml`,
   21:30 UTC ≈ 05:30 SGT next day, after US close): fetches fresh daily
   closes, recomputes MA60/100/150/200/250 per stock, evaluates each tier's
   ladder against the new price, and commits the result to `data/state.json`.
   This step needs real internet access to Yahoo/stooq, which the Claude
   sandbox that built this doesn't have — hence it runs on GitHub's own
   runners instead of as a Claude-scheduled job.
2. **Daily + Weekly** (Claude scheduled routines, since only a Claude session
   has the Artifact and WebSearch tools): pulls the latest `state.json`,
   rebuilds `dashboard/index.html`, and republishes it to the same Artifact
   URL. On **Mondays** it additionally web-searches each stock's current
   Morningstar-style analyst average target price and fair value estimate
   and updates `config/stocks.yaml` before rebuilding.
3. **You** open the dashboard link each morning, see what's hit, place your
   GTC order(s) manually in moomoo, and tick the checkbox next to the rung
   you acted on.

   **What the checkbox actually does**: purely a personal reminder. It's
   written to `localStorage` in your browser only (key
   `moomooinvest-ticks-v1`) — never committed to the repo, never read by
   `run_check.py` or `engine.py`, and doesn't sync across devices. Its only
   two effects: (1) it grays out that rung and moves it into the "Action
   log" table below, and (2) that table is what "Export CSV" reads. It does
   **not** change whether a rung is considered "fired," does not stop the
   next period from re-offering the same rung, and does not affect
   `data/state.json` at all. If you want an action to actually change
   future alerting behavior, use a **custom target** instead (below).

## The rule engine (`scripts/engine.py`)

For each tier, a fixed set of MA periods is watched (`config/rules.yaml`).
Once per refresh period (weekly for T1, monthly for T2 and below — rule 4),
those MAs' current values are sorted **by value, not by label** (rule 2) to
build that period's ladder: highest value = first rung = ×1, next = ×1.5,
lowest = ×2 (the cap, rule 1). Within the period, each rung fires once; a
new period resets all of them even if price never recovered (rule 4). If two
adjacent rungs are within 1.5% of each other, the whole ladder is replaced
with a clean 5%-drop cascade from the top instead (rule 5). If price falls
through the lowest rung, further trigger points are generated every 5% below
that, still capped at ×2 per trigger (rule 3).

## Tiers, as read from your watchlist screenshots

| Tier | Stocks | MA ladder | Refresh |
|---|---|---|---|
| T1 | NVDA, TSM, AVGO | MA60 → MA100 → MA150 | weekly |
| T2 | PLTR, IGV*, MSFT, META | MA100 → MA150 → MA200 | **biweekly** |
| T3 | GOOG, AMZN, RKLB, AMD | MA150 → MA200 → MA250 | monthly |
| T3.5 | NBIS, LRCX, FTNT, XLV* | MA200 → MA250 (then 5% cascade) | monthly |
| T5 | MU, SOFI, V, ASML, GRAB, TSLA, FXI*, OSCR, ASTS, MRVL | MA250 only (then 5% cascade) | monthly |
| T9 | BRK-B, HIMS, PYPL, DUOL, NU, MSTR, VITL | MA250 only (then 5% cascade) | monthly |

T5/T9 were added from your "T3.9 above" moomoo watchlist screenshots. Per
your instruction they deliberately use only **one** trigger (break below
MA250, the lowest MA tracked) rather than the fuller 3-rung ladder — same
single-rung mechanism already used for MU. `T9`'s `base_amount`/`refresh`
default to match `T5` (600/monthly) since none was specified; adjust in
`config/rules.yaml` if wrong. MRVL's watchlist label was `!T5` (others were
plain `T5`) — added to T5 as-is since the `!` meaning wasn't specified,
flag it if it should be handled differently.

\* IGV, FXI, XLV are ETFs — MA-ladder alerts apply, but they have no analyst
target price / fair value (moomoo doesn't show one for ETFs either), so
that part is skipped for them.

## Every card always shows its full planned ladder

Cards used to only show rungs that had already fired, plus a one-line
"Next: ..." hint for the closest unfired one. Now every card always shows
**all** of that period's rungs (typically 2-3 for T1-T3.5, 1 for T5/T9) —
fired ones are checkable as before, not-yet-fired ones show as a dashed
"pending" row with their price level, amount, and how far away the current
price is. This is meant to let you review the whole plan for a stock at a
glance and decide whether you're comfortable just waiting for it to fire,
without having to reconstruct the ladder from `config/rules.yaml` yourself.

## Fair value / target price: now sourced from moomoo, not web search

`target_price` and `fair_value` in `config/stocks.yaml` used to be filled by
a weekly best-effort web search (a proxy for Morningstar's numbers, often
stale or unavailable). That's been replaced: you export/paste the
**"平均目标价" (target price) and "公允价值" (fair value)** columns straight
from the moomoo App/CSV, and those exact numbers get written into
`config/stocks.yaml` with `fundamentals_source: "moomoo (user CSV export)"`.
There's no moomoo API integration doing this automatically (see chat history
for why — no official moomoo Claude Skill exists, and the "moomoo skill
installer" doc that surfaced is not something this repo trusts or executes);
it's a manual-but-precise refresh: whenever you want updated numbers, export
the CSV from moomoo and share it, and it gets applied the same way.

**Valuation overview tab**: the dashboard now has a second tab (next to
"Alerts & ladder") showing every stock sorted from most-undervalued to
most-overvalued vs its fair value estimate, as a diverging bar chart plus a
data table (price, target price, vs-target %, fair value, vs-fair-value %).
Use it to sanity-check whether a stock's tier / MA-ladder assignment still
matches how cheap or expensive it actually looks — e.g. if a stock you put
in T3 (slow accumulation) is sitting 35%+ under fair value, that's a signal
its tier might deserve reconsidering.

## Custom targets: your own buy levels, layered on top of the ladder

Sometimes you want to wait for a specific lower price on a stock regardless
of what the MA ladder says. Add a `custom_targets` list to that stock in
`config/stocks.yaml`:

```yaml
  - ticker: RKLB
    ...
    custom_targets:
      - level: 60
        amount: 900          # optional, defaults to the tier's base_amount
        note: "wait for capitulation"
        added: "2026-08-22"  # optional, informational only
```

These are evaluated every day alongside the MA ladder, but behave
differently on purpose:

- **They don't reset each period.** The MA ladder's rungs reset every
  week/biweek/month so the same level can fire again next period. A custom
  target fires once and then stays "fired" indefinitely — it's your
  one-off call, not a recurring rule.
- **They're always shown**, in their own "Your targets" section on that
  stock's card, tagged distinctly from the MA rungs, so they can't be
  mistaken for auto-generated ones.
- **Editing = a new target.** Change the `level` or `note` and it's treated
  as a fresh entry (can fire again); delete the entry and its fired history
  is dropped too. There's no separate "reset" command — editing the YAML
  *is* the edit mechanism.
- **How to edit it right now**: tell me the ticker/price/amount/note in
  chat and I'll update `config/stocks.yaml` and push — same flow as
  updating fair value numbers. A fully self-serve in-dashboard editor that
  writes straight back to this repo isn't wired up (the dashboard is a
  static Artifact; the engine that reads this file runs on GitHub Actions,
  which can't watch the Artifact live) — this chat-driven flow is the
  reliable version of that for now. If you want true point-and-edit later,
  a small hosted endpoint (e.g. via a Val Town-backed bridge) could let the
  dashboard write directly and have `run_check.py` read from it over HTTP
  — happy to build that out if the manual flow gets tedious.
- Takes effect on the **next `run_check.py` run** (the daily GitHub Actions
  job) — a dashboard-only rebuild (no network) still picks up **fair
  value/target price edits** immediately, since those are just re-read from
  config each render, but custom-target *firing* needs a fresh price
  check to evaluate against.

## ⚠️ Please confirm / adjust

A few things were inferred rather than stated outright — please check
`config/rules.yaml` and `config/stocks.yaml` and edit if wrong:

- **Base amount per tier**: only T1's SGD 600 was given explicitly. T2–T5
  are currently defaulted to the same SGD 600 base — change
  `base_amount` in `config/rules.yaml` if you invest different amounts per
  tier.
- **T3 / T3.5 / T5 MA ladders**: your rules explicitly gave T1
  (60/100/150) and T2 (100/150/200). T3 ("start at MA150, end at MA250")
  and T3.5 ("start at MA200, end at MA250") were inferred as shown above;
  T5 (MU) isn't in your original rules at all — it's a new tier extending
  the same pattern one step further, using MA250 plus the 5%-cascade for
  its second and third rungs.
- **IGV's "%111" label**: not used anywhere in the engine — flagged in
  `config/stocks.yaml` in case it should mean something (e.g. distance
  from 52-week high) that should feed into alerts.
- **Morningstar figures via web search**: there's no free API for
  Morningstar's own numbers, so the weekly refresh uses web search as a
  best-effort proxy (analyst consensus target price is usually findable;
  Morningstar's own fair value estimate is often paywalled and may lag or
  be missed). Worth spot-checking against the app periodically — the
  dashboard shows `fundamentals_source` / last-updated date for each stock
  so you can see how fresh/reliable each number is.

## Repo layout

```
config/
  rules.yaml    tier ladder definitions, multipliers, cadence
  stocks.yaml   tier assignment + target price / fair value per stock
data/
  state.json    computed output (prices, MAs, ladder, fired triggers) — generated
  prices/       cached daily close history per ticker — generated
scripts/
  fetch_prices.py   stooq (primary) / Yahoo (fallback) daily close history
  indicators.py     moving averages
  engine.py         ladder construction + trigger evaluation
  run_check.py      daily entrypoint -> data/state.json
  build_dashboard.py  renders dashboard/index.html from state + config
dashboard/
  index.html    generated dashboard (also what gets published as the Artifact)
.github/workflows/
  daily-price-check.yml   the only step that needs real internet access
```

## Manual run

```bash
pip install pyyaml
cd scripts
python3 run_check.py        # needs internet access to stooq/Yahoo
python3 build_dashboard.py  # pure templating, no internet needed
```

Note: GitHub only runs *scheduled* Actions workflows from the files on the
repository's **default branch**. If this branch isn't the default, the cron
schedule won't fire until it is merged (or triggered manually via
"Run workflow" / `workflow_dispatch`).
