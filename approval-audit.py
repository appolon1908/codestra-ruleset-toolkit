"""Effective approval requirement per repo: the strongest approval count across
all active rulesets, plus classic protection. Answers 'can a PR merge here with
zero human review?'"""
import json

OWNER = "appolon1908-hue"
REPOS = [
    "codestra-production-platform", "Middleware-", "Odoo", "N8N", "Kong",
    "Keycloak", "Caddy", "Codestra-AI", "Codesrea-Social-",
    "Codestra-Communication-CC", "Codestra-Marketing-", "Infustruction-repo",
    "SDK-repository", "social.codestra.co",
]


# Shared helper: returns None only for a real 404 and raises on any other
# failure, so an API outage cannot be misread as "protection is missing".
from rulesetlib import gh_json_or_none as gh


print(f"{'repo':<30} {'ruleset_max':>11} {'classic':>8} {'checks':>7}  verdict")
for repo in REPOS:
    branch = gh(f"repos/{OWNER}/{repo}")["default_branch"]

    best = 0
    total_checks = 0
    for s in gh(f"repos/{OWNER}/{repo}/rulesets") or []:
        d = gh(f"repos/{OWNER}/{repo}/rulesets/{s['id']}") or {}
        for r in d.get("rules", []):
            if r["type"] == "pull_request":
                best = max(best, r["parameters"]["required_approving_review_count"])
            if r["type"] == "required_status_checks":
                total_checks += len(r["parameters"]["required_status_checks"])

    prot = gh(f"repos/{OWNER}/{repo}/branches/{branch}/protection")
    has_classic = bool(prot and "message" not in prot)
    cl_appr = ((prot.get("required_pull_request_reviews") or {})
               .get("required_approving_review_count")) if has_classic else None
    cl_checks = len((prot.get("required_status_checks") or {}).get("contexts", [])) if has_classic else 0

    eff_appr = max(best, cl_appr or 0)
    eff_checks = total_checks + cl_checks
    verdict = "OK" if (eff_appr >= 1 or eff_checks > 0) else "*** UNGATED ***"
    if eff_appr == 0:
        verdict += "  (no approval required)"

    print(f"{repo:<30} {best:>11} {str(cl_appr):>8} {eff_checks:>7}  {verdict}")
