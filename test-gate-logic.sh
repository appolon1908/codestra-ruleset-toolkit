#!/usr/bin/env bash
# Exercise the pending/failed classification from production-merge-gate.yml
# against representative check-run tables. Input format: name<TAB>status<TAB>conclusion
set -uo pipefail

classify() {
  local all="$1"
  local pending failed
  pending=$(printf '%s\n' "$all" | sed '/^$/d' \
    | awk -F'\t' '$2 != "completed" { print $1" ("$2")" }')
  failed=$(printf '%s\n' "$all" | sed '/^$/d' \
    | awk -F'\t' '$2 == "completed" &&
                  $3 != "success" &&
                  $3 != "skipped" &&
                  $3 != "neutral" { print $1" -> "$3 }')

  if [ -z "$(printf '%s' "$all" | sed '/^$/d')" ]; then echo "PASS"; return; fi
  if [ -n "$pending" ]; then echo "WAIT: $(echo $pending | tr '\n' ' ')"; return; fi
  if [ -n "$failed" ]; then echo "FAIL: $(echo $failed | tr '\n' ' ')"; return; fi
  echo "PASS"
}

t() {
  local desc="$1" expect="$2" data="$3"
  local got; got=$(classify "$data")
  local head="${got%%:*}"; local exp="${expect%%:*}"
  if [ "$head" = "$exp" ]; then echo "  ok   $desc => $got"
  else echo "  FAIL $desc => got '$got', expected '$expect'"; fi
}

echo "gate classification tests:"
t "no checks at all (all path-filtered out)" "PASS" ""
t "all green" "PASS" "$(printf 'validate\tcompleted\tsuccess\nbuild\tcompleted\tsuccess')"
t "one still running" "WAIT" "$(printf 'validate\tcompleted\tsuccess\nbuild\tin_progress\t-')"
t "one queued" "WAIT" "$(printf 'validate\tqueued\t-')"
t "one failed" "FAIL" "$(printf 'validate\tcompleted\tsuccess\nbuild\tcompleted\tfailure')"
t "skipped treated as pass" "PASS" "$(printf 'validate\tcompleted\tskipped\nbuild\tcompleted\tsuccess')"
t "neutral treated as pass" "PASS" "$(printf 'validate\tcompleted\tneutral')"
t "cancelled is a failure" "FAIL" "$(printf 'build\tcompleted\tcancelled')"
t "timed_out is a failure" "FAIL" "$(printf 'build\tcompleted\ttimed_out')"
t "action_required is a failure" "FAIL" "$(printf 'build\tcompleted\taction_required')"
t "legacy status failure" "FAIL" "$(printf 'ci/ext\tcompleted\tfailure')"
t "legacy status pending blocks" "WAIT" "$(printf 'ci/ext\tpending\t-')"
t "matrix job names with spaces/parens" "PASS" \
  "$(printf 'build (mail-api, deploy/mail-platform/Dockerfile.api)\tcompleted\tsuccess')"
t "matrix job failing" "FAIL" \
  "$(printf 'build (reseller-portal, deploy/reseller-portal/Dockerfile)\tcompleted\tfailure')"
t "mixed: skipped + running" "WAIT" \
  "$(printf 'a\tcompleted\tskipped\nb\tin_progress\t-\nc\tcompleted\tsuccess')"
