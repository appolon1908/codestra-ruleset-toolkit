"""Create the gate branch, commit the workflow, and open the PR."""
import base64
import json
import subprocess

REPO = "appolon1908-hue/codestra-production-platform"
BASE = "release/production-activation"
BRANCH = "ci/production-merge-gate"
PATH = ".github/workflows/production-merge-gate.yml"
LOCAL = "production-merge-gate.yml"

COMMIT_MSG = """ci: add unfiltered production merge gate

Every pull_request workflow in this repository is path-filtered, so no single
check runs on every PR and none can serve as a required status check: a
required context that never runs leaves the PR blocked at "Expected"
indefinitely.

This adds a deliberately unfiltered gate that runs on every PR and aggregates
the other check runs and commit statuses on the head commit, failing if any of
them failed. Skipped and neutral conclusions count as passing, so a
path-filtered job that correctly did not apply does not block the merge.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"""

PR_BODY = """## Why

Every `pull_request` workflow in this repository is path-filtered. That means
no single check runs on every PR, so none of them can be marked as a required
status check — a required context that never runs sits at "Expected" and blocks
the PR forever. The practical effect today is that **a PR whose checks failed
can still be merged**, because nothing is required.

This is the one repo in the `AI automated production gates` rollout that could
not be given required status checks for this reason.

## What this does

Adds `production-gate`: an unfiltered `pull_request` job that runs on every PR,
waits for all other check runs and commit statuses on the head commit, and
fails if any of them failed.

- `skipped` / `neutral` count as passing, so a path-filtered job that correctly
  did not apply does not block the merge
- 60s grace period before evaluating, so it cannot pass while a sibling
  workflow is still queued
- `filter=latest` on the check-runs query, so a failure that was re-run and
  fixed does not wedge the gate
- No third-party actions; read-only token scopes; 35 minute timeout

## Follow-up (not in this PR)

Once merged, `production-gate` should be added as a required status check on
the `AI automated production gates` ruleset. It must be done in that order —
requiring the context before the workflow exists on the base branch would block
every open PR.

Note that open PRs will need a branch update to pick up the new workflow, since
adding it to the base branch does not retroactively run it.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"""


def gh(*args, stdin=None):
    p = subprocess.run(["gh", *args], capture_output=True, text=True, input=stdin)
    if p.returncode:
        raise RuntimeError(p.stderr.strip()[:400])
    return p.stdout


base_sha = json.loads(gh("api", f"repos/{REPO}/git/ref/heads/{BASE}"))["object"]["sha"]
print(f"base {BASE} @ {base_sha}")

gh("api", "--method", "POST", f"repos/{REPO}/git/refs", "--input", "-", "--silent",
   stdin=json.dumps({"ref": f"refs/heads/{BRANCH}", "sha": base_sha}))
print(f"created branch {BRANCH}")

content = base64.b64encode(open(LOCAL, "rb").read()).decode()
commit = json.loads(gh("api", "--method", "PUT", f"repos/{REPO}/contents/{PATH}",
                       "--input", "-",
                       stdin=json.dumps({"message": COMMIT_MSG, "content": content,
                                         "branch": BRANCH})))
print(f"committed {PATH} @ {commit['commit']['sha'][:8]}")

pr = json.loads(gh("api", "--method", "POST", f"repos/{REPO}/pulls", "--input", "-",
                   stdin=json.dumps({
                       "title": "ci: add unfiltered production merge gate",
                       "head": BRANCH, "base": BASE, "body": PR_BODY})))
print(f"\nPR #{pr['number']}: {pr['html_url']}")
