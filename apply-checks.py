"""Set the required_status_checks rule on the toolkit's ruleset.

Usage:
  python apply-checks.py batch.json            # dry run, prints the diff
  python apply-checks.py batch.json --apply    # write it

batch.json is {"repo": ["context", ...]}.

This edits production branch protection, so it defaults to a dry run and
refuses to act when the target is ambiguous.
"""
import json
import sys

from rulesetlib import GhError, find_ruleset, gh, load_policy, summarise


def build_payload(current, checks):
    """Replace only the required_status_checks rule, preserving everything else."""
    rules = [r for r in current["rules"] if r["type"] != "required_status_checks"]
    if checks:
        rules.append({
            "type": "required_status_checks",
            "parameters": {
                "strict_required_status_checks_policy": True,
                "do_not_enforce_on_create": False,
                "required_status_checks": [{"context": c} for c in checks],
            },
        })
    return {
        "name": current["name"],
        "target": current["target"],
        "enforcement": current["enforcement"],
        "bypass_actors": current.get("bypass_actors", []),
        "conditions": current["conditions"],
        "rules": rules,
    }


def main(argv):
    if not argv or argv[0].startswith("--"):
        print(__doc__)
        return 2

    batch_path, apply = argv[0], "--apply" in argv
    policy = load_policy()
    owner, name = policy["owner"], policy["ruleset_name"]

    with open(batch_path, encoding="utf-8") as handle:
        targets = json.load(handle)

    failures = 0
    for repo, checks in targets.items():
        try:
            current = find_ruleset(owner, repo, name)
            if current is None:
                raise GhError(f"no ruleset named {name!r} on this repo")

            before = summarise(current)["checks"]
            after = sorted(checks)
            removing = sorted(set(before) - set(after))

            print(f"{repo}")
            print(f"    before: {before or '(none)'}")
            print(f"    after : {after or '(none)'}")
            if removing:
                # Surfaced loudly: dropping a required check is the exact
                # failure mode this toolkit exists to detect.
                print(f"    WARNING removes {removing}")

            if not apply:
                continue

            gh("api", "--method", "PUT",
               f"repos/{owner}/{repo}/rulesets/{current['id']}",
               "--input", "-", "--silent",
               stdin=json.dumps(build_payload(current, checks)))

            verify = summarise(find_ruleset(owner, repo, name))["checks"]
            if verify != after:
                print(f"    FAILED verification: got {verify}")
                failures += 1
            else:
                print("    applied and verified")
        except (GhError, OSError, KeyError) as exc:
            print(f"{repo}\n    FAILED: {exc}")
            failures += 1

    if not apply:
        print("\nDry run. Re-run with --apply to write these changes.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
