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
   you acted on. Ticks are stored in your browser's local storage (per
   device) purely for your own tracking — they don't feed back into the
   alerting logic. Export your tick history as CSV any time from the
   dashboard.

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
| T2 | PLTR, IGV*, MSFT, META | MA100 → MA150 → MA200 | monthly |
| T3 | GOOG, AMZN, RKLB, AMD | MA150 → MA200 → MA250 | monthly |
| T3.5 | NBIS, LRCX, FTNT | MA200 → MA250 (then 5% cascade) | monthly |
| T5 | MU | MA250 (then 5% cascade) | monthly |

\* IGV is an ETF — MA-ladder alerts apply, but it has no Morningstar
analyst target price / fair value, so that part is skipped for it.

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
