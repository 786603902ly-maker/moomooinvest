# moomooinvest — working notes for Claude sessions

## Trunk branch: `claude/investment-rules-stock-tiers-benvvw`

This is the repo's permanent trunk. It is also the actual GitHub default
branch, and it's what both automations read from:

- `.github/workflows/daily-price-check.yml` (GitHub Actions cron) only
  fires from the repo's default branch, by GitHub's own design.
- The "moomooinvest dashboard refresh" scheduled Routine (see
  `mcp__Claude_Code_Remote__list_triggers`) has this branch name hardcoded
  in its prompt — it clones, checks out, and pushes back to it directly.
- The Vercel project's "Production Branch" setting (see README's Hosting
  section) is also pinned to this branch name — that's what makes every
  push here auto-deploy the live dashboard. If this branch is ever renamed,
  update that Vercel setting too (Project Settings → Git), not just the
  Routine's prompt and this file.

The name looks like an ephemeral Claude-session branch (because it started
as one) but it is not disposable — treat it as this repo's `main`.

**If you're a Claude Code session working on this repo on a different
branch** (interactive sessions get their own auto-generated branch, e.g.
`claude/<slug>-<random>`): merge your work into `claude/investment-rules-stock-tiers-benvvw`
and push it there before you finish, not just to your own session branch.
Work left stranded on a throwaway session branch never reaches the daily
Routine or GitHub Actions — they only ever see this trunk branch. This bit
Claude once already (2026-08-23): a full round of feature work sat on
`claude/moomoo-skills-portfolio-w0orcr` for two commits before anyone
noticed the scheduled dashboard refresh was silently rebuilding from the
old code on trunk instead.

If you ever get real permission/ability to change the repository's actual
GitHub default-branch setting (not available via the standard GitHub MCP
tools as of this writing — there's no repo-settings-update tool, only
branch/PR/file/issue operations) and want to rename trunk to something
less session-branch-looking (e.g. `main`), that's a reasonable cleanup —
just remember to also update the Routine's prompt (it hardcodes the branch
name) and this file.

## System overview

See `README.md` for the full DCA alert system design (tiers, MA ladder,
custom targets, valuation dashboard, etc.).

## Standing user preferences on ladder levels (recorded 2026-09-20)

Read `config/rung_notes.yaml` and the README section **"Your standing ladder
preferences"** before advising on, or changing, any rung level. The short
version of the rule the user stated:

- Default step between rungs is `drop_step_pct` = 5%. When a stock is in a
  **clear downtrend and already at a low price**, they'd rather step down
  **7%** instead — deeper entry, lower average cost — **but only where that
  7% level is still above the next real MA support**. If an MA sits above
  the 7% level, that MA stays the rung; the preference only widens steps
  that were synthetic to begin with.
- When several MAs are bunched (a few percent apart, so consecutive rungs
  read as near-repeats) and price has already fallen well below them, they'd
  rather **skip the shallow top rungs** and start the ladder at the deeper
  support (e.g. RKLB: "start with ma250 directly").
- ETFs are treated the other way: smaller expected drawdown, so the default
  5% step is fine (XLV).

**Implemented 2026-09-21** as a `ladder:` block per stock in
`config/stocks.yaml` (`drop_step_pct`, `start_ma`, `skip_top_rungs`), read
by `build_period_ladder` / `extend_with_drop_cascade` in
`scripts/engine.py`. 13 stocks carry one; the rest build exactly as before.
Two invariants to preserve when touching this:

- Rule 3 still decides every rung — whichever is **lower** of the next real
  MA support and the drop level. A widened step therefore never overrides
  an MA that sits deeper than it (this is why AMD's and LRCX's MA rungs
  didn't move), and that is the user's own rule, not a limitation.
- Ladders are frozen per refresh period, so `ladder_config` (the shape
  inputs) is stored in `state.json` and compared on every run — a config
  edit rebuilds that stock's ladder immediately instead of waiting out the
  period. A rebuild clears `fired_this_period`, so a fired record is
  carried over — re-stated at the rung's new level, keeping its original
  `first_hit_date` (tick ids embed that date, so this is what keeps the
  user's ✓ attached). Two conditions, both required: the rung id survived
  **and** its new level is at or above the level that actually fired. An id
  alone is not enough — re-anchoring a ladder can leave `rung-drop-1`
  pointing at a much deeper level that price never reached, and marking
  that fired would hide a rung the user hasn't bought.

### Rung note keys drift

Rung ids come from the MAs, so they move. `normalize_rung_id` in
`scripts/common.py` makes cluster-order flips (`ma-200+100` vs
`ma-100+200`) resolve to the same note, but a cluster merging or splitting
renames the rung for real. `build_dashboard.py` prints
`[rung_notes] note key matches no rung today: ...` to stderr in that case —
re-point the key in `config/rung_notes.yaml` when one shows up, rather than
letting the note silently render nowhere.

## Where the user's buy history lives

Ticked-off rungs ("I actually bought this") are stored in the Vercel KV
database behind `api/ticks.js`, **not** in this repo. Cloning the repo does
not give you that history.

- If `data/ticks.json` exists, that is the archive `daily-price-check.yml`
  writes each run — read it.
- If it does not exist, the repository is still public and the archive step
  is deliberately skipping. Buy history in a public repo is published
  permanently, git history included, so do not commit it and do not print
  it into Actions logs (they inherit repository visibility). Both the daily
  job and the smoke test read the real visibility from the API each run and
  gate themselves on it — do not replace that check with an assumption.
- Only the user can change repository visibility; the GitHub MCP tools have
  no repo-settings operation.

`fired_this_period` is the period's MEMORY, not a list of rows to render. A
rung stays in it after price rises back above the level, and the dashboard
renders a checkbox only while `price <= level`. That combination is what
prevents a second buy into a level already taken this period: the tick id is
pinned to `first_hit_date`, so when price returns the same checkbox comes
back already ticked. Do not "tidy up" fired entries whose level is above the
current price -- that silently re-opens levels the user already bought.

Tick ids are `ticker|rung-id|first_hit_date`, and the dashboard's live-price
code mints that same id client-side for a rung the live price reaches during
the session (see `syncLiveCheckbox`). That is deliberate and load-bearing:
it is what lets an intraday tick survive into the evening run instead of
needing reconciliation. If you change how either side builds the id, change
both, or every intraday tick silently detaches.

Ticks are a personal record only. `run_check.py` never reads them, and a
ticked rung is still re-offered when its period resets — that is intended.
An action meant to change future alerting is a `custom_targets` entry.

## This sandbox cannot reach the live site

The network policy denies both `moomooinvest.vercel.app` and the upstream
quote provider, so you cannot curl the dashboard or `/api/quote` to check a
deploy. Run the **Live site smoke test** workflow instead (manual trigger)
and read its logs — a GitHub runner has plain internet access. Don't claim
a deploy is working without doing that.
