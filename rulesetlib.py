"""Shared helpers for the ruleset toolkit.

Every script previously carried its own copy of OWNER, the repo list and a gh()
wrapper that silently returned None on failure. That made an API error
indistinguishable from a missing ruleset, so a rate limit or an auth problem
would be reported as "protection is gone". This module centralises both.
"""
from __future__ import annotations

import json
import os
import subprocess

POLICY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "policy.json")


class GhError(RuntimeError):
    """A gh invocation failed. Distinct from 'the resource does not exist'."""


class GhNotFound(GhError):
    """The resource does not exist (HTTP 404)."""


def gh(*args: str, stdin: str | None = None) -> str:
    """Run gh, raising on failure. Never returns partial output silently."""
    proc = subprocess.run(
        ["gh", *args], capture_output=True, text=True, input=stdin
    )
    if proc.returncode:
        err = (proc.stderr or proc.stdout).strip()
        if "404" in err or "Not Found" in err:
            raise GhNotFound(err[:300])
        raise GhError(err[:300])
    return proc.stdout


def gh_json(path: str):
    """GET an API path and parse JSON."""
    return json.loads(gh("api", path))


def gh_json_or_none(path: str):
    """GET an API path, returning None only for a genuine 404.

    Any other failure propagates, so callers cannot mistake an outage for an
    absent resource.
    """
    try:
        return gh_json(path)
    except GhNotFound:
        return None


def load_policy(path: str = POLICY_PATH) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def save_policy(policy: dict, path: str = POLICY_PATH) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(policy, handle, indent=2, sort_keys=False)
        handle.write("\n")


def find_ruleset(owner: str, repo: str, name: str) -> dict | None:
    """Return the single ruleset with this name.

    Raises if more than one carries the name. Duplicate names are exactly how
    this estate broke before: two writers, one name, each silently replacing
    the other. Refusing to guess is the point.
    """
    matches = [s for s in gh_json(f"repos/{owner}/{repo}/rulesets") if s["name"] == name]
    if not matches:
        return None
    if len(matches) > 1:
        ids = ", ".join(str(m["id"]) for m in matches)
        raise GhError(f"{repo}: {len(matches)} rulesets named {name!r} (ids: {ids})")
    return gh_json(f"repos/{owner}/{repo}/rulesets/{matches[0]['id']}")


def summarise(ruleset: dict | None) -> dict:
    """Reduce a ruleset to the fields the policy cares about."""
    if ruleset is None:
        return {"present": False, "approvals": 0, "checks": []}
    approvals = 0
    checks: list[str] = []
    for rule in ruleset.get("rules", []):
        if rule["type"] == "pull_request":
            approvals = rule["parameters"]["required_approving_review_count"]
        elif rule["type"] == "required_status_checks":
            checks += [c["context"]
                       for c in rule["parameters"]["required_status_checks"]]
    return {
        "present": True,
        "approvals": approvals,
        "checks": sorted(checks),
        "id": ruleset.get("id"),
        "updated_at": ruleset.get("updated_at"),
        "enforcement": ruleset.get("enforcement"),
    }


def compare(expected: dict, actual: dict) -> tuple[str, list[str]]:
    """Compare a baseline entry against live state.

    Returns (verdict, reasons) where verdict is one of:
      "ok"       - matches the baseline
      "weakened" - protection was reduced; this is the alarm case
      "changed"  - differs, but not in a weakening direction

    Distinguishing these two matters: adding a required check is a deliberate
    improvement and must not page anyone, while dropping an approval or a check
    is what happened when this estate was silently rewritten.
    """
    reasons: list[str] = []
    weakened = False

    if not actual["present"]:
        return "weakened", ["ruleset is missing"]

    exp_appr = expected.get("approvals", 0)
    act_appr = actual["approvals"]
    if act_appr < exp_appr:
        weakened = True
        reasons.append(f"approvals {exp_appr} -> {act_appr}")
    elif act_appr > exp_appr:
        reasons.append(f"approvals {exp_appr} -> {act_appr} (stricter)")

    exp_checks = set(expected.get("checks", []))
    act_checks = set(actual["checks"])
    removed = sorted(exp_checks - act_checks)
    added = sorted(act_checks - exp_checks)
    if removed:
        weakened = True
        reasons.append(f"checks removed: {removed}")
    if added:
        reasons.append(f"checks added: {added}")

    if actual.get("enforcement") not in (None, "active"):
        weakened = True
        reasons.append(f"enforcement={actual['enforcement']}")

    if weakened:
        return "weakened", reasons
    if reasons:
        return "changed", reasons
    return "ok", []
