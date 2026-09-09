# GitHub ruleset tooling — server65 repo set

Cross-repo scripts that manage and monitor the `server65-default-branch-gates`
ruleset across 14 `appolon1908-hue` repositories. Everything talks to GitHub via
`gh api`; nothing is tied to a particular clone.

Requires `gh` authenticated with `repo` + `workflow` scope, and Python 3 (plus
PyYAML for `audit.py` / `jobifs.py`).

Last verified: **2026-09-09**.

## Read this first: three ruleset names are in play

This toolkit originally used the name `AI automated production gates`. That name
is **also** used by an ad-hoc process outside this toolkit. Because both matched
rulesets by name, each silently overwrote the other. On 2026-09-03 that left
`N8N` completely ungated for ~5 hours and destroyed `SDK-repository`'s 7
required checks.

| Name | Owner | Targets | Notes |
|---|---|---|---|
| `server65-default-branch-gates` | **this toolkit** | `~DEFAULT_BRANCH` | Do not rename it back. |
| `AI automated production gates` | ad-hoc, unidentified | `~DEFAULT_BRANCH` | 0 approvals, no checks. Not in any committed code. |
| `AI automated production branch gates` | `Middleware-/.github/workflows/portfolio-production-ruleset-apply.yml` | `refs/heads/production` only | Inert on the 13 repos with no `production` branch. |

Nothing in any repo's committed code deletes a ruleset. The deletions and
rewrites observed on 2026-09-03 were direct API calls from something holding
`Administration: write` — most likely the `CODESTRA_REPOSITORY_ADMIN_TOKEN`
fine-grained PAT, whose own documentation says to rotate or remove it after
rollout. User accounts have no audit log API, so the actor could not be
identified.

## Layout

- `rulesetlib.py` — shared helpers.
  - `gh_json_or_none()` returns `None` only for a genuine 404 and raises
    otherwise, so an API outage is never misread as "protection is missing".
  - `find_ruleset()` refuses to guess when two rulesets share a name — the exact
    ambiguity that broke this estate.
  - `compare()` holds the drift logic; unit-tested.
- `policy.json` — the recorded baseline: expected approvals and required checks
  per repo, with notes where a value is deliberate.
- `test_rulesetlib.py` — unit tests, no network:
  `python -m unittest test_rulesetlib -v`

## Drift detection

```bash
python drift-check.py            # report
python drift-check.py --quiet    # only problems
python drift-check.py --refresh  # accept live state as the new baseline
```

Exit codes, so it works as a CI gate rather than only a report:

| code | meaning |
|------|---------|
| 0 | matches baseline |
| 1 | **weakened** — approvals dropped, checks removed, enforcement off, ruleset deleted |
| 2 | changed but not weakened (e.g. a check was added) |
| 3 | could not check (API error, ambiguous ruleset name) |

The weakened/changed split is the point: adding a required check is a deliberate
tightening and should not page anyone, while a dropped approval is what actually
happened on 2026-09-03.

## Applying changes

`apply-checks.py` **defaults to a dry run**, prints a before/after diff, and
warns when a change would remove a required check. `--apply` writes, then reads
the ruleset back to verify.

```bash
python apply-checks.py batch.json          # dry run
python apply-checks.py batch.json --apply  # write
```

## Auditing

- `protection-audit.py` — classic branch protection per repo, beside the
  ruleset's checks.
- `approval-audit.py` — effective approval requirement across all rulesets plus
  classic protection. Answers "can a PR merge here with no human review?"
- `reconcile-diff.py` — ruleset checks vs classic checks, per repo.
- `ruleset-inventory.py` — every ruleset on every repo, with last-updated.
- `audit.py <repo>...` — per workflow: does it trigger on `pull_request`, is that
  trigger path/branch-filtered, and what are its job names.
- `jobifs.py <repo> <workflow>` — job-level `if:` conditions.

**Run `audit.py` and `jobifs.py` before requiring any check.** A required context
that never runs on a PR leaves that PR blocked at "Expected" forever. Two live
examples caught this way: `Odoo`'s `Validate Odoo main push` is
`if: github.event_name == 'push'`, and `social.codestra.co`'s image build is
tag-only. Both appear in the check-run list like any other check.

## Classic branch protection also applies

Rulesets are not the whole story: 11 of the 14 repos also have *classic* branch
protection on their default branch, a separate system applying on top.

`required_signatures` is enabled on `codestra-production-platform`, `Kong` and
`Caddy`, all with `enforce_admins: true`. **Commits created through the GitHub
REST API are unsigned and can never merge there** — they must be made via the
GitHub web UI or locally with a signing key. This blocked PR #232 for a day.
`N8N`, `Keycloak` and `Codesrea-Social-` have no classic protection at all.

Four repos also carry their own, separately-managed rulesets that are stronger
than this toolkit's — `middleware-main-production-authority`, `Protect main
without bypass` (N8N), `Bootstrap protect main` (Keycloak), `Protect main`
(Caddy). **Do not delete these.**

## codestra-production-platform

Every one of this repo's `pull_request` workflows is path-filtered, so no context
ran on every PR and none could be marked required. Six different workflows emit a
job called `validate`.

`production-merge-gate.yml` solves this: an unfiltered gate that runs on every
PR, aggregates all other check runs and commit statuses on the head commit, and
fails if any failed (`skipped`/`neutral` count as passing). `test-gate-logic.sh`
unit-tests its classification logic.

**Status: landed.** PR #232 merged 2026-09-04; the workflow is on
`release/production-activation` and `production-gate` is a required check.

The repo now runs a **checks-only policy**: `approvals=0`, gated by four required
checks (`checks-only-policy`, `diagnose`, `production-gate`, `validate`) plus a
`required_signatures` rule. `policy.json` records this deliberately — raising
approvals there is a policy decision, not a fix.

## Historical scripts

- `rollout-rulesets.sh` — original rollout: auto-merge + ruleset on all 14.
- `rename-rulesets.py` — one-time migration off the colliding name. Already run.
- `open-pr.py` — **pushes**. Created branch `ci/production-merge-gate` and PR
  #232. Produces unsigned commits, which cannot merge to a signature-protected
  branch.
- `batch1.json`, `batch2.json`, `batch3-production-gate.json` — the check sets
  applied, kept for reference.
- `n8n-protect-main-without-bypass.json` — payload used to restore N8N's deleted
  ruleset on 2026-09-03.

## Known follow-ups

- The actor that deleted `N8N`'s ruleset and rewrote others is still
  unidentified. Check installed GitHub Apps for `Administration: write`, and
  whether `CODESTRA_REPOSITORY_ADMIN_TOKEN` is still live.
- On 2026-09-03, three PRs (#38, #46, #47 — ~47 files, ~3,700 added lines)
  merged to `N8N` `main` with no approving review while protection was absent.
  Diffs reviewed and found benign; saved under
  `~/CodestraTools/n8n-unreviewed-merges-2026-09-03/`.
- `drift-check.py` is not scheduled anywhere. It only catches a regression if
  something runs it.
