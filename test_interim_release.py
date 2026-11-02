import copy
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

try:
    import interim_release as release
except ImportError:
    release = None


NOW = datetime(2026, 11, 2, 14, tzinfo=timezone.utc)
SHA = 'a' * 40
CHECK = {'context': 'codestra/repository-validation', 'integration_id': 15368}


def ruleset():
    return {
        'id': 42, 'name': 'controller-required', 'target': 'branch',
        'source': 'appolon1908/Backstage', 'source_type': 'Repository',
        'enforcement': 'active', 'bypass_actors': [],
        'conditions': {'ref_name': {'include': ['~DEFAULT_BRANCH'], 'exclude': []}},
        'rules': [
            {'type': 'non_fast_forward'},
            {'type': 'pull_request', 'parameters': {'required_approving_review_count': 1}},
            {'type': 'required_status_checks', 'parameters': {
                'strict_required_status_checks_policy': True,
                'required_status_checks': [
                    {'context': 'codestra-control-plane'},
                    {'context': 'security', 'integration_id': 777}]}}]}


def check_run(**overrides):
    result = {'id': 20, 'name': CHECK['context'], 'head_sha': SHA,
              'status': 'completed', 'conclusion': 'success',
              'completed_at': '2026-11-02T13:55:00Z', 'app': {'id': 15368}}
    result.update(overrides)
    return result


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(release, 'migration implementation does not exist yet')

    def test_replaces_only_controller_check_without_mutating_input(self):
        before = ruleset()
        original = copy.deepcopy(before)
        result = release.replacement_payload(before, [CHECK])
        self.assertEqual(before, original)
        self.assertEqual(result['rules'][:2], original['rules'][:2])
        self.assertEqual(result['conditions'], original['conditions'])
        self.assertEqual(result['bypass_actors'], [])
        self.assertEqual(result['rules'][2]['parameters']['required_status_checks'],
                         [CHECK, {'context': 'security', 'integration_id': 777}])

    def test_empty_replacement_refused(self):
        with self.assertRaises(ValueError):
            release.replacement_payload(ruleset(), [])

    def test_controller_names_cannot_be_replacement(self):
        for context in ('codestra-control-plane', 'codestra/control-plane'):
            with self.subTest(context=context), self.assertRaises(ValueError):
                release.replacement_payload(ruleset(), [{'context': context, 'integration_id': 15368}])

    def test_missing_publisher_refused(self):
        with self.assertRaises(ValueError):
            release.replacement_payload(ruleset(), [{'context': 'test'}])

    def test_noncontroller_ruleset_refused(self):
        before = ruleset()
        before['rules'][2]['parameters']['required_status_checks'] = [{'context': 'security'}]
        with self.assertRaises(ValueError):
            release.replacement_payload(before, [CHECK])

    def test_valid_exact_commit_evidence(self):
        release.verify_evidence([check_run()], SHA, [CHECK], NOW)

    def test_missing_failed_skipped_cancelled_and_wrong_sha_refused(self):
        cases = [[], [check_run(conclusion='failure')], [check_run(conclusion='skipped')],
                 [check_run(conclusion='cancelled')], [check_run(status='in_progress')],
                 [check_run(head_sha='b' * 40)], [check_run(app={'id': 123})],
                 [check_run(completed_at='2026-11-01T13:55:00Z')],
                 [check_run(completed_at='2026-11-03T13:55:00Z')]]
        for runs in cases:
            with self.subTest(runs=runs), self.assertRaises(ValueError):
                release.verify_evidence(runs, SHA, [CHECK], NOW)

    def test_duplicate_success_does_not_hide_failure(self):
        with self.assertRaises(ValueError):
            release.verify_evidence([check_run(), check_run(id=21, conclusion='failure')], SHA, [CHECK], NOW)

    def test_push_and_pull_request_successes_for_same_commit_are_accepted(self):
        release.verify_evidence([check_run(), check_run(id=21)], SHA, [CHECK], NOW)

    def test_concurrent_ruleset_change_refused_before_write(self):
        original = ruleset()
        plan = release.make_plan('appolon1908/Backstage', original, [CHECK], SHA,
                                 [check_run()], NOW)
        changed = copy.deepcopy(original)
        changed['rules'][1]['parameters']['required_approving_review_count'] = 2
        calls = []
        def api(method, endpoint, payload=None):
            calls.append(method)
            return changed
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
            release.apply_plan(plan, api, Path(folder), NOW)
        self.assertEqual(calls, ['GET'])

    def test_apply_backs_up_and_reads_back_exact_payload(self):
        original = ruleset()
        plan = release.make_plan('appolon1908/Backstage', original, [CHECK], SHA,
                                 [check_run()], NOW)
        state = copy.deepcopy(original)
        calls = []
        def api(method, endpoint, payload=None):
            nonlocal state
            calls.append((method, endpoint))
            if endpoint.endswith('/check-runs?per_page=100'):
                return {'total_count': 1, 'check_runs': [check_run()]}
            if method == 'PUT':
                state = copy.deepcopy(payload)
            return state
        with tempfile.TemporaryDirectory() as folder:
            backup = release.apply_plan(plan, api, Path(folder), NOW)
            self.assertTrue(backup.exists())
            self.assertEqual(state, plan['after'])
            self.assertEqual(calls[-1], ('GET', 'repos/appolon1908/Backstage/rulesets/42'))

    def test_readback_mismatch_is_failure(self):
        original = ruleset()
        plan = release.make_plan('appolon1908/Backstage', original, [CHECK], SHA,
                                 [check_run()], NOW)
        def api(method, endpoint, payload=None):
            if 'check-runs?' in endpoint:
                return {'total_count': 1, 'check_runs': [check_run()]}
            return original
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(RuntimeError):
            release.apply_plan(plan, api, Path(folder), NOW)

    def test_tampered_plan_cannot_remove_security_rule(self):
        plan = release.make_plan('appolon1908/Backstage', ruleset(), [CHECK], SHA,
                                 [check_run()], NOW)
        plan['after']['rules'] = []
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
            release.apply_plan(plan, lambda *args: self.fail('no network allowed'), Path(folder), NOW)

    def test_second_read_detects_concurrent_change_before_write(self):
        original = ruleset()
        plan = release.make_plan('appolon1908/Backstage', original, [CHECK], SHA, [check_run()], NOW)
        reads = 0
        writes = []
        def api(method, endpoint, payload=None):
            nonlocal reads
            if 'check-runs?' in endpoint:
                return {'total_count': 1, 'check_runs': [check_run()]}
            if method != 'GET':
                writes.append(method)
            reads += 1
            current = copy.deepcopy(original)
            if reads == 2:
                current['enforcement'] = 'disabled'
            return current
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                release.apply_plan(plan, api, Path(folder), NOW)
            self.assertEqual(len(list(Path(folder).glob('*.json'))), 1)
        self.assertEqual(writes, [])

    def test_uncertain_put_retains_backup_and_never_retries_write(self):
        original = ruleset()
        plan = release.make_plan('appolon1908/Backstage', original, [CHECK], SHA, [check_run()], NOW)
        writes = []
        def api(method, endpoint, payload=None):
            if 'check-runs?' in endpoint:
                return {'total_count': 1, 'check_runs': [check_run()]}
            if method == 'PUT':
                writes.append(payload)
                raise TimeoutError('response lost after possible acceptance')
            return original
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(TimeoutError):
                release.apply_plan(plan, api, Path(folder), NOW)
            self.assertEqual(len(list(Path(folder).glob('*.json'))), 1)
        self.assertEqual(writes, [plan['after']])

    def test_incomplete_paginated_evidence_refused(self):
        with self.assertRaises(ValueError):
            release.check_runs(lambda *args: {'total_count': 101, 'check_runs': [check_run()]},
                               'appolon1908/Backstage', SHA)

    def test_existing_different_publisher_is_not_overwritten(self):
        before = ruleset()
        before['rules'][2]['parameters']['required_status_checks'].append(
            {'context': CHECK['context'], 'integration_id': 999})
        with self.assertRaises(ValueError):
            release.replacement_payload(before, [CHECK])

    def test_rollback_restores_original_and_verifies(self):
        plan = release.make_plan('appolon1908/Backstage', ruleset(), [CHECK], SHA, [check_run()], NOW)
        state = copy.deepcopy(plan['after'])
        calls = []
        def api(method, endpoint, payload=None):
            nonlocal state
            calls.append(method)
            if method == 'PUT':
                state = copy.deepcopy(payload)
            return state
        release.rollback(plan, api)
        self.assertEqual(state, plan['before'])
        self.assertEqual(calls, ['GET', 'PUT', 'GET'])

    def test_rollback_never_overwrites_later_admin_change(self):
        plan = release.make_plan('appolon1908/Backstage', ruleset(), [CHECK], SHA, [check_run()], NOW)
        current = copy.deepcopy(plan['after'])
        current['rules'].append({'type': 'deletion'})
        calls = []
        def api(method, endpoint, payload=None):
            calls.append(method)
            return current
        with self.assertRaises(ValueError):
            release.rollback(plan, api)
        self.assertEqual(calls, ['GET'])

    def test_expired_plan_refused_without_network(self):
        plan = release.make_plan('appolon1908/Backstage', ruleset(), [CHECK], SHA, [check_run()], NOW)
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
            release.apply_plan(plan, lambda *args: self.fail('no network allowed'),
                               Path(folder), datetime(2026, 11, 2, 16, tzinfo=timezone.utc))


if __name__ == '__main__':
    unittest.main()
