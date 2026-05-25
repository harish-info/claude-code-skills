---
name: multi-agent-review
description: Three-agent code review where Claude (Tech Lead) adjudicates findings from Codex (Senior Dev) and AGY (Staff Engineer). Produces a single unified verdict with optional fix delegation. Works across any project.
user_invocable: true
---

# Review Board

Up to three independent AI agents review your branch in parallel. Claude Code acts as **Tech Lead** — it runs its own review, collects findings from Codex (Senior Developer) and AGY (Staff Engineer), then produces a single unified verdict.

## Flags

| Flag | Effect |
|------|--------|
| `--challenge` | Codex runs a challenge review (via `adversarial-review`) that questions design decisions, tradeoffs, and assumptions |
| `--base <ref>` | Base branch to diff against (auto-detects default branch) |

## Severity Scale

| Level | Meaning | Blocks merge? |
|-------|---------|:---:|
| **Blocker** | Security hole, crash, data loss, regression, broken build | Yes |
| **Bug** | Logic error, race condition, missing null check, wrong behavior | Yes |
| **Improvement** | Performance, missing test, weak error handling, better pattern | No |
| **Nit** | Naming, style, minor clarity, formatting | No |

---

## Phase 0: Ask the user for review mode

**If the user did NOT pass explicit flags**, use `AskUserQuestion` to ask which mode to run before doing anything else:

```
Which review mode would you like?
```

Options (in this order):
1. **Standard** — straightforward code review focusing on bugs, correctness, and project standards
2. **Challenge** — questions design decisions, tradeoffs, hidden assumptions, and whether a simpler approach exists

Map the user's selection:
- Standard → CHALLENGE=false
- Challenge → CHALLENGE=true

Base branch is auto-detected unless `--base <ref>` was provided. To detect, run:
```bash
git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' || echo "main"
```

**If the user already passed flags** (e.g., `/multi-agent-review --challenge`), skip this phase entirely.

---

## Phase 1: Verify there are changes to review

```bash
BASE_BRANCH="${BASE_BRANCH:-$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' || echo 'main')}"
DIFF_STAT=$(git diff --shortstat "$BASE_BRANCH"...HEAD)
BRANCH_NAME=$(git rev-parse --abbrev-ref HEAD)
echo "Branch: $BRANCH_NAME | Base: $BASE_BRANCH | $DIFF_STAT"
```

If the diff is empty (no output from `--shortstat`), stop and tell the user there are no changes to review.

---

## Phase 2: Detect available agents and dispatch in parallel

### Agent detection

Run these checks at startup (same as debate skill):

**Claude** — always available (Agent tool).

**Codex:**
```bash
CODEX_ROOT="$(find ~/.claude/plugins/cache/openai-codex -name codex-companion.mjs -path '*/scripts/*' 2>/dev/null | head -1 | xargs dirname | xargs dirname)"
```
Available if `CODEX_ROOT` is non-empty. If empty, Codex is not installed — mark it unavailable.

**AGY:**
```bash
# Kill stale AGY processes from previous sessions before detection
pkill -f "agy.*(--sandbox|--print).*/tmp/review-agy" 2>/dev/null || true
which agy 2>/dev/null && agy --print-timeout 30s -p "respond with only the word READY" 2>&1 | grep -qi "ready"
```
Available if the grep succeeds. AGY receives the diff inline via the `-p` prompt argument (not via file + view_file).

Minimum: Claude always runs. Proceed with however many agents are available.

### Dispatch all available agents in parallel

Launch all simultaneously using `run_in_background: true`. All MUST be dispatched in one message (single tool-use block).

### Agent 1: Claude Code (Tech Lead) — Agent tool, background

```
You are a Tech Lead reviewing branch changes.
Run `git diff {BASE_BRANCH}...HEAD` and read any files needed for full context.
Read CLAUDE.md (if it exists) for project standards and conventions.

Do a thorough code review. For each finding:
- Severity: Blocker / Bug / Improvement / Nit
- File and line
- What's wrong and WHY (quote the code)
- Suggested fix

Pay special attention to: regressions, security, correctness, and error handling.

Sort findings by severity (Blockers first). Numbered markdown list.
```

