"""Diff each repo's ruleset required checks against its classic branch
protection checks, so the two systems can be reconciled to one answer."""
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
    branch = gh(f"repos/{OWNER}/{repo}")["default_branch"]

    rs = set()
    for s in gh(f"repos/{OWNER}/{repo}/rulesets") or []:
        if s["name"] != NAME:
            continue
        full = gh(f"repos/{OWNER}/{repo}/rulesets/{s['id']}") or {}
        rs = {c["context"]
              for r in full.get("rules", [])
              if r["type"] == "required_status_checks"
              for c in r["parameters"]["required_status_checks"]}

    prot = gh(f"repos/{OWNER}/{repo}/branches/{branch}/protection")
    has_classic = bool(prot and "message" not in prot)
    cl = set((prot.get("required_status_checks") or {}).get("contexts", [])) if has_classic else set()

    only_classic = sorted(cl - rs)
    only_ruleset = sorted(rs - cl)

    if not has_classic:
        verdict = "no classic protection"
    elif not only_classic and not only_ruleset:
        verdict = "MATCH"
    elif not only_classic:
        verdict = "ruleset is superset (ok)"
    else:
        verdict = "GAP: classic requires checks the ruleset does not"

    print(f"{repo}")
    print(f"  {verdict}")
    if only_classic:
        print(f"    only in classic : {only_classic}")
    if only_ruleset:
        print(f"    only in ruleset : {only_ruleset}")
