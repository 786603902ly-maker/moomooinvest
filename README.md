# moomooinvest — DCA Alert System

Codifies your tiered, moving-average-based dollar-cost-averaging rules into
an automated pipeline: prices refresh daily via GitHub Actions alone (no
Claude session needed), thresholds are evaluated against your ladder rules,
and a dashboard (hosted on Vercel — see [Hosting](#hosting-vercel), which
auto-deploys on every push) shows what's hit and lets you tick off what
you've actually invested in, synced across your devices. A Claude Artifact
copy of the same dashboard still exists as a manual backup/preview link,
but nothing refreshes it automatically anymore (see below) — ask in chat if
you want it re-published.

> **Trunk branch is `claude/investment-rules-stock-tiers-benvvw`** — the
> GitHub Actions crons and Vercel's Production Branch setting all read/write
> this branch. If you're a Claude session working from a different
> (session-specific) branch, merge into this one before you're done — see
> `CLAUDE.md` for why this matters and what went wrong once already when it
> wasn't.

## How it works

1. **Daily** (GitHub Actions, `.github/workflows/daily-price-check.yml`,
   21:30 UTC ≈ 05:30 SGT next day, after US close): fetches fresh daily
   closes, recomputes MA60/100/150/200/250 per stock, evaluates each tier's
   ladder against the new price, and commits the result to `data/state.json`
   along with a rebuilt `dashboard/index.html` (before 2026-09-21 it
   committed the state alone, so the page Vercel served kept its previous
   build until some later market-open run happened to rebuild it).
   Prices come from stooq with Yahoo as a second source, and the two are
   **merged** rather than "first one that answers wins": stooq publishes US
   closes on a lag, so it can return a perfectly valid series that stops a
   day or two short. Each source is checked against the last expected
   trading session and the next is consulted if it's behind — otherwise a
   stale-but-successful response silently pins the dashboard to an old
   close, which is exactly what happened on 2026-09-21.
   This step needs real internet access to Yahoo/stooq, which the Claude
   sandbox that built this doesn't have — hence it runs on GitHub's own
   runners instead of as a Claude-scheduled job. This is the data the
   MA/ladder math is keyed off — it never changes intraday.
2. **Live, on every page load** (`api/quote.js`, no cron involved): the
   dashboard asks this small serverless function for current quotes when you
   open it, then again every 60 seconds while the US market is open (and
   whenever you switch back to the tab). It fetches server-side, so the price
   you see is seconds old, not hours. It updates the displayed price, each
   pending rung's "% away", and flags any pending rung the live price has
   already reached as **hit now**. If the fetch fails, every card falls back
   to the committed close — the page never ends up blank or wrong, just less
   current. This is display only: which rungs have officially *fired* is
   still decided by `run_check.py` off the daily close, so a "hit now" flag
   is a heads-up to go look, not a state change.
3. **Market open** (GitHub Actions, `.github/workflows/market-open-price-check.yml`):
   NYSE opens at 9:30am ET, which lands at either 9:30pm SGT (EDT, roughly
   Mar–Nov) or 10:30pm SGT (EST, roughly Nov–Mar) depending on the time of
   year. Rather than track the DST flip, this workflow fires at *both*
   possible "~15 min after open" times every weekday (13:44 UTC and
   14:44 UTC). `scripts/market_open_snapshot.py` then checks the real
   America/New_York clock and only actually fetches a live quote if it's
   genuinely within ~25 minutes of today's open — so whichever of the two
   firings doesn't match the current DST regime is a silent no-op, and the
   schedule self-adjusts across the March/November transitions with no
   manual cron edits.

   **Treat this as a fallback, not the live-price mechanism** — step 2 is
   that. GitHub queues scheduled runs behind everything else and was
   starting this one **3.5–5 hours late** (measured Sept 2026: firings due
   at 09:44 ET actually landed 13:13–14:52 ET). Until 2026-09-21 the script
   also only accepted 09:30–09:55 ET, so *every* firing fell outside its own
   window and skipped the fetch — `intraday_price` had never once been
   written for any stock, and the job's only real effect was rebuilding the
   dashboard, under a commit message that claimed otherwise. The window is
   now the whole session (09:30–16:00 ET). You can also run it on demand
   from the Actions tab (`workflow_dispatch`), which starts immediately —
   the delay only affects `schedule` events.

   When it does fire, it writes a live
   `intraday_price` / `intraday_price_at` per stock into `data/state.json`
   (on top of, not instead of, the daily close) and rebuilds
   `dashboard/index.html` so the repo has a fresh static copy — with
   Vercel's git integration connected (see [Hosting](#hosting-vercel)),
   this commit alone is enough to trigger a live redeploy, no Routine or
   Claude session needed.
4. ~~Daily + Weekly Claude scheduled routines~~ — **disabled as of 2026-09-06**.
   Two "moomooinvest dashboard refresh" Routines used to pull `state.json`,
   rebuild `dashboard/index.html`, and republish it to the Artifact backup
   URL shortly after each possible market-open time. Once Vercel's git
   integration went live, steps 1/2 above already keep the real dashboard
   current on their own — these Routines were only extending that to the
   Artifact copy, so they were turned off rather than left running for no
   reason. The Artifact backup is now static between whenever a Claude
   session last published it; ask in chat if you want it refreshed. (Even
   further back, this used to also web-search Morningstar-style target
   price / fair value every Monday — replaced by you pasting exact moomoo
   App numbers into chat instead, well before the Vercel move.)
5. **You** open the dashboard link any time during the session, see what's
   hit against the live price, place your GTC order(s) manually in moomoo,
   and tick the checkbox next to the rung you acted on.

   **What the checkbox actually does**: purely a personal reminder, not a
   rule input. Checking it calls `api/ticks.js` (a small serverless
   function, see [Hosting](#hosting-vercel)) which stores the tick in a
   database — so it syncs across every device you open the dashboard on,
   with a `localStorage` copy (key `moomooinvest-ticks-v1`) kept only as an
   instant-paint cache for while that request is in flight. There's no
   login on this endpoint: anyone with the dashboard link can view or check
   things off, which is an accepted tradeoff for a personal tracker — don't
   share the link if that's not okay. Ticks are never read by
   `run_check.py` or `engine.py`. Its effects are all cosmetic/logging: (1)
   it grays out that rung, tags it "✓ confirmed \<date\>", and moves it into
   the "Action log" table below; (2) that table is what "Export CSV" reads.
   It does **not** change whether a rung is considered "fired," does not
   stop the next period from re-offering the same rung, and does not affect
   `data/state.json` at all. If you want an action to actually change
   future alerting behavior, use a **custom target** instead (below).

   **Where ticks live, and whether Claude can see them.** A tick is stored
   server-side in the Vercel KV database, so it syncs to every device you
   open the dashboard on. That database is *not* part of this git repo, so a
   Claude session — which only ever clones the repo — cannot see your buy
   history by default. Two things bridge that gap, and **both are gated on
   the repository being private**, because buy history committed to a public
   repo is published permanently and stays in git history even if the file
   is later deleted:

   - `daily-price-check.yml` archives the tick store to `data/ticks.json`
     on each run, so every future session reads it straight from the repo.
   - The **Live site smoke test** workflow prints the tick contents rather
     than just counts.

   Each checks the repository's actual visibility through the API on every
   run, so while this repo is public they skip with a notice and nothing
   leaks. Flip it to private (Settings → General → Change visibility) and
   both start working on the next run with no code change.

   Note that repository visibility and *dashboard* visibility are separate:
   making the repo private does **not** make <https://moomooinvest.vercel.app/>
   private, and the tick/note endpoints stay unauthenticated either way.

## Hosting: Vercel

The dashboard is a static file (`dashboard/index.html`) plus three tiny
serverless functions — `api/ticks.js` and `api/notes.js` for cross-device
tick and note sync, and `api/quote.js` for live prices — no build step.
`api/quote.js` needs no database and no env vars (it just proxies a public
quote endpoint server-side, with a 30s edge cache so repeat loads don't
re-hit upstream), so it works as soon as the project deploys. One-time setup, done from the Vercel
dashboard (not by Claude — Claude doesn't have your Vercel login):

1. **Import the repo**: on vercel.com, "Add New… → Project", import
   `786603902ly-maker/moomooinvest`. Framework preset "Other" is fine —
   `vercel.json` handles routing `/` to `dashboard/index.html`, and Vercel
   auto-detects everything under `api/` as serverless functions regardless
   of framework preset. No build command, no output directory setting
   needed.
2. **Set the production branch** to `claude/investment-rules-stock-tiers-benvvw`
   (Project Settings → Git) — that's this repo's trunk (see the branch note
   at the top of this file / `CLAUDE.md`), so every push to it (the daily
   GitHub Actions job or a Claude session) triggers an automatic redeploy.
   No manual "publish" step, unlike the Artifact.
3. **Add a database for tick/note sync**: Project → Storage → connect a KV
   store (Upstash-backed; free tier is plenty for this). Vercel injects the
   `KV_REST_API_URL` / `KV_REST_API_TOKEN` env vars automatically — both
   `api/ticks.js` and `api/notes.js` just need them present, no other
   config, since they already share one store. Until this step is done,
   checkboxes/notes still work per-device (falling back to the
   `localStorage` cache) but won't sync across devices, and the dashboard
   footer/sync-status line will say so.
4. You get a stable `<project>.vercel.app` URL (or attach a custom domain
   under Project Settings → Domains) that never changes across redeploys —
   unlike an Artifact URL, which is one specific chat's publish target.

**The live dashboard is <https://moomooinvest.vercel.app/>** (project:
`vercel.com/786603902ly-5925s-projects/moomooinvest`). Note that the Claude
sandbox which develops this repo sits behind a network policy that denies
both that host and the quote provider, so a Claude session **cannot check
the live site or `/api/quote` directly**. To verify a deploy, run the
**Live site smoke test** workflow (`.github/workflows/live-smoke-test.yml`,
manual trigger only) — a GitHub runner has plain internet access and its
logs are readable, so that is how a session confirms the deployed endpoint
actually works.

The Claude Artifact copy (see `data/artifact_url.txt`) is kept as a manual
backup/preview link — a Claude session can still republish it on request,
but it isn't the primary link once Vercel is live, and its `/api/ticks` and
`/api/notes` calls will silently fail (Artifacts sandbox out arbitrary
network requests) so ticks and notes there only ever work per-device.

## The rule engine (`scripts/engine.py`)

For each tier, a fixed set of MA periods is watched (`config/rules.yaml`).
Once per refresh period (weekly for T1, biweekly for T2, monthly for T3 and
below), those MAs' current values are looked up and turned into that
period's ladder as follows, aimed at genuinely spaced-out support levels
rather than blindly following whichever MAs happen to be configured:

1. **Merge near-duplicate MAs into one support.** MAs within
   `cluster_merge_pct` (3%) of each other are averaged into a single support
   level — two MAs a percent or two apart isn't two buy points, it's the
   market agreeing on one support.
2. **Rung 1 = the highest support**, multiplier ×1.
3. **Each further rung = whichever is lower of** (a) the next real support
   level below the prior rung, or (b) the prior rung minus `drop_step_pct`
   (5% globally, overridable per stock — see "Your standing ladder
   preferences"). A real MA support only becomes a rung when it's already at least
   5% below the one above it; otherwise that step is a plain 5% drop
   instead. This guarantees rungs are never bunched close together, and a
   rung is always a genuinely deeper level than the last, not a near-repeat
   of it. Multipliers step ×1 → ×1.5 → ×2 (the cap) across however many
   rungs this produces (fewer than 3 if MAs merged/ran out).
4. Within a period, each rung fires once; a new period resets all of them
   even if price never recovered.
5. If price falls through the lowest rung, further trigger points are
   generated every `drop_step_pct` below that, still capped at ×2 per
   trigger.
6. A stock may override how its own ladder is built, via a `ladder:` block
   in `config/stocks.yaml` — `drop_step_pct` (this stock's step),
   `start_ma` (anchor the ladder at this MA, ignore shallower ones) and
   `skip_top_rungs` (discard the N shallowest rungs, multipliers restarting
   at ×1). Rule 3 is unchanged underneath: a widened step never overrides
   an MA support that sits deeper than it. Changing any of these rebuilds
   that stock's ladder on the next run rather than waiting out its period —
   `ladder_config` in `state.json` is what that comparison reads, and rungs
   that survive a rebuild keep their original `first_hit_date`.

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

## Rung notes: annotate a specific price level

Under every rung on the dashboard (fired or pending) there's a small text
field where you can type a note directly — reasoning, conviction, "wait for
X to confirm", whatever. These are **purely informational**, not a trigger
mechanism (see Custom targets below for that):

- Typing into a note field syncs it live across your devices via
  `api/notes.js` (same small serverless backend + database as the tick
  sync — see [Hosting](#hosting-vercel)), with a `localStorage` copy kept
  only as an instant-paint cache. Same no-login tradeoff as ticks: anyone
  with the dashboard link can read or edit them.
- **"Backup my notes"** (next to Export CSV) is now just an optional local
  export — a Markdown file, one section per rung, each carrying a `key`
  like `NVDA|ma-60+100` — for your own offline record. You don't need to
  download or paste anything back for notes to persist or sync anymore;
  typing is enough.
- `config/rung_notes.yaml` (`ticker: { rung_id: "note text" }`) still exists
  as the seed value baked into `dashboard/index.html` at build time — it's
  what a fresh page shows before the live fetch lands, and what the Claude
  Artifact backup falls back to (its sandbox blocks the live fetch
  entirely, same as ticks there). Ask in chat if you want a note committed
  there directly instead of through the dashboard.
- **Note keys drift with the ladder.** A rung's id is derived from its MAs,
  so it changes when they do. Order flips inside a merged cluster
  (`ma-200+100` → `ma-100+200` once MA100 crosses above MA200) are
  normalized away, so those notes keep matching on their own. A cluster
  *merging or splitting* renames the rung for real; `build_dashboard.py`
  prints `[rung_notes] note key matches no rung today: ...` to stderr when
  that happens, so re-point the key in `config/rung_notes.yaml` instead of
  letting the note silently render nowhere.
- If a note implies you actually want an alert at a specific price, say so
  explicitly — notes alone don't create one; that's what Custom targets
  (below) are for. The eventual goal is for Claude to learn your reasoning
  patterns from accumulated notes well enough to weigh in on tier/ladder
  judgment calls on its own — this is a step toward that, not the whole
  thing yet.

## Your standing ladder preferences (from your notes)

Stated 2026-09-20, recorded here so a later session applies the same
reasoning instead of re-deriving it from the raw note text. Implemented
2026-09-21 as per-stock `ladder:` overrides in `config/stocks.yaml` — see
"Status" at the end of this section.

**The rule you gave, in your words:** *"i considered recent trend and
price, if in a clear downtrend and at low price, then normally ok to choose
bit lower price, like 7% drop, if lower than next ma."*

Unpacked into the engine's vocabulary:

- The engine's default step between rungs is `drop_step_pct` = 5%
  (`config/rules.yaml`), and rule 3 already takes whichever is **lower** of
  "next real MA support" and "prior rung − 5%".
- When a stock is in a clear downtrend and already at a low price, you want
  that step widened to **7%** — a deeper entry, to pull the average cost
  down — *provided the 7% step doesn't jump past a real MA support*. If the
  next MA sits above the 7% level, that MA is the rung; the 7% preference
  only applies where the step would have been synthetic anyway.
- The mirror-image case is when the MAs are bunched together
  (`cluster_merge_pct` = 3% merges them, but MAs 4–6% apart still produce
  rungs that feel like near-repeats). There you'd rather **skip the shallow
  top rungs entirely** and start the ladder at the deeper support, because
  price has already fallen well past them — e.g. your RKLB note, "start
  with ma250 directly." Two knobs cover this: `start_ma` when a real MA is
  the level you want to anchor on, `skip_top_rungs` when it isn't (AVGO's
  wanted level is two steps below MA100, with no MA down there to name).
  Multipliers restart at ×1 on whatever survives, so the ladder still steps
  ×1 → ×1.5 → ×2 below it.
- ETFs are the exception in the other direction: you expect a smaller drawdown
  from them, so the default step is fine (your XLV note: *"ok since etf
  expects less drop ratio"*).

What each stock's notes ask for, and the override that now implements it.
Levels are this period's ladder from `data/state.json` (close 2026-09-18):

| Stock | What your note asks for | Override in `stocks.yaml` | Ladder now |
| --- | --- | --- | --- |
| AVGO | Skip the two shallow rungs; first buy two steps below MA100 | `skip_top_rungs: 2` | 354.77 / 337.04 / 320.18 |
| NVDA | Ladder as-is, all three rungs | none | 211.00 / 200.45 / 190.43 |
| TSM | Skip the MA60+MA100 cluster; start at MA150 | `start_ma: 150` | 399.41 / 379.44 / 360.47 |
| IGV | Rung 1 as-is; rungs 2–3 at 7% steps | `drop_step_pct: 7` | 94.82 / 88.18 / 82.01 |
| META | Rung 1 as-is; rungs 2–3 at 7% steps | `drop_step_pct: 7` | 613.62 / 570.67 / 530.72 |
| MSFT | Rung 1 as-is; rungs 2–3 at 7% steps | `drop_step_pct: 7` | 429.14 / 399.10 / 371.16 |
| PLTR | Rungs 2–3 at 7% steps | `drop_step_pct: 7` | 151.75 / 141.13 / 131.25 |
| AMD | MA150 as-is; 7% steps below it | `drop_step_pct: 7` | 399.07 / 354.62 / 327.71 |
| AMZN | Rung 1 as-is; rungs 2–3 at 7% steps | `drop_step_pct: 7` | 240.47 / 223.64 / 207.98 |
| GOOG | Rung 1 as-is; rungs 2–3 at 7% steps | `drop_step_pct: 7` | 338.52 / 314.83 / 292.79 |
| RKLB | Start at MA250, then two 7% steps | `start_ma: 250`<br>`drop_step_pct: 7` | 75.29 / 70.02 / 65.12 |
| FTNT | Rungs 2–3 at 7% steps | `drop_step_pct: 7` | 113.88 / 105.91 / 98.50 |
| LRCX | Rung 3 at a 7% step | `drop_step_pct: 7` | 267.20 / 243.21 / 226.18 |
| NBIS | Rungs 2–3 at 7% steps | `drop_step_pct: 7` | 160.71 / 149.46 / 138.99 |
| XLV | Default 5% step is fine (ETF) | none | 153.76 / 146.07 / 138.77 |

**Status: implemented 2026-09-21.** The `ladder:` block in
`config/stocks.yaml` is read by `scripts/engine.py`; the other 17 stocks
carry no override and build exactly as before. Two things worth knowing:

- **AMD's ladder didn't move.** Its MA150 → MA200 → MA250 gaps are already
  wider than 7% (−11.1% and −7.6%), and rung selection still takes whichever
  is *lower* of the next MA support and the drop level — which is your own
  rule ("7% drop… if lower than next ma"). The override is set, so it starts
  applying the moment those MAs bunch up. Same reasoning left LRCX's MA250
  rung in place.
- **A ladder rebuilds as soon as its config changes**, rather than waiting
  for the period to roll over — `ladder_config` is stored in `state.json`
  and compared on every run. Rungs that survive a rebuild keep their
  original `first_hit_date`, so anything you'd already ticked off stays
  ticked.

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
                     + Yahoo intraday quote (get_intraday_quote)
  indicators.py     moving averages
  engine.py         ladder construction + trigger evaluation
  run_check.py      daily entrypoint -> data/state.json
  market_open_snapshot.py  live post-open snapshot -> intraday_price fields
  build_dashboard.py  renders dashboard/index.html from state + config
dashboard/
  index.html    generated dashboard (deployed to Vercel; also what gets
                 published as the Artifact backup)
api/
  ticks.js      serverless function backing the cross-device tick sync
  notes.js      serverless function backing the cross-device note sync
                (both need a Vercel KV store connected -- see Hosting)
vercel.json     routes "/" to dashboard/index.html
package.json    declares api/*.js's one shared dependency (@vercel/kv)
.github/workflows/
  daily-price-check.yml         daily close fetch, needs real internet access
  market-open-price-check.yml   live snapshot ~15min after NYSE open, also
                                 needs real internet access
```

## Manual run

```bash
pip install pyyaml
cd scripts
python3 run_check.py               # needs internet access to stooq/Yahoo
python3 market_open_snapshot.py    # optional: live snapshot, no-ops outside
                                    # the ~9:30-9:55am ET window (see below)
python3 build_dashboard.py         # pure templating, no internet needed
```

Note: GitHub only runs *scheduled* Actions workflows from the files on the
repository's **default branch**. If this branch isn't the default, the cron
schedule won't fire until it is merged (or triggered manually via
"Run workflow" / `workflow_dispatch`).
