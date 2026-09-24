---
name: multi-agent-review
description: Runs a read-only review of the current branch across available Claude, Codex, and AGY reviewers, then adjudicates findings into one verdict. Use whenever the user says "review code", "code review", "multi-agent review", "multi agent review", "review my changes", "review this branch" or "review this PR", or wants a multi-model review or a second opinion before shipping.
user_invocable: true
tools: Bash, Read, Grep, Agent, AskUserQuestion
---

# Multi-Agent Review

The host is Tech Lead. Available peers review independently. Every review is read-only; implementation happens outside this skill.

## Flags

- `--challenge`: question design choices and hidden assumptions.
- `--base <ref>`: override the default branch.

## Severity

- **Blocker**: security, data loss, broken build, or major regression.
- **Bug**: incorrect behavior that should block shipping.
- **Improvement**: worthwhile but non-blocking.
- **Nit**: minor clarity or style issue.

## 1. Resolve roster and base

```bash
ROSTER=$(ls ~/.claude/skills/.shared/agent-roster.sh ~/.codex/skills/.shared/agent-roster.sh 2>/dev/null | head -1)
[ -n "$ROSTER" ] || { echo "roster helper not found"; exit 1; }
eval "$($ROSTER)"
DEFAULT_BASE=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')
BASE_BRANCH=${BASE_BRANCH:-${DEFAULT_BASE:-main}}
echo "Host: $HOST | Peers: $PEERS | Base: $BASE_BRANCH"
```

Shell variables do not survive tool calls. Re-run those lines before using roster commands.

Roles:

- Host: Tech Lead; correctness, security, standards, adjudication.
- Other Claude/Codex peer: Senior Developer; bugs and error handling.
- AGY: Staff Engineer; architecture and hidden complexity.

If no mode flag was supplied, ask for Standard or Challenge before dispatching.

## 2. Verify the review target

```bash
BRANCH_NAME=$(git rev-parse --abbrev-ref HEAD)
SLUG=$(printf '%s' "$BRANCH_NAME" | tr '/' '-')
git diff --shortstat "$BASE_BRANCH"...HEAD
git status --porcelain > "/tmp/review-pre-$SLUG.txt"
```

Stop if both the branch diff and working-tree diff are empty. A dirty tree is allowed; the snapshot protects it from misattribution.

## 3. Dispatch reviewers

Launch every available peer first, then review inline as host while peers run.

Each peer receives:

```text
You are a {ROLE} reviewing branch changes.

READ-ONLY: Do not edit, create, delete, move, stage, commit, restore, stash, format,
or generate files. Use read commands only and output findings as text.

Review the branch diff against {BASE_BRANCH}. If the working tree is dirty, also
review the unstaged and staged diffs. Read AGENTS.md or CLAUDE.md for standards.

For each finding provide severity, file and line, evidence, impact, and suggested
fix. Sort Blockers and Bugs first. Pay special attention to {LENS}.
```

Append for Challenge mode:

```text
Challenge the design, tradeoffs, hidden assumptions, and whether a simpler approach exists.
```

Never place review text or diff bytes directly in a shell command. Write one uniquely named prompt file per reviewer with a quoted heredoc, then pass its contents as one argument or stdin. For AGY, append at most 200 KB of diff bytes to its prompt file.

Dispatch:

- Claude host: use the Agent tool in the background.
- Codex host: review inline.
- Claude peer: `firefly_claude "$(cat prompt-file)"`.
- Codex companion: `(unset CLAUDECODE; firefly_codex review --base "$BASE_BRANCH" --wait)`; use `adversarial-review` for Challenge.
- Codex CLI: `(unset CLAUDECODE; firefly_codex --sandbox read-only - < prompt-file)`.
- AGY: `firefly_agy 10m -p "$(cat prompt-file)"`.

The Codex CLI must use its read-only sandbox. AGY must not receive sandbox or skip-permission flags. If Codex fails, follow [Codex troubleshooting](references/codex-troubleshooting.md). Mark a failed or timed-out optional peer unavailable; do not retry AGY.

## 4. Wait and protect the tree

Wait until every dispatched reviewer completes or is marked unavailable. Do not adjudicate partial results.

Then compare status snapshots:

```bash
SLUG=$(git rev-parse --abbrev-ref HEAD | tr '/' '-')
git status --porcelain > "/tmp/review-post-$SLUG.txt"
diff "/tmp/review-pre-$SLUG.txt" "/tmp/review-post-$SLUG.txt" || true
```

If new changes appeared, report the exact paths and the reviewer that was active. Do not restore, delete, stage, or otherwise modify them. The snapshot shows timing, not authorship.

Delete only the temporary prompt and snapshot files after review.

## 5. Adjudicate

Verify every claimed issue against the source. Merge duplicates, reject false positives, and adjust severity when evidence warrants it.

Return one report:

```markdown
## Review Board

**Branch**: branch
**Base**: base
**Mode**: Standard | Challenge
**Agents**: Codex (Tech Lead) | Claude | AGY unavailable

### All Findings

| # | Finding | Codex | Claude | AGY | Verdict | Severity | Action |
|---|---------|:-----:|:------:|:---:|---------|----------|--------|
| 1 | Short description | Bug | Bug | — | Accepted | Bug | Concrete fix |

### Accepted findings

**#1 — Title** (`path:line`)
Evidence, impact, and correction. Raised by: agents.

### Verdict

**Ship it | Needs fixes | Needs rework**

### Stats
- Findings: X raised, Y accepted, Z rejected
- Agreement: N findings raised by multiple agents
- Agents: reviewer counts
```

The skill ends after the report. It never applies fixes, posts comments, or speaks externally.

## Tech Lead rules

- Read the referenced source before accepting a finding.
- Treat regressions as blocking unless evidence shows otherwise.
- Agreement is signal, not proof.
- Keep rejected findings in the table with a short reason.
- Never modify the working tree during review.
