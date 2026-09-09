"""Compare live ruleset state against the recorded baseline in policy.json.

Exit codes (so this is usable as a CI gate, not just a report):
  0  everything matches the baseline
  1  protection was WEAKENED somewhere - approvals dropped, checks removed,
     enforcement disabled, or the ruleset deleted outright
  2  differences that are not weakenings (e.g. a check was added)
  3  the check could not run (API error, ambiguous ruleset name)

Usage:
  python drift-check.py                    # check, print a report
  python drift-check.py --quiet            # only print problems
  python drift-check.py --refresh          # rewrite policy.json from live state
  python drift-check.py --policy FILE      # use an alternate baseline file
"""
import sys

from rulesetlib import (
    POLICY_PATH, GhError, compare, find_ruleset, load_policy, save_policy,
    summarise,
)


def main(argv):
    refresh = "--refresh" in argv
    quiet = "--quiet" in argv

    policy_path = POLICY_PATH
    if "--policy" in argv:
        policy_path = argv[argv.index("--policy") + 1]

    policy = load_policy(policy_path)
    owner = policy["owner"]
    name = policy["ruleset_name"]
    repos = policy["repos"]

    weakened, changed, errors = [], [], []

    for repo, expected in repos.items():
        try:
            actual = summarise(find_ruleset(owner, repo, name))
        except GhError as exc:
            errors.append(repo)
            print(f"  ERROR    {repo:<30} {exc}")
            continue

        if refresh:
            expected_new = {"approvals": actual["approvals"],
                            "checks": actual["checks"]}
            if "note" in expected:
                expected_new["note"] = expected["note"]
            repos[repo] = expected_new
            print(f"  baseline {repo:<30} approvals={actual['approvals']} "
                  f"checks={len(actual['checks'])}")
            continue

        verdict, reasons = compare(expected, actual)
        if verdict == "weakened":
            weakened.append(repo)
        elif verdict == "changed":
            changed.append(repo)

        if quiet and verdict == "ok":
            continue
        flag = {"ok": "ok      ", "changed": "CHANGED ", "weakened": "WEAKENED"}[verdict]
        detail = "; ".join(reasons)
        print(f"  {flag} {repo:<30} approvals={actual['approvals']} "
              f"checks={len(actual['checks'])} updated={actual.get('updated_at')}"
              + (f"\n           -> {detail}" if detail else ""))

    if refresh:
        save_policy(policy, policy_path)
        print(f"\nbaseline written to {policy_path} ({len(repos)} repos)")
        return 0

    print()
    if errors:
        print(f"COULD NOT CHECK {len(errors)} repo(s): {errors}")
        return 3
    if weakened:
        print(f"WEAKENED: {weakened}")
        print("Protection was reduced. Investigate before assuming it was intentional.")
        return 1
    if changed:
        print(f"changed (not weakened): {changed}")
        print("Run --refresh to accept these into the baseline.")
        return 2
    print("no drift")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
