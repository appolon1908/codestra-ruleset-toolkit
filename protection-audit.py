"""Classic branch protection audit.

Rulesets and classic branch protection are separate systems and both apply.
This reports the classic protection on each repo's default branch alongside the
ruleset's required checks, so conflicts and hidden gates are visible.
"""
import json

OWNER = "appolon1908-hue"
NAME = "server65-default-branch-gates"

REPOS = [
    "codestra-production-platform", "Middleware-", "Odoo", "N8N", "Kong",
    "Keycloak", "Caddy", "Codestra-AI", "Codesrea-Social-",
    "Codestra-Communication-CC", "Codestra-Marketing-", "Infustruction-repo",
    "SDK-repository", "social.codestra.co",
]


# Shared helper: returns None only for a real 404 and raises on any other
# failure, so an API outage cannot be misread as "protection is missing".
from rulesetlib import gh_json_or_none as gh


for repo in REPOS:
    info = gh(f"repos/{OWNER}/{repo}")
    branch = info["default_branch"]
    prot = gh(f"repos/{OWNER}/{repo}/branches/{branch}/protection")

    ruleset_checks = []
    sets = gh(f"repos/{OWNER}/{repo}/rulesets") or []
    for s in sets:
        if s["name"] != NAME:
            continue
        full = gh(f"repos/{OWNER}/{repo}/rulesets/{s['id']}") or {}
        ruleset_checks = [
            c["context"]
            for r in full.get("rules", [])
            if r["type"] == "required_status_checks"
            for c in r["parameters"]["required_status_checks"]
        ]

    print(f"\n{repo}  (default: {branch})")
    print(f"  ruleset required checks : {ruleset_checks or 'none'}")
    if not prot or "message" in prot:
        print("  classic protection      : NONE")
        continue

    sigs = prot.get("required_signatures", {}).get("enabled")
    admins = prot.get("enforce_admins", {}).get("enabled")
    rsc = prot.get("required_status_checks") or {}
    rpr = prot.get("required_pull_request_reviews") or {}
    print(f"  classic protection      : PRESENT")
    print(f"    required_signatures   : {sigs}")
    print(f"    enforce_admins        : {admins}")
    print(f"    linear_history        : {prot.get('required_linear_history',{}).get('enabled')}")
    print(f"    conversation_resolution: {prot.get('required_conversation_resolution',{}).get('enabled')}")
    if rsc:
        print(f"    classic checks (strict={rsc.get('strict')}): {rsc.get('contexts')}")
    if rpr:
        print(f"    approvals required    : {rpr.get('required_approving_review_count')}")
