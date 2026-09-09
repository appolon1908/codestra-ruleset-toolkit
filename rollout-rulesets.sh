#!/usr/bin/env bash
# Roll out the "server65-default-branch-gates" ruleset + auto-merge across
# the server65 repo set. Continues past per-repo failures and prints a summary.
set -uo pipefail

cd "$(dirname "$0")"

OWNER="appolon1908-hue"
RULESET_FILE="server65-ai-automation-ruleset.json"
RULESET_NAME="server65-default-branch-gates"

repos=(
  "codestra-production-platform"
  "Middleware-"
  "Odoo"
  "N8N"
  "Kong"
  "Keycloak"
  "Caddy"
  "Codestra-AI"
  "Codesrea-Social-"
  "Codestra-Communication-CC"
  "Codestra-Marketing-"
  "Infustruction-repo"
  "SDK-repository"
  "social.codestra.co"
)

[[ -f "$RULESET_FILE" ]] || { echo "missing $RULESET_FILE" >&2; exit 1; }

summary=()
failed=0

for repo in "${repos[@]}"; do
  echo "=== $OWNER/$repo ==="
  am_status="am:ok"
  rs_status="rs:ok"

  # Enable repository auto-merge (-F for a real boolean, not the string "true")
  if ! err=$(gh api --method PATCH "repos/$OWNER/$repo" -F allow_auto_merge=true --silent 2>&1); then
    am_status="am:FAIL"
    echo "  auto-merge failed: $(echo "$err" | tr '\n' ' ' | cut -c1-160)"
  fi

  # Find an existing ruleset by name; tolerate a failed lookup
  ruleset_id=""
  if ids=$(gh api "repos/$OWNER/$repo/rulesets" \
             --jq ".[] | select(.name==\"$RULESET_NAME\") | .id" 2>&1); then
    ruleset_id=$(printf '%s\n' "$ids" | head -n 1)
  else
    rs_status="rs:FAIL(list)"
    echo "  ruleset list failed: $(echo "$ids" | tr '\n' ' ' | cut -c1-160)"
  fi

  if [[ "$rs_status" == "rs:ok" ]]; then
    if [[ -n "$ruleset_id" ]]; then
      echo "  updating ruleset $ruleset_id"
      if ! err=$(gh api --method PUT "repos/$OWNER/$repo/rulesets/$ruleset_id" \
                   --input "$RULESET_FILE" --silent 2>&1); then
        rs_status="rs:FAIL(put)"
        echo "  update failed: $(echo "$err" | tr '\n' ' ' | cut -c1-200)"
      fi
    else
      echo "  creating ruleset"
      if ! err=$(gh api --method POST "repos/$OWNER/$repo/rulesets" \
                   --input "$RULESET_FILE" --silent 2>&1); then
        rs_status="rs:FAIL(post)"
        echo "  create failed: $(echo "$err" | tr '\n' ' ' | cut -c1-200)"
      fi
    fi
  fi

  [[ "$am_status" == "am:ok" && "$rs_status" == "rs:ok" ]] || failed=$((failed + 1))
  summary+=("$(printf '%-32s %-8s %s' "$repo" "$am_status" "$rs_status")")
done

echo
echo "===== SUMMARY ====="
printf '%s\n' "${summary[@]}"
echo "-------------------"
echo "$((${#repos[@]} - failed))/${#repos[@]} repos fully applied"
exit $(( failed > 0 ))