### Agent 2: Codex (Senior Developer) — Bash tool, background

**Standard mode** (default):

```bash
node "$CODEX_ROOT/scripts/codex-companion.mjs" review --base {BASE_BRANCH} --wait
```

**Challenge mode** (when `--challenge` flag is set):

```bash
node "$CODEX_ROOT/scripts/codex-companion.mjs" adversarial-review --base {BASE_BRANCH} --wait
```

The `--wait` flag tells the companion to run synchronously and return output to stdout.

### Agent 3: AGY (Staff Engineer) — Bash tool, background

AGY v1 has two known issues: (1) `--sandbox` and `--dangerously-skip-permissions` both break the `--print-timeout` mechanism, causing AGY to hang indefinitely, and (2) `view_file` reads files in small chunks via sequential API calls, making it too slow for large diffs. The working pattern is to pass the diff inline via the `-p` argument and use bare flags with `--print-timeout`.

```bash
# Get the diff content, truncate if over 200KB to stay within shell ARG_MAX
DIFF_CONTENT="$(git diff {BASE_BRANCH}...HEAD)"
DIFF_SIZE=${#DIFF_CONTENT}
if [ "$DIFF_SIZE" -gt 200000 ]; then
  DIFF_CONTENT="$(echo "$DIFF_CONTENT" | head -c 200000)"
  DIFF_CONTENT="$DIFF_CONTENT
... [TRUNCATED — diff exceeded 200KB, review the full diff via git]"
fi

# Pass diff inline via -p, use --print-timeout (NOT --sandbox or --dangerously-skip-permissions)
agy --print-timeout 10m -p "You are a Staff Engineer reviewing branch changes.

Here is the diff to review:

$DIFF_CONTENT

Do a thorough code review. For each finding:
- Severity: Blocker / Bug / Improvement / Nit
- File and line
- What is wrong and WHY (quote the code)
- Suggested fix

Pay special attention to: architecture decisions, scalability, hidden complexity, and cross-cutting concerns.

Sort findings by severity (Blockers first). Numbered markdown list."
```

If AGY returns a 503, timeout, or error, mark it unavailable and continue with Claude + Codex.

---

## Phase 3: Wait for ALL agents — do not proceed early

**CRITICAL: Do NOT start adjudicating until all dispatched agents have completed (or been marked unavailable).** This prevents fragmented output.

When an agent completes, note it silently and keep waiting. Give a brief status update to the user:

```
Claude — done (N findings)
Codex — done (N findings)
AGY — still running...
```

### Checking Codex progress

If Codex is taking long, you can check its status:

```bash
node "$CODEX_ROOT/scripts/codex-companion.mjs" status
```

### Handling slow or failed agents

If Codex fails or returns empty output, **diagnose before retrying**:

```bash
CODEX_ROOT="$(find ~/.claude/plugins/cache/openai-codex -name codex-companion.mjs -path '*/scripts/*' 2>/dev/null | head -1 | xargs dirname | xargs dirname)"
if [ -z "$CODEX_ROOT" ]; then
  echo "PLUGIN_MISSING"
else
  node "$CODEX_ROOT/scripts/codex-companion.mjs" setup --json
fi
```

- **`PLUGIN_MISSING`**: Tell the user the Codex plugin needs to be installed. Ask them to run in order:
  ```
  /plugin marketplace add openai/codex-plugin-cc
  /plugin install codex@openai-codex
  /reload-plugins
  ```
  Then say: "After running those commands, re-run `/multi-agent-review`." and **stop**.

- **`node.available: false`**: Node.js is not installed. Tell the user to install it (e.g. `brew install node`) and re-run. **Stop**.

- **`codex.available: false`**: Codex CLI is not installed. If `npm.available: true`, offer to run `npm install -g @openai/codex`. After install, re-run the diagnostic to verify, then continue.

