# Interim repository release policy

The user authorized implementation of the GitHub replacement on 2026-11-02.
This tool replaces only `codestra-control-plane` and `codestra/control-plane`
requirements in explicitly selected, repository-owned branch rulesets. All
other rule payloads are preserved. It neither emits controller statuses nor
claims custom-controller certification or production readiness.

## Prerequisites per repository

1. Review its instructions, active writer ownership, promotion routes and
   deployment workflows. Keep existing implementation branches intact.
2. Install a distinct, unfiltered repository validation gate. Require the real
   tests for that repository; a monitoring metadata check is not a substitute.
   Missing tests, path-filtered workflows and deliberately disabled staging
   jobs need repository-specific work. Do not treat them as migration-ready.
3. Obtain independent review and a successful hosted run on the exact revision.
   Gate changes must be merged through the permitted protected path before
   considering migration complete. Review workflow changes as permission changes.
4. Inventory classic protection, rulesets, environment reviewers and deployment
   authority. This tool changes only rulesets; unresolved classic controller
   requirements or environment policy remain blockers.
5. Serialize administration writers. GitHub ruleset PUT has no compare-and-swap
   guarantee. The tool checks twice, but cannot close the network race itself.

## Plan, apply, verify

Use `gh` authenticated to the owner or an administrator with repository
administration write access. The current GitHub connector has no settings write
tool. The inspected win-laptop account `ingtrader21-spec` has no push/admin
permission on Backstage. Do not extract credentials or reuse a different
person's account to work around that limitation.

Write `checks.json` as an array of the new check's exact name and observed
`integration_id` (GitHub App id). Example, only after verifying the publisher:

```json
[{"context": "codestra/repository-validation", "integration_id": 15368}]
```

```bash
python3 interim_release.py plan appolon1908/Backstage RULESET_ID EXACT_SHA --checks checks.json > plan.json
python3 interim_release.py apply plan.json
python3 interim_release.py apply plan.json --apply --backup-dir /secure/release-backups
```

Planning and applying require at least one successful check run for each
context/publisher on the specified SHA, completed within one hour. When push and
pull-request events both run, every matching run must succeed. Skipped,
cancelled, neutral, absent or stale evidence is rejected. Plans expire
after one hour. Generate a separate plan for each ruleset; inspect every diff.
The apply path validates that its payload is precisely the allowed replacement,
checks live state twice, writes an exclusive rollback record before mutation and
requires exact readback after mutation. Any failure stops that invocation.

The supplied SHA is evidence, not proof that the gate was installed on every
protected branch or that a PR is merge-ready. The operator must verify those
facts and the required independent reviews separately. Checks API responses
with more than 100 runs are rejected rather than silently truncated. No batch
mode invents a replacement mapping for repositories without verified gates.

## Rollback

```bash
python3 interim_release.py rollback /secure/release-backups/RECORD.json
python3 interim_release.py rollback /secure/release-backups/RECORD.json --apply
```

Rollback is allowed only if current settings equal the saved applied payload.
It restores and verifies the entire original writable payload. If any other
administrator changed settings, stop and reconcile manually. Never delete a
ruleset as a shortcut.

## Scope and rollout state

The authoritative starting inventory is `github-interim-release-matrix-20261102.csv`
(120 repositories; 113 dual-controller dependencies). Its assessment is not a
verified per-repository replacement mapping. Backstage is the first explicit
pilot; the toolkit gains offline tests for the migration mechanism. All other
repositories require their own gate and release-path reconciliation. No estate
activation is implied by publishing these PRs.

Existing toolkit PR #4 and other implementation owners are untouched. No merge,
settings mutation, deployment, task/lease fabrication or signing waiver is
performed by this source change.
