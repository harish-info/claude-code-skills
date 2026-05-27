#!/usr/bin/env bash
# E2E smoke: verify the SKILL.md documents --dry-run and the contract is intact.
# This is a contract test — does not invoke the LLM. Run before the manual 2-day soak.

set -euo pipefail

SKILL="$(dirname "$0")/../SKILL.md"

# Contract 1: --dry-run must be documented as an invocation
grep -q -- "--dry-run" "$SKILL" || {
  echo "FAIL: --dry-run not documented in SKILL.md"
  exit 1
}

# Contract 2: SKILL.md must reference all 5 bin/ helpers (either hyphen or underscore form)
for helper in state lock classify git notify; do
  grep -E -q "pr.babysit.$helper" "$SKILL" || {
    echo "FAIL: SKILL.md does not reference pr-babysit-$helper or pr_babysit_$helper"
    exit 1
  }
done

# Contract 3: all 5 bin/ helpers exist and are non-empty
BIN_DIR="$(dirname "$0")/../bin"
for helper in state lock classify git notify; do
  f="$BIN_DIR/pr-babysit-$helper.py"
  if [ ! -s "$f" ]; then
    echo "FAIL: $f missing or empty"
    exit 1
  fi
done

# Contract 4: SKILL.md must mention scope check and validation gate
grep -q "scope_check\|scope check" "$SKILL" || {
  echo "FAIL: SKILL.md does not reference scope check"
  exit 1
}

grep -q "validation" "$SKILL" || {
  echo "FAIL: SKILL.md does not reference validation gate"
  exit 1
}

# Contract 5: /loop mentioned for recurring usage
grep -q "/loop" "$SKILL" || {
  echo "FAIL: SKILL.md does not mention /loop for recurring babysitting"
  exit 1
}

echo "PASS: pr-babysit SKILL.md contract verified"
