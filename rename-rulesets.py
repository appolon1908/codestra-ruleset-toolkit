"""Move this toolkit's ruleset to a distinct name so it stops colliding with
the ad-hoc "AI automated production gates" rulesets created outside it.

For each repo:
  - if a ruleset already exists under NEW_NAME, update it in place;
  - else if one exists under OLD_NAME *and it carries our config* (>=1 required
    approval), rename it by PUTting the same rules under NEW_NAME;
  - else create a fresh one under NEW_NAME. An OLD_NAME ruleset with 0 required
    approvals is someone else's and is left untouched.
"""
import json
import subprocess
import sys

OWNER = "appolon1908-hue"
OLD_NAME = "AI automated production gates"
NEW_NAME = "server65-default-branch-gates"

# Required status checks per repo, verified to run unfiltered on pull_request.
CHECKS = {
    "Kong": ["validate", "kong-config", "security"],
    "Codestra-AI": ["unit-and-contract", "postgres-certification", "container-build"],
    "Codestra-Marketing-": ["unit-and-contract", "postgres-certification", "container-build"],
    "Codesrea-Social-": ["unit-and-contract", "postgres-certification"],
    # container-build added to match classic protection, which already requires it
    "Codestra-Communication-CC": ["unit-and-contract", "postgres-certification", "container-build"],
    "Odoo": ["Validate Odoo source head", "Validate Odoo merge result",
             "Test Odoo 19 and PostgreSQL runtime", "secret-and-source-security",
             "dependency-review"],
    "social.codestra.co": ["Backend policy, migration, test, and build",
                           "Backend container build and hardening"],
    "Infustruction-repo": ["validate", "validate-source", "validate-merge-result"],
    "SDK-repository": ["secret-scan", "moneybee-python-connectors", "verify",
                       "compatibility", "validate", "certify", "generate"],
    # codestra-production-platform: none until PR #232 lands production-gate.
    # Middleware-/N8N/Keycloak/Caddy: covered by their own stronger rulesets.
}

REPOS = [
    "codestra-production-platform", "Middleware-", "Odoo", "N8N", "Kong",
    "Keycloak", "Caddy", "Codestra-AI", "Codesrea-Social-",
    "Codestra-Communication-CC", "Codestra-Marketing-", "Infustruction-repo",
    "SDK-repository", "social.codestra.co",
]

APPLY = "--apply" in sys.argv


def gh(*args, stdin=None):
    p = subprocess.run(["gh", *args], capture_output=True, text=True, input=stdin)
    if p.returncode:
        raise RuntimeError(p.stderr.strip()[:300])
    return p.stdout


def payload(repo):
    rules = [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {"type": "required_linear_history"},
        {"type": "pull_request", "parameters": {
            "required_approving_review_count": 1,
            "dismiss_stale_reviews_on_push": True,
            "require_code_owner_review": False,
            "require_last_push_approval": False,
            "required_review_thread_resolution": True,
            "allowed_merge_methods": ["squash"],
        }},
    ]
    checks = CHECKS.get(repo)
    if checks:
        rules.append({"type": "required_status_checks", "parameters": {
            "strict_required_status_checks_policy": True,
            "do_not_enforce_on_create": False,
            "required_status_checks": [{"context": c} for c in checks],
        }})
    return {
        "name": NEW_NAME, "target": "branch", "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": rules,
    }


for repo in REPOS:
    sets = json.loads(gh("api", f"repos/{OWNER}/{repo}/rulesets"))
    new = next((s for s in sets if s["name"] == NEW_NAME), None)
    old = next((s for s in sets if s["name"] == OLD_NAME), None)

    old_is_ours = False
    if old:
        d = json.loads(gh("api", f"repos/{OWNER}/{repo}/rulesets/{old['id']}"))
        for r in d["rules"]:
            if r["type"] == "pull_request":
                old_is_ours = r["parameters"]["required_approving_review_count"] >= 1

    body = payload(repo)
    n = len(CHECKS.get(repo, []))

    if new:
        action, target = "update-in-place", new["id"]
    elif old and old_is_ours:
        action, target = "rename", old["id"]
    else:
        action, target = "create", None

    note = ""
    if old and not old_is_ours:
        note = f"  (left foreign ruleset {old['id']} with 0 approvals alone)"

    print(f"{repo:<30} {action:<16} checks={n}{note}")
    if not APPLY:
        continue

    if target:
        gh("api", "--method", "PUT", f"repos/{OWNER}/{repo}/rulesets/{target}",
           "--input", "-", "--silent", stdin=json.dumps(body))
    else:
        gh("api", "--method", "POST", f"repos/{OWNER}/{repo}/rulesets",
           "--input", "-", "--silent", stdin=json.dumps(body))