- **`auth.loggedIn: false`**: Tell the user: "Codex is installed but not logged in. Run `!codex login` to authenticate, then re-run `/multi-agent-review`." and **stop**.

- **`sessionRuntime.mode` is not `"shared"` OR the socket endpoint is unreachable**: The shared Codex runtime is not active. Tell the user to restart it:
  ```
  /plugin reload codex@openai-codex
  ```
  Then re-run `/multi-agent-review`. **Stop**.

- **`ready: false` with no specific field flagging**: Unknown setup failure. Show the full JSON to the user and ask them to check the Codex plugin installation.

- **Setup OK (`ready: true`) but Codex still failed**: Retry once in the foreground with a 5-minute timeout. If the retry also fails, mark Codex as "unavailable" in the final output.

### Handling AGY failures

If AGY returns a 503, timeout, or error, mark it as unavailable and continue. No retry — AGY is additive, not required.

Only after ALL dispatched agents have completed (or been marked unavailable) should you proceed to Phase 4.

---

## Phase 4: Adjudicate and present unified output

Read the source files referenced by findings to verify claims. Then produce **one single output** in exactly this format:

```markdown
## Review Board

**Branch**: `{branch_name}`
**Base**: `{BASE_BRANCH}`
**Mode**: Standard | Challenge
**Agents**: Claude ✅ | Codex ✅ | AGY ✅ (or ❌ unavailable for any)

---

### All Findings

| # | Finding | Claude | Codex | AGY | Verdict | Severity | Action |
|---|---------|:------:|:-----:|:------:|---------|----------|--------|
| 1 | Short description | Bug | Bug | Bug | Accepted | Improvement | What to do |
| 2 | Short description | — | P2 | Imp | Accepted | Improvement | What to do |
| 3 | Short description | Nit | — | Nit | Accepted | Nit | What to do |
| 4 | Short description | — | Bug | — | Rejected | — | Why rejected (short) |

Legend: The "Claude / Codex / AGY" columns show what each agent called it (— means that agent did not flag it).
"Verdict" is the Tech Lead's final call. "Severity" is the Tech Lead's final severity (may differ from original).
If AGY was unavailable, omit the AGY column entirely.

---

### Detail: Accepted findings only

For each ACCEPTED finding, provide a short paragraph:

**#1 — [Title]** (`file.kt:123`)
What's wrong, with quoted code evidence. Why it matters. What to do about it.
Raised by: Claude + Codex + AGY (or whichever agents flagged it). Tech Lead downgraded from Bug to Improvement because [reason].

**#2 — [Title]** (`file.kt:456`)
...

(Skip rejected findings here — the table already shows why they were rejected.)

---

### Verdict

**[Ship it ✅ | Needs fixes ⚠️ | Needs rework ❌]**

[1-3 sentences. If "Needs fixes", list the blocking items.]

### Stats
- Findings: X raised → Y accepted, Z rejected
- Agreement: X/Y findings where 2+ agents aligned
- Agents: Claude (N findings) | Codex (N findings) | AGY (N findings)
```

### Output rules

1. **One output, not fragments.** Never present partial results. Wait for all agents, then present everything at once.
2. **Table first, detail second.** The summary table is the primary output — it should give a complete picture at a glance. Detail paragraphs follow for accepted findings only.
3. **No per-finding tables.** Use the single summary table, not individual `| key | value |` tables for each finding. Those are hard to scan.
4. **Rejected findings stay in the table.** Show them with ❌ and a short reason in the Action column. Don't expand on them below.
5. **Merge duplicate findings.** If both agents flagged the same issue, it's ONE row in the table showing both agents. Not two rows.

---

## Phase 5: Offer next actions

Skip this phase entirely if there are **no accepted findings** at any severity.

**IMPORTANT**: This phase runs in the SAME response as Phase 4. Do not wait for user input between the review output and the action prompt. Present the review findings, then immediately call `AskUserQuestion` in the same message.

**If there are accepted Blocker/Bug findings**, use `AskUserQuestion` to ask:

```
There are N accepted Blocker/Bug findings. What would you like to do?
```

