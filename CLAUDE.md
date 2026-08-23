# moomooinvest — working notes for Claude sessions

## Trunk branch: `claude/investment-rules-stock-tiers-benvvw`

This is the repo's permanent trunk. It is also the actual GitHub default
branch, and it's what both automations read from:

- `.github/workflows/daily-price-check.yml` (GitHub Actions cron) only
  fires from the repo's default branch, by GitHub's own design.
- The "moomooinvest dashboard refresh" scheduled Routine (see
  `mcp__Claude_Code_Remote__list_triggers`) has this branch name hardcoded
  in its prompt — it clones, checks out, and pushes back to it directly.

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
