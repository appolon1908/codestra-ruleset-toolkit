#!/usr/bin/env bash
# Offline validation only: never execute audit/apply scripts or call GitHub.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
export PYTHONDONTWRITEBYTECODE=1

python3 - <<'PY'
import ast
import json
from pathlib import Path

root = Path(".")
for path in sorted(root.glob("*.py")):
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
for path in sorted(root.glob("*.json")):
    json.loads(path.read_text(encoding="utf-8"))
print("ROOT_PYTHON_AND_JSON_SYNTAX=PASS")
PY

for source in ./*.sh; do
  bash -n "$source"
done
python3 -m unittest discover -s . -p 'test_*.py' -v
bash test-gate-logic.sh
printf 'OFFLINE_SOURCE_VALIDATION=PASS\n'
