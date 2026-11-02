"""Process-level regressions for the shell harness; no network access."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


class TestGateHarness(unittest.TestCase):
    def run_harness(self, source):
        with tempfile.TemporaryDirectory(prefix="toolkit-harness-") as directory:
            script = Path(directory) / "test-gate-logic.sh"
            script.write_text(source, encoding="utf-8")
            return subprocess.run(
                ["bash", str(script)], capture_output=True, text=True,
                timeout=30, check=False,
            )

    def test_matching_expectations_exit_zero(self):
        result = self.run_harness((ROOT / "test-gate-logic.sh").read_text())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("  FAIL ", result.stdout)

    def test_early_mismatch_exits_nonzero_even_when_last_case_passes(self):
        source = (ROOT / "test-gate-logic.sh").read_text()
        original = 't "no checks at all (all path-filtered out)" "PASS" ""'
        self.assertEqual(source.count(original), 1, "fixture anchor changed")
        source = source.replace(original, original.replace('"PASS"', '"FAIL"'), 1)
        result = self.run_harness(source)
        self.assertIn("  FAIL no checks at all", result.stdout)
        self.assertIn("  ok   mixed: skipped + running", result.stdout)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_last_mismatch_exits_nonzero(self):
        source = (ROOT / "test-gate-logic.sh").read_text()
        original = 't "mixed: skipped + running" "WAIT"'
        self.assertEqual(source.count(original), 1, "fixture anchor changed")
        source = source.replace(original, original.replace('"WAIT"', '"PASS"'), 1)
        result = self.run_harness(source)
        self.assertIn("  FAIL mixed: skipped + running", result.stdout)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
