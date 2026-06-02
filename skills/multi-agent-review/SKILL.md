---
name: multi-agent-review
description: Three-agent code review where Claude (Tech Lead) adjudicates findings from Codex (Senior Dev) and AGY (Staff Engineer). Produces a single unified verdict with optional fix delegation. Works across any project.
user_invocable: true
tools: Bash, Read, Edit, Grep, Agent, AskUserQuestion
---

# Multi-Agent Review

Run a read-only branch review with Claude as Tech Lead plus Codex and AGY when available. Output one unified verdict. Fix only after explicit user selection.

## Modes

- No flags: ask `Standard` or `Challenge` with `AskUserQuestion`.
- `--challenge`: use Codex adversarial review and ask every reviewer to question design/tradeoffs.
- `--base <ref>`: review against that base. Otherwise use `origin/HEAD`, fallback `main`.

Severity: `Blocker` and `Bug` block merge; `Improvement` and `Nit` do not.

## Non-Negotiable Review Safety

READ-ONLY REVIEW MANDATE applies to Claude, Codex, and AGY:

- No file edits, creates, deletes, moves, staging, formatting, codegen, commits, checkout, restore, stash, or other mutating commands.
- Reviewers may only read (`git diff`, `git log`, `cat`, `grep`, `Read`) and emit text findings.
- If any reviewer changes files, discard those changes and keep only textual findings.
- Phase 5 fixes require explicit user approval.

## Flow

1. Resolve `BASE_BRANCH`; print branch/base/diff shortstat. If diff is empty, stop.
2. Detect agents:
   - Claude: always available via `Agent`.
   - Codex: `CODEX_ROOT="$(find ~/.claude/plugins/cache/openai-codex -name codex-companion.mjs -path '*/scripts/*' 2>/dev/null | head -1 | xargs dirname | xargs dirname)"`.
   - AGY: clear stale review processes, then `which agy && agy --print-timeout 30s -p "respond with only the word READY" | grep -qi ready`.
3. Dispatch all available reviewers in parallel in one tool-use block.
4. Wait for every dispatched reviewer to finish or be marked unavailable. Do not adjudicate early.
5. Merge duplicate findings, drop unsupported claims, and produce one ordered verdict.
6. Ask what to fix only if findings exist. Fix selected items yourself, then validate.

## Reviewer Prompts

All reviewer prompts must include:

```text
READ-ONLY: This is a review, not a fix. Do NOT edit, create, delete, move, or stage files. Do NOT run mutating commands. Output findings only.

Review git diff {BASE_BRANCH}...HEAD. Read project instructions such as CLAUDE.md/AGENTS.md when present.

For each finding:
- Severity: Blocker / Bug / Improvement / Nit
- File and line
- What is wrong and why
- Suggested fix

Prioritize regressions, security, correctness, race conditions, error handling, and project-standard violations. Sort by severity.
```

Codex command:

```bash
node "$CODEX_ROOT/scripts/codex-companion.mjs" review --base {BASE_BRANCH} --wait
# challenge mode:
node "$CODEX_ROOT/scripts/codex-companion.mjs" adversarial-review --base {BASE_BRANCH} --wait
```

AGY command: pass the diff inline to `agy --print-timeout 10m -p "<prompt>"`. Do not use `--sandbox` or `--dangerously-skip-permissions`; those break timeout behavior.

## Adjudication Format

Lead with findings, ordered by severity:

```markdown
## Verdict: Ready | Not Ready

1. **[Bug] path/file.kt:42** — issue
   - Evidence: quote or concrete reference
   - Fix: exact change

## Agent Coverage
- Claude: N findings
- Codex: N findings / unavailable reason
- AGY: N findings / unavailable reason

## Fix Options
1. Fix Blockers + Bugs
2. Fix all
3. No fixes
```

If there are no issues, say that clearly and mention residual test gaps.
