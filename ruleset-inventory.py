"""Full inventory of every ruleset on every repo in the set, with required
checks and last-updated time. Use this to detect concurrent automation
replacing or renaming rulesets."""
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


for repo in REPOS:
    sets = gh(f"repos/{OWNER}/{repo}/rulesets") or []
    print(f"\n{repo}  ({len(sets)} ruleset(s))")
    for s in sets:
        d = gh(f"repos/{OWNER}/{repo}/rulesets/{s['id']}") or {}
        checks = [c["context"]
                  for r in d.get("rules", [])
                  if r["type"] == "required_status_checks"
                  for c in r["parameters"]["required_status_checks"]]
        print(f"  id={d.get('id')}  {d.get('name')!r}  enf={d.get('enforcement')}")
        print(f"     updated={d.get('updated_at')}")
        print(f"     checks({len(checks)})={checks}")
