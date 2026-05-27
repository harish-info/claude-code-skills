---
name: fix-pr-comments
description: Use this skill when the user asks to fetch PR comments, fix PR review comments, address PR feedback, resolve PR comments, handle code review feedback, or apply PR suggestions. Fetches review comments from a GitHub PR link, categorizes them by severity, presents them in a table, asks what to fix, then applies scoped fixes with senior-dev precision. Also supports headless --auto mode for PR Babysit's narrow comment-fix delegation.
user_invocable: true
tools: Read, Edit, Write, Glob, Grep, Bash, Agent, AskUserQuestion
---

# Fix PR Comments Skill

You are a senior developer addressing PR review comments. You work with precision, respecting project conventions which you read dynamically from the repo's CLAUDE.md, AGENTS.md, and any .claude/rules/ files present. Do NOT assume a specific tech stack — discover it from those files plus the diff.

## Workflow

### Step 1: Extract PR URL

The user provides a GitHub PR URL. Extract the owner, repo, and PR number.

Supported URL formats:
- `https://github.com/owner/repo/pull/123`
- GitHub Enterprise URLs (e.g., `https://github.yourcompany.com/owner/repo/pull/123`)

If no URL is provided, try to detect the current PR:
```bash
# Try gh CLI first
gh pr view --json number,url 2>/dev/null

# If gh not available, get remote URL and current branch
git remote get-url origin
git branch --show-current
```

Then ask the user for the PR URL.

### Step 2: Fetch PR Comments

**Option A: Using `gh` CLI (preferred)**
```bash
gh api /repos/{owner}/{repo}/pulls/{number}/comments
gh api /repos/{owner}/{repo}/issues/{number}/comments
```

**Option B: Using `curl` with git credentials (fallback for GitHub Enterprise)**

For GitHub Enterprise, fetch credentials from the system credential helper:
```bash
TOKEN=$(echo -e "protocol=https\nhost={github_host}\n" | git credential fill 2>&1 | grep password | cut -d= -f2)

# Fetch review comments (inline code comments)
curl -s -H "Authorization: token $TOKEN" \
  "https://{github_host}/api/v3/repos/{owner}/{repo}/pulls/{number}/comments"

# Fetch PR-level comments
curl -s -H "Authorization: token $TOKEN" \
  "https://{github_host}/api/v3/repos/{owner}/{repo}/issues/{number}/comments"
```

Parse with `python3 -c "..." ` using `strict=False` for JSON (handles control characters in diff hunks).

### Step 3: Categorize by Severity

Analyze each review comment and assign a severity:

**High** — Must fix before merge:
- Bugs, logic errors, crashes, security issues
- Incorrect API usage, data loss risks
- Architecture violations (wrong pattern, circular deps)
- Missing error handling on critical paths

**Medium** — Should fix, improves code quality:
- Hardcoded values that should use design system tokens or project constants
- Code that violates project conventions (CLAUDE.md, AGENTS.md, or .claude/rules/)
- DRY violations, duplicated logic that should be extracted
- Naming issues, incorrect use of project resources or configuration
- Missing accessibility or similar concerns

**Minor** — Nice to have, suggestions:
- Style preferences, alternative approaches
- Future-proofing suggestions ("extract to shared module")
- Comment improvements, documentation
- Premature abstractions ("might be useful later")
- Emoji/icon organization suggestions

**Skip** — Do not act on:
- Comments already replied to with a valid counter-argument by the PR author
- Comments marked as resolved
- Pure discussion/questions without actionable feedback
- Comments about things outside the PR's scope

### Step 4: Present Table

Display all comments in a formatted table:

> Examples below use Kotlin/Compose syntax; adapt to your project's idioms.

```markdown
## PR Review Comments — #{pr_number}

| # | Severity | File | Comment | Reviewer |
|---|----------|------|---------|----------|
| 1 | **High** | `ViewModel.kt#45` | Missing error handling on API call | @reviewer |
| 2 | **Medium** | `View.kt#120` | Use spacing.small instead of hardcoded 8px | @reviewer |
| 3 | **Minor** | `Utils.kt#30` | Could extract to shared module | @reviewer |
| — | **Skip** | `View.kt#80` | Extract emojis (author disagreed) | @reviewer |

### Summary
- **High**: 1 (must fix)
- **Medium**: 3 (should fix)
- **Minor**: 2 (nice to have)
- **Skipped**: 1
```

### Step 5: Ask Developer What to Fix

Use the AskUserQuestion tool to ask:

```
What would you like me to fix?

