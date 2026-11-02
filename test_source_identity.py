"""Offline identity checks; parse audit entrypoints without executing them."""
import ast
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
OWNER = "appolon1908"
AUDIT_SCRIPTS = (
    "approval-audit.py", "audit.py", "jobifs.py", "protection-audit.py",
    "reconcile-diff.py", "ruleset-inventory.py",
)


class TestSourceIdentity(unittest.TestCase):
    def record(self):
        return json.loads((ROOT / "monitoring-integration.v1.json").read_text())

    def test_policy_uses_canonical_owner(self):
        policy = json.loads((ROOT / "policy.json").read_text())
        self.assertEqual(policy["owner"], OWNER)

    def test_audit_entrypoints_use_canonical_owner_without_running_them(self):
        for filename in AUDIT_SCRIPTS:
            with self.subTest(script=filename):
                tree = ast.parse((ROOT / filename).read_text(), filename=filename)
                owners = [
                    ast.literal_eval(node.value)
                    for node in tree.body
                    if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == "OWNER"
                            for target in node.targets)
                ]
                self.assertEqual(owners, [OWNER])

    def test_monitoring_self_identity_is_canonical(self):
        self.assertEqual(self.record()["repository"], OWNER + "/codestra-ruleset-toolkit")

    def test_monitoring_controller_identity_is_canonical(self):
        self.assertEqual(self.record()["controller_repository"], OWNER + "/Middleware-")

    def test_runtime_activation_remains_disabled(self):
        record = self.record()
        self.assertIs(record["activation_enabled"], False)
        self.assertIs(record["runtime_onboarding_allowed"], False)
        self.assertEqual(record["runtime_coverage"], "unverified")
        self.assertEqual(record["service_ids"], [])

    def test_immutable_historical_contract_pins_are_preserved(self):
        record = self.record()
        self.assertEqual(record["design_url"],
            "https://github.com/appolon1908-hue/Infustruction-repo/blob/"
            "afeea11b86d296874ec12ce6e8615400240bc72f/INTEGRATED-MONITORING-DESIGN.md")
        self.assertEqual(record["api_contract_url"],
            "https://raw.githubusercontent.com/appolon1908-hue/Middleware-/"
            "cedaa23b89f84f365ae6789413411c3f01516952/"
            "contracts/observability/integrated-monitoring.openapi.json")


if __name__ == "__main__":
    unittest.main()
