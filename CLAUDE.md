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

As of 2026-09-20 this is **documentation, not engine behavior** — the engine
still uses one global 5% step and never skips rungs. If the user asks to
make it real, it needs a per-stock override in `config/stocks.yaml` plus
`build_period_ladder` / `extend_with_drop_cascade` changes in
`scripts/engine.py`, and the ladder is frozen per period, so a rebuild-on-
config-change guard is needed too (state reuses the stored ladder while the
period key is unchanged).

### Rung note keys drift

Rung ids come from the MAs, so they move. `normalize_rung_id` in
`scripts/common.py` makes cluster-order flips (`ma-200+100` vs
`ma-100+200`) resolve to the same note, but a cluster merging or splitting
renames the rung for real. `build_dashboard.py` prints
`[rung_notes] note key matches no rung today: ...` to stderr in that case —
re-point the key in `config/rung_notes.yaml` when one shows up, rather than
letting the note silently render nowhere.
