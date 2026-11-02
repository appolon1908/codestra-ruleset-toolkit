"""Scoped controller-check migration. Dry run is the default; no status is issued.

This changes rulesets only. Classic protection, deployment environments, gate
installation and independent review must be reconciled separately before apply.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

CONTROLLER_CONTEXTS = {'codestra-control-plane', 'codestra/control-plane'}
PAYLOAD_KEYS = ('name', 'target', 'enforcement', 'conditions', 'rules', 'bypass_actors')
MAX_AGE = timedelta(hours=1)


def payload_of(ruleset):
    if any(key not in ruleset for key in PAYLOAD_KEYS):
        raise ValueError('Incomplete ruleset snapshot; refusing to infer defaults')
    return {key: copy.deepcopy(ruleset[key]) for key in PAYLOAD_KEYS}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_checks(checks):
    if not checks or not isinstance(checks, list):
        raise ValueError('At least one explicit replacement check is required')
    seen = set()
    for check in checks:
        if set(check) != {'context', 'integration_id'}:
            raise ValueError('Each check needs exactly context and integration_id')
        context, app = check['context'], check['integration_id']
        if not isinstance(context, str) or not context.strip() or context in CONTROLLER_CONTEXTS:
            raise ValueError('Replacement must have a distinct nonempty validation context')
        if type(app) is not int or app <= 0 or context in seen:
            raise ValueError('Check publisher must be a positive app id; contexts must be unique')
        seen.add(context)


def replacement_payload(before, checks):
    validate_checks(checks)
    after = payload_of(before)
    if after['enforcement'] != 'active' or after['target'] != 'branch':
        raise ValueError('Only active branch rulesets can be migrated')
    found = False
    for rule in after['rules']:
        if rule['type'] != 'required_status_checks':
            continue
        existing = rule['parameters']['required_status_checks']
        if not any(check['context'] in CONTROLLER_CONTEXTS for check in existing):
            continue
        found = True
        result = []
        for check in existing:
            if check['context'] in CONTROLLER_CONTEXTS:
                for new in checks:
                    if new not in result:
                        result.append(copy.deepcopy(new))
            elif check not in result:
                result.append(check)
        # A same-named check from a different publisher is an ambiguity, not a dedupe.
        names = [check['context'] for check in result]
        if len(names) != len(set(names)):
            raise ValueError('Ambiguous existing replacement context publisher')
        rule['parameters']['required_status_checks'] = result
    if not found:
        raise ValueError('No controller requirement in the selected ruleset')
    return after


def parse_time(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Evidence timestamps must have a timezone')
    return parsed


def verify_evidence(runs, sha, checks, now):
    validate_checks(checks)
    if not isinstance(sha, str) or not re.fullmatch('[a-f0-9]{40}', sha):
        raise ValueError('A full exact commit SHA is required')
    for check in checks:
        matches = [run for run in runs if run.get('name') == check['context']
                   and run.get('app', {}).get('id') == check['integration_id']]
        if not matches:
            raise ValueError(f'Missing check evidence: {check["context"]}')
        # The same revision can legitimately have both push and PR check runs.
        # Every matching run must pass; a success never hides a pending/failing run.
        for run in matches:
            if run.get('head_sha') != sha or run.get('status') != 'completed' or run.get('conclusion') != 'success':
                raise ValueError(f'Check did not succeed on exact SHA: {check["context"]}')
            age = now - parse_time(run['completed_at'])
            if age < timedelta(0) or age > MAX_AGE:
                raise ValueError('Check evidence must be no more than one hour old and not in the future')


def make_plan(repository, before, checks, sha, runs, now):
    if not re.fullmatch(r'appolon1908/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Migration scope is appolon1908 repositories only')
    if before.get('source') != repository or before.get('source_type') != 'Repository':
        raise ValueError('Inherited or differently owned rulesets are not supported')
    if type(before.get('id')) is not int or before['id'] <= 0:
        raise ValueError('Explicit ruleset id required')
    verify_evidence(runs, sha, checks, now)
    return {'schema_version': 1, 'repository': repository, 'ruleset_id': before['id'],
            'created_at': now.isoformat(), 'evidence_sha': sha, 'checks': copy.deepcopy(checks),
            'before': payload_of(before), 'after': replacement_payload(before, checks),
            'before_sha256': fingerprint(payload_of(before))}


def gh_api(method, endpoint, payload=None):
    args = ['gh', 'api', '--method', method, endpoint]
    if payload is not None:
        args += ['--input', '-']
    result = subprocess.run(args, input=json.dumps(payload) if payload is not None else None,
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(f'GitHub {method} failed for {endpoint}: {result.stderr[:300]}')
    return json.loads(result.stdout)


def check_runs(api, repository, sha):
    response = api('GET', f'repos/{repository}/commits/{sha}/check-runs?per_page=100&filter=all')
    runs = response['check_runs']
    if response['total_count'] != len(runs):
        raise ValueError('Check evidence is paginated; provide a narrower reviewed migration')
    return runs


def validate_plan(plan, now):
    if plan['schema_version'] != 1:
        raise ValueError('Unsupported plan schema')
    if not re.fullmatch(r'appolon1908/[A-Za-z0-9_.-]+', plan['repository']):
        raise ValueError('Repository outside authorized scope')
    if type(plan['ruleset_id']) is not int or plan['ruleset_id'] <= 0:
        raise ValueError('Invalid ruleset id')
    age = now - parse_time(plan['created_at'])
    if age < timedelta(0) or age > MAX_AGE:
        raise ValueError('Migration plan is expired or future-dated; regenerate it')
    if fingerprint(plan['before']) != plan['before_sha256']:
        raise ValueError('Snapshot digest mismatch')
    if replacement_payload(plan['before'], plan['checks']) != plan['after']:
        raise ValueError('Plan changes more than the permitted controller requirements')


def apply_plan(plan, api, backup_dir, now):
    validate_plan(plan, now)
    endpoint = f'repos/{plan["repository"]}/rulesets/{plan["ruleset_id"]}'
    current = api('GET', endpoint)
    if payload_of(current) != plan['before']:
        raise ValueError('Ruleset changed since planning; no write performed')
    verify_evidence(check_runs(api, plan['repository'], plan['evidence_sha']),
                    plan['evidence_sha'], plan['checks'], now)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f'{plan["repository"].replace("/", "--")}-{plan["ruleset_id"]}-{fingerprint(plan)[:16]}.json'
    # Exclusive create: a rerun cannot silently overwrite the rollback record.
    with backup.open('x', encoding='utf-8') as handle:
        json.dump(plan, handle, indent=2)
        handle.write('\n')
    # Re-read immediately before mutation. GitHub ruleset PUT has no CAS/ETag
    # guarantee, so administration writers must be serialized operationally.
    if payload_of(api('GET', endpoint)) != plan['before']:
        raise ValueError('Concurrent ruleset update detected; no write performed')
    api('PUT', endpoint, plan['after'])
    if payload_of(api('GET', endpoint)) != plan['after']:
        raise RuntimeError(f'Ruleset readback mismatch; stop rollout and inspect backup {backup}')
    return backup


def rollback(plan, api):
    # Deliberate rollback may be later than one hour; payload integrity still applies.
    validate_plan(plan, parse_time(plan['created_at']))
    endpoint = f'repos/{plan["repository"]}/rulesets/{plan["ruleset_id"]}'
    if payload_of(api('GET', endpoint)) != plan['after']:
        raise ValueError('Current settings differ from applied plan; refusing to overwrite newer changes')
    api('PUT', endpoint, plan['before'])
    if payload_of(api('GET', endpoint)) != plan['before']:
        raise RuntimeError('Rollback readback mismatch')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    plan_parser = sub.add_parser('plan', help='Read live state and print an unapplied plan')
    plan_parser.add_argument('repository')
    plan_parser.add_argument('ruleset_id', type=int)
    plan_parser.add_argument('evidence_sha')
    plan_parser.add_argument('--checks', required=True, type=Path, help='JSON array of context/integration_id')
    for command in ('apply', 'rollback'):
        target = sub.add_parser(command)
        target.add_argument('plan', type=Path)
        target.add_argument('--apply', action='store_true', help='Without this flag only validate and print')
        if command == 'apply':
            target.add_argument('--backup-dir', type=Path, default=Path('interim-release-backups'))
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    if args.command == 'plan':
        before = gh_api('GET', f'repos/{args.repository}/rulesets/{args.ruleset_id}')
        checks = json.loads(args.checks.read_text())
        plan = make_plan(args.repository, before, checks, args.evidence_sha,
                         check_runs(gh_api, args.repository, args.evidence_sha), now)
    else:
        plan = json.loads(args.plan.read_text())
        validate_plan(plan, now if args.command == 'apply' else parse_time(plan['created_at']))
        if args.apply:
            if args.command == 'apply':
                print(apply_plan(plan, gh_api, args.backup_dir, now))
            else:
                rollback(plan, gh_api)
                print('Rollback verified')
            return
    print(json.dumps(plan, indent=2))


if __name__ == '__main__':
    main()
