"""Tests for the pure logic in rulesetlib: summarise() and compare().

Run: python -m unittest test_rulesetlib -v
No network access; these exercise the decision logic only.
"""
import unittest

from rulesetlib import compare, summarise


def ruleset(approvals=1, checks=(), enforcement="active"):
    rules = [
        {"type": "deletion"},
        {"type": "pull_request",
         "parameters": {"required_approving_review_count": approvals}},
    ]
    if checks:
        rules.append({
            "type": "required_status_checks",
            "parameters": {"required_status_checks": [{"context": c} for c in checks]},
        })
    return {"id": 1, "updated_at": "2026-09-08T00:00:00Z",
            "enforcement": enforcement, "rules": rules}


class TestSummarise(unittest.TestCase):
    def test_missing_ruleset(self):
        s = summarise(None)
        self.assertFalse(s["present"])
        self.assertEqual(s["approvals"], 0)
        self.assertEqual(s["checks"], [])

    def test_extracts_approvals_and_checks(self):
        s = summarise(ruleset(approvals=2, checks=["b", "a"]))
        self.assertTrue(s["present"])
        self.assertEqual(s["approvals"], 2)
        self.assertEqual(s["checks"], ["a", "b"], "checks must be sorted")

    def test_no_status_check_rule(self):
        self.assertEqual(summarise(ruleset(approvals=1))["checks"], [])


class TestCompare(unittest.TestCase):
    def verdict(self, expected, actual):
        return compare(expected, summarise(actual))[0]

    # --- the alarm cases -------------------------------------------------
    def test_missing_is_weakened(self):
        self.assertEqual(self.verdict({"approvals": 1, "checks": []}, None), "weakened")

    def test_approvals_dropped_is_weakened(self):
        # This is exactly what happened to N8N and Middleware- on 2026-09-03.
        self.assertEqual(
            self.verdict({"approvals": 1, "checks": []}, ruleset(approvals=0)),
            "weakened")

    def test_check_removed_is_weakened(self):
        # SDK-repository lost 7 checks this way.
        self.assertEqual(
            self.verdict({"approvals": 1, "checks": ["a", "b"]},
                         ruleset(approvals=1, checks=["a"])),
            "weakened")

    def test_disabled_enforcement_is_weakened(self):
        self.assertEqual(
            self.verdict({"approvals": 1, "checks": []},
                         ruleset(approvals=1, enforcement="disabled")),
            "weakened")

    def test_weakened_wins_over_simultaneous_addition(self):
        v, reasons = compare({"approvals": 1, "checks": ["a"]},
                             summarise(ruleset(approvals=1, checks=["b"])))
        self.assertEqual(v, "weakened")
        self.assertTrue(any("removed" in r for r in reasons))
        self.assertTrue(any("added" in r for r in reasons))

    # --- the non-alarm cases --------------------------------------------
    def test_exact_match_is_ok(self):
        self.assertEqual(
            self.verdict({"approvals": 1, "checks": ["a", "b"]},
                         ruleset(approvals=1, checks=["b", "a"])),
            "ok", "check order must not matter")

    def test_added_check_is_changed_not_weakened(self):
        # Infustruction-repo added orchestrator-contract on 2026-09-08.
        # A deliberate tightening must not read as an alarm.
        self.assertEqual(
            self.verdict({"approvals": 1, "checks": ["a"]},
                         ruleset(approvals=1, checks=["a", "b"])),
            "changed")

    def test_more_approvals_is_changed_not_weakened(self):
        self.assertEqual(
            self.verdict({"approvals": 1, "checks": []}, ruleset(approvals=2)),
            "changed")

    def test_baseline_of_zero_approvals_tolerates_zero(self):
        # codestra-production-platform is deliberately checks-only.
        self.assertEqual(
            self.verdict({"approvals": 0, "checks": ["x"]},
                         ruleset(approvals=0, checks=["x"])),
            "ok")

    def test_reasons_are_reported(self):
        _, reasons = compare({"approvals": 2, "checks": ["a"]},
                             summarise(ruleset(approvals=0, checks=[])))
        self.assertEqual(len(reasons), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
