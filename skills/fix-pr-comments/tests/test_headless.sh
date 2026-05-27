#!/usr/bin/env bash
# Smoke test: headless mode rejects unknown transforms and accepts known ones.
# This is a contract test — does not actually invoke the LLM. Verifies the
# skill's instructions handle the args correctly.

set -euo pipefail

SKILL="$(dirname "$0")/../SKILL.md"

grep -q "auto.*comment-ids.*transform" "$SKILL" || {
  echo "FAIL: headless invocation syntax not documented in SKILL.md"
  exit 1
}

for transform in rename_local remove_unused formatting api_swap; do
  grep -q "$transform" "$SKILL" || {
    echo "FAIL: transform '$transform' not listed in SKILL.md"
    exit 1
  }
done

grep -q "No public-API renames" "$SKILL" || {
  echo "FAIL: transform constraint prose (e.g., 'No public-API renames') missing"
  exit 1
}

grep -q '"fixed":' "$SKILL" && grep -q '"skipped":' "$SKILL" && grep -q '"failed":' "$SKILL" || {
  echo "FAIL: headless output shape (fixed/skipped/failed) not documented"
  exit 1
}

echo "PASS: headless mode contract documented in SKILL.md"