Options (in this order):
1. **Claude fixes** — Claude applies fixes directly using Edit tool, with full project context and CLAUDE.md standards
2. **Codex fixes** — Codex applies fixes via the `codex:codex-rescue` subagent, an independent second pass
3. **AGY fixes** — AGY applies fixes via headless CLI with full repo access
4. **Post as PR review** — Post all accepted findings as review comments on the remote PR (for reviewing others' code)
5. **Skip** — I'll fix them manually

Only show fix options for agents that are available. If AGY is unavailable, omit option 3.

**If there are NO Blocker/Bug findings but there ARE accepted Improvement/Nit findings**, use `AskUserQuestion` to ask:

```
No blocking findings, but there are N accepted Improvement/Nit findings. What would you like to do?
```

Options (in this order):
1. **Post as PR review** — Post all accepted findings as review comments on the remote PR (for reviewing others' code)
2. **Skip** — No action needed

(Do not offer fix options for Improvement/Nit-only results.)

### Option 1: Claude fixes

Apply fixes directly in the main conversation using the Edit tool. For each blocking finding:

1. Read the file for full context around the finding
2. Apply the smallest safe patch — do not refactor surrounding code
3. Follow CLAUDE.md standards (MVVM, Coroutines, Koin, Arrow Either)

After all fixes are applied, present a summary:

```markdown
### Fix Results (Claude)

| # | Finding | Status | Detail |
|---|---------|--------|--------|
| 1 | Title | ✅ Fixed | Brief description of the change |
| 3 | Title | ⚠️ Partial | What was done, what remains |
| 5 | Title | ❌ Skipped | Why it couldn't be auto-fixed |
```

### Option 2: Codex fixes

Delegate to Codex via the Agent tool with `subagent_type: "codex:codex-rescue"`.

Prompt for the rescue agent:

```
Fix the following code review findings. Each is a Blocker or Bug that blocks merge.

## Context: Claude's full review

{Paste Claude's complete review output here verbatim — all findings including rejected ones,
with code quotes, reasoning, and severity calls. This gives Codex the full picture so it can
make correct judgment calls on ambiguous fixes.}

---

## Findings to fix

{For each blocking finding, include:}
- Finding #{N}: {title}
- File: {file_path}:{line}
- Issue: {description with quoted code}
- Suggested fix: {action from the review}

Apply the smallest safe patch for each. Do not refactor surrounding code.
Follow CLAUDE.md project standards if present.
```

After Codex returns, present a summary:

```markdown
### Fix Results (Codex)

| # | Finding | Status | Detail |
|---|---------|--------|--------|
| 1 | Title | ✅ Fixed | Brief description of the change |
| 3 | Title | ⚠️ Partial | What was done, what remains |
| 5 | Title | ❌ Skipped | Why it couldn't be auto-fixed |
```

### Option 3: AGY fixes

Delegate fixes to AGY via headless CLI:

```bash
cat > /tmp/review-agy-fix.txt << 'PROMPT'
Fix the following code review findings. Each is a Blocker or Bug that blocks merge.

## Context: Tech Lead review

{Paste Claude's complete review output here verbatim — all findings including rejected ones,
with code quotes, reasoning, and severity calls.}

---

## Findings to fix

{For each blocking finding, include:}
- Finding #{N}: {title}
- File: {file_path}:{line}
- Issue: {description with quoted code}
- Suggested fix: {action from the review}

Apply the smallest safe patch for each. Do not refactor surrounding code.
Read CLAUDE.md for project standards if present.
PROMPT

agy --print-timeout 10m -p "$(cat /tmp/review-agy-fix.txt)"
```

Note: Do NOT use `--sandbox` or `--dangerously-skip-permissions` — both break AGY's `--print-timeout` mechanism, causing indefinite hangs. Use bare `-p` with `--print-timeout` instead.

After AGY returns, present a summary:

```markdown
### Fix Results (AGY)

| # | Finding | Status | Detail |
|---|---------|--------|--------|
| 1 | Title | ✅ Fixed | Brief description of the change |
| 3 | Title | ⚠️ Partial | What was done, what remains |
| 5 | Title | ❌ Skipped | Why it couldn't be auto-fixed |
```

### Option 4: Post as PR review

Post the accepted findings as GitHub PR review comments. This is useful when reviewing someone else's code — instead of fixing, you leave the findings as review feedback on their PR.

**Step 1: Find the PR number for the current branch.**

```bash
gh pr list --head "$(git rev-parse --abbrev-ref HEAD)" --json number,url --jq '.[0]'
```

If no PR exists for the current branch, tell the user: "No open PR found for this branch. Push the branch and open a PR first, then re-run `/multi-agent-review`." and **stop**.

**Step 2: Build review comments.**

For each **accepted** finding (all severities, not just Blocker/Bug):

- Use `gh api` to post a **PR review** with file-level comments, not individual comments.
- Map each finding to its file path and line number in the diff.
- Format each comment body as:

```
**[Severity]** Finding title

Description of the issue with code evidence.

**Suggested action:** What to do about it.

_— Review Board ({actual agent roster})_
```

**Step 3: Submit the review.**

Use `gh api` to create a pull request review with all comments in a single review submission:

```bash
gh api repos/{owner}/{repo}/pulls/{pr_number}/reviews \
  --method POST \
  -f event="COMMENT" \
  -f body="## Review Board Summary

**Mode**: Standard | Challenge
**Verdict**: [Ship it ✅ | Needs fixes ⚠️ | Needs rework ❌]

[Verdict summary from Phase 4]

**Stats**: X findings raised → Y accepted, Z rejected" \
  -f 'comments=[...]'
```

Each comment in the array:

```json
{
  "path": "relative/path/to/file.kt",
  "line": 123,
  "body": "**[Bug]** Finding title\n\nDescription...\n\n**Suggested action:** ...\n\n_— Review Board ({actual agent roster})_"
}
```

**Important notes for posting comments:**
- The `line` must be a line number in the **diff** (the changed side). Use `gh api repos/{owner}/{repo}/pulls/{pr_number}/files` to get the diff and verify line numbers are valid comment targets. If a finding references a line not in the diff, use a top-level review comment instead of an inline comment.
- If a finding's line can't be mapped to the diff (e.g., it's in unchanged context), include it in the review body summary instead.
- Use `event: "COMMENT"` for informational reviews. Use `event: "REQUEST_CHANGES"` only if there are Blocker/Bug findings.

After posting, present a summary:

```markdown
### PR Review Posted

| # | Finding | Status | Detail |
|---|---------|--------|--------|
| 1 | Title | ✅ Posted | Inline comment on file.kt:123 |
| 3 | Title | ✅ Posted | Included in review body (line not in diff) |
| 5 | Title | ❌ Failed | Error reason |

PR: {pr_url}
```

### Option 5: Skip

Say "Understood — leaving fixes to you." and stop.

### After fixes (Option 1, 2, or 3)

If any fixes were applied (Option 1, 2, or 3), tell the user to run `/multi-agent-review` again to verify the fixes don't introduce new issues.

If a PR review was posted (Option 4), provide the PR URL and stop.

---

## Tech Lead Rules

1. **Evidence over opinion.** Cite code and line numbers. "Looks wrong" isn't enough.
2. **Read the file first.** A "bug" in the diff might be correct in surrounding context.
3. **Know the codebase.** Read CLAUDE.md for project standards. Use those as your baseline for architecture findings.
4. **Reject false positives confidently.** External agents may lack full project context. If the code is correct, say so and prove it.
5. **Change severity when warranted.** A "nit" that crashes prod is a Blocker. A "blocker" in dead code is a Nit.
6. **Add your own findings.** If you found something the other agents missed, include it.
7. **Regressions are almost always Blockers.** Breaking existing behavior is serious.
8. **Multi-agent agreement = strong signal.** If 2+ agents independently flag the same issue, take it seriously. Solo findings deserve more scrutiny. If all 3 agents agree, it's almost certainly valid.
