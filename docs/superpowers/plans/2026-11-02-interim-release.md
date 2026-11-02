# Interim release implementation plan

Goal: replace the unfinished custom-controller dependency with genuine repository validation, preserving other release protections.

Authority: user request, 2026-11-02, “implementate, unblock all”. Portfolio parent: PAS-233. Existing toolkit PRs #3 and #4 are separate and untouched. This branch owns only the new migration tool.

Design: give validation its own context, `codestra/repository-validation`. Start with Backstage's existing test suite. Replace only `codestra-control-plane` and `codestra/control-plane` in explicitly selected rulesets after fresh passing evidence exists. Never issue either controller status or claim controller certification. Do not alter any other rule, bypass actor, condition, enforcement, security check, review, deployment switch or signature policy.

Alternative considered: issuing controller-named statuses from a new generic workflow would obscure the distinction between validation and controller certification. Deleting entire rulesets would discard unrelated protections. Neither is used.

Tasks:
- [x] Implement and test a dry-run migration planner with exact ruleset snapshots, replacement check publisher binding, fresh evidence, rollback payloads and readback verification.
- [x] Implement Backstage's unfiltered repository gate, dependent on its existing validation job. Prove it fails for failure, cancellation, skip, unknown and empty results.
- [ ] Publish isolated PRs, run hosted validation, obtain independent review, and apply only through an administration-capable connection.

Review focus: stale/ambiguous checks, empty replacement sets, unrelated rule loss, concurrent settings changes, partial API failure. Exercise each in the migration tests.

Constraints: no force push, no main development, no production activation. Never call an unresolved repository migrated. Current publication laptop is authenticated as ingtrader21-spec with pull=true, push=false, admin=false for Backstage. GitHub connector has no administration write operation.

Execution record: toolkit PR #7, Backstage PR #9. Independent review accepted unmerged publication; seven suggested safety regressions were added. Hosted push and PR runs succeeded for both initial revisions. The initial duplicate-run policy required every matching result to be fresh; the follow-up policy below supersedes that freshness requirement. Regression reproduced the prior rejection and then passed, with the full 33-test suite green. The live Backstage dry-run preview is in docs/backstage-migration-preview-20261102.json. No settings mutation, merge or activation has occurred. Existing owners and PRs are preserved.

Follow-up evidence policy: for each required context and publisher app, inspect all returned attempts (`filter=all`) and refuse incomplete pagination. Every matching attempt must have the exact requested SHA, be completed, conclude success, and have a completion timestamp no later than the current time. At least one matching successful completion must be within the preceding hour, inclusive. Older successful attempts may coexist with that fresh proof: rerunning an unchanged successful source revision should refresh its evidence without making the old success a blocker. Old-success-only evidence still fails. Any old or current failure, skip, cancellation, pending run, wrong SHA, invalid timestamp or future timestamp still blocks even alongside a fresh success. Plan expiry, publisher binding, concurrent-change checks, rollback safeguards and preservation of all other rules remain unchanged.