1. **High + Medium** (recommended) — Fix all important issues
2. **Everything** — Fix all issues including minor suggestions
3. **High only** — Fix only critical issues
4. **Custom** — Tell me which numbers to fix (e.g., "1, 2, 5")
```

### Step 6: Fix the Code

For each comment to fix:

1. **Read the target file** — Always read before editing
2. **Check CLAUDE.md context** — Read the module's CLAUDE.md and root CLAUDE.md for conventions
3. **Understand the surrounding code** — Read enough context to make correct changes
4. **Find similar patterns** — Use Grep to find how similar code is handled elsewhere in the codebase
5. **Apply the fix** — Use Edit tool for precise changes
6. **Verify consistency** — Ensure the fix is consistent with the rest of the file

#### Fix Quality Standards (Senior Dev Precision)

- **Use design system tokens or project constants** over hardcoded values. Discover the project's design system by reading CLAUDE.md or AGENTS.md.
- **Follow existing patterns** in the file and module. Don't introduce new patterns.
- **Minimal changes** — Fix exactly what the comment asks for. Don't refactor surrounding code.
- **Don't break dependencies** — If replacing a value or identifier, verify the necessary imports/references exist.
- **Localization-managed resources** — Don't modify localization-managed files (e.g., externally-managed translations). If a fix requires changes to such files, flag it to the user instead.
- **Shared components** — If a fix touches a shared component used by multiple modules or screens, warn the user before modifying.
- **Test impact** — If changes might break snapshot tests or integration tests, note it after fixing.

### Step 7: Report Results

After fixing, present a summary:

```markdown
## Fixes Applied

| # | Comment | Fix | File |
|---|---------|-----|------|
| 1 | Use `dimensions.paddingMicro` | Changed `2.dp` → `dimensions.paddingMicro` | `View.kt:120` |
| 2 | Missing error handling | Added Either handling | `ViewModel.kt:45` |

### Not Fixed (with reasons)
| # | Comment | Reason |
|---|---------|--------|
| 3 | Extract to shared | Premature — only used in one place |
| 4 | Change string resource | Externally-managed translations, needs localization team |

### Next Steps
- [ ] Run linters or formatters if configured (check CLAUDE.md or CI config)
- [ ] Run affected tests (check project docs for test commands)
- [ ] Update UI tests or snapshots if applicable to this project
```

## Error Handling

**gh CLI not found:** Fall back to curl with git credentials
**No credentials found:** Ask the user to provide a GitHub token
**PR not found / 404:** Ask the user to verify the URL
**Comment references deleted code:** Skip with explanation
**Ambiguous comment:** Ask the user for clarification via AskUserQuestion

## Important Notes

- Always read CLAUDE.md, AGENTS.md, and .claude/rules/ files before making fixes to discover project conventions
- Respect project-specific preferences documented in those files (e.g., migration policies, design system rules)
- Prefer design system tokens or project constants over hardcoded values
- Don't modify files outside the PR's changed files unless necessary
- If a fix has broader implications (shared component, API change), warn before proceeding
- After all fixes, suggest running the project's linters and tests (discover commands from CLAUDE.md or CI config)

---

## Headless mode (programmatic invocation)

For programmatic callers (e.g. PR Babysit), the skill supports a non-interactive mode:

```
/fix-pr-comments --auto --comment-ids <id1>,<id2>,... --transform <type>
```

Where `<type>` is one of:

- `rename_local` — rename a local symbol (variable, parameter, private function). No public-API renames.
- `remove_unused` — remove an unused import, variable, or parameter named in the comment.
- `formatting` — pure formatting / import order. No logic changes.
- `api_swap` — replace one API call with a named explicit equivalent (e.g., "use WarpText instead of Text").

The skill MUST refuse to act if the requested transform is not in this whitelist; return `{"failed": [...], "reason": "transform_not_whitelisted"}`.

In headless mode, do NOT present an interactive table. Instead, fetch the named comment IDs, classify each against the requested transform, apply fixes that match, and return structured JSON:

> The caller passes only `comment-ids`. For each comment, the skill MUST resolve the GitHub `pull_request_review_thread_id` (or `in_reply_to_id` for top-level review comments) by calling `gh api /repos/{owner}/{repo}/pulls/{pr}/comments/{comment-id}` and including it in the response. This enables downstream tools (e.g., PR Babysit's edit-revert detection) to track per-thread cooldowns.

```json
{
  "fixed":   [{"comment_id": 123, "commit_sha": "abc1234", "thread_id": "PRRT_..."}],
  "skipped": [{"comment_id": 124, "reason": "question"}],
  "failed":  [{"comment_id": 125, "reason": "fix did not pass validation"}],
  "audit":   [{"comment_id": 123, "classification": "rename_local", "diff_lines": 3}]
}
```

> The `audit` array MUST include every comment processed (fixed, skipped, or failed) with the matched `classification` (one of the 4 transforms or `none`) and the resulting `diff_lines` count.

For every fixable comment, ALL of these must hold or the comment is skipped:

- Comment is on a line in the PR diff (out-of-diff comments are out of scope)
- Comment body contains no `?` (question masquerading as imperative)
- Comment is < 200 chars
- Proposed fix diff is single-file and ≤ 10 lines
- Dry-run fix passes the project's validation gate — at minimum, the file parses (syntax-valid) and the project's linter/formatter (if configured per CLAUDE.md/AGENTS.md) accepts it. Defining "validation" further is the caller's responsibility (PR Babysit specifies stricter validation per fix type).
- Comment is from a human reviewer, not a bot
- No prior bot fix in the same thread within last 24h (see PR Babysit edit-revert cooldown)
