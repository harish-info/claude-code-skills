---
name: pr-babysit
description: Babysits open GitHub PRs. One-shot pass that auto-fixes CI failures (lint, tests, merge conflicts) and review comments, then reports what it can't fix. Run via /loop for recurring checks. Invocations - /pr-babysit, /pr-babysit <url>, /pr-babysit --mine, /pr-babysit --dry-run, /pr-babysit --takeover.
user_invocable: true
---

# PR Babysit

Runs one PR babysitting pass for a PR (or all your open PRs) -- fixes what it safely can, reports what it can't, and exits cleanly on merge/close.

For recurring babysitting, use Claude Code's `/loop` command (e.g., `/loop 15m /pr-babysit <url>`).

## Invocation

| Form | Behavior |
|------|----------|
| `/pr-babysit` | One-shot pass for current branch PR |
| `/pr-babysit <url>` | One-shot pass for specific PR (includes drafts) |
| `/pr-babysit --mine` | One-shot sweep for all your open non-draft PRs |
| `/pr-babysit --dry-run` | Classify only, no fixes or push |
| `/pr-babysit --takeover` | Forces lock reclaim if another session holds it |

Every invocation runs one pass. `--dry-run` is read-only: it classifies and prints the worklist without fixes, commits, or push.

## One-shot body

Each invocation executes one pass. The skill body is intentionally re-entrant -- every pass re-derives state from GitHub.

### Step 0 -- Resolve PR(s) and acquire lock

Parse args:

- No args: `gh pr view --json url,number,headRefOid,...` to resolve current branch's PR. Exit with "no PR found" if absent.
- `--mine`: `gh pr list --author @me --state open --draft=false --json url,number`. Exit with "no PRs to babysit" if empty.
- `<url>`: parse owner/repo/pr-number. `gh pr view <url> --json ...`.
- `--takeover`: same as default but pass takeover=true to lock acquisition.
- `--dry-run`: skip Steps 5-6 (no fixes, no reporting). Print the worklist after Step 4 and proceed to Step 7 state/heartbeat only.

For each PR to process, acquire the lock:

```python
import sys, os
skill_dir = os.path.dirname(os.path.abspath("__file__"))  # resolve relative to skill
sys.path.insert(0, os.path.join(skill_dir, "bin"))
import pr_babysit_lock as L
result = L.acquire(owner, repo, pr_number, session_id, schedule_seconds=900, takeover=False)
# Returns: "acquired" | "blocked_other_session" | "blocked_overrun" | "blocked_race"
```

Lock outcomes:
- `acquired` -> proceed with this PR
- `blocked_other_session` -> skip this PR, print session log line, continue with next (or exit if single PR)
- `blocked_overrun` -> skip this PR, print "prior pass still running"
- `blocked_race` -> skip this PR, print "metadata race -- try again later"

State directory: `~/.cache/pr-babysit/` (locks and per-PR state files live here).

### Step 1 -- Resolve PR head remote + workspace sync

```bash
PR_META=$(gh pr view <url> --json headRefOid,headRefName,headRepositoryOwner,headRepository)
HEAD_REMOTE="origin"   # add fork as remote if owner differs
HEAD_BRANCH=$(echo "$PR_META" | jq -r .headRefName)
CURRENT_HEAD_SHA=$(echo "$PR_META" | jq -r .headRefOid)

git fetch "$HEAD_REMOTE" "$HEAD_BRANCH"
```

### Step 2 -- First-fire init OR head-change detection

Load state via `pr_babysit_state`. If `state.head_sha == None`, this is the first fire:

```bash
PR_DIFF_FILES=$(gh pr diff --name-only <url>)
BASE_SHA=$(gh pr view <url> --json baseRefOid -q .baseRefOid)
git reset --hard "$HEAD_REMOTE/$HEAD_BRANCH"
```

Else detect head change via `pr_babysit_git.detect_head_change`:

```python
import pr_babysit_git as G
kind = G.detect_head_change(repo_root, state.head_sha, current_head_sha)
# Returns None | "fast_forward" | "rewrite"
```

If kind is non-None:
- Sync workspace: `G.sync_workspace(repo_root, head_remote, head_branch)`
- Re-snapshot `pr_diff_files` and `base_sha` regardless of kind
- If kind == "rewrite": clear `state.handled_comment_ids`, filter `state.audit` to 24h, print "force-push detected on PR #<n>, state partially reset"

### Step 3 -- Fetch PR state in parallel

```bash
CHECKS_JSON=$(gh pr checks <url> --json name,status,conclusion)
PR_VIEW=$(gh pr view <url> --json mergeStateStatus,reviewDecision,statusCheckRollup)
COMMENTS=$(gh api "/repos/<owner>/<repo>/pulls/<n>/comments")
REVIEWS=$(gh api "/repos/<owner>/<repo>/pulls/<n>/reviews")
```

If PR is merged or closed -> cleanup and exit:

```python
S.delete_state(owner, repo, pr_number)
L.release(owner, repo, pr_number)
print(f"PR #{pr_number} merged/closed, exiting")
```

### Step 4 -- Build worklist

For each failing check from `CHECKS_JSON`, categorize by name using patterns from `.claude/pr-babysit.yaml`:

- Checks matching `lint.pattern` -> lint
- Checks matching `test.pattern` -> test
- Checks matching `snapshot.pattern` -> snapshot
- Everything else -> other (report only)

For each, call `pr_babysit_classify.classify_ci_failure(...)`. Returns a `Decision` with `decision` ("fix"|"escalate") and `reason`.

For comments, filter to new since `state.last_fire` AND not in `state.handled_comment_ids`:

```python
import pr_babysit_classify as C
import pr_babysit_notify as N

for comment in new_comments:
    thread_id = comment["pull_request_review_id"] or comment["in_reply_to_id"]
    if N.is_in_cooldown(state.audit, thread_id):
        continue
    decision = C.classify_comment(
        comment_body=comment["body"],
        on_diff_line=comment.get("line") is not None,
        is_bot=comment["user"]["type"] == "Bot",
        config=config["fixes"]["comment_fix"],
    )
```

Check merge conflict: `if mergeStateStatus == "DIRTY"`, add to worklist with type "merge_conflict". Defer file enumeration to Step 5's actual `git merge --no-commit` probe.

If `--dry-run`, print the worklist as a markdown table and skip to Step 7.

### Step 5 -- Act on fixable items (sequentially, fail-fast)

For each item with decision == "fix":

```bash
# Assert clean worktree
if [ -n "$(git status --porcelain)" ]; then
  echo "ERROR: dirty worktree before fix on PR #<n>"
  exit 1
fi

PRE_FIX_SHA=$(git rev-parse HEAD)
```

Apply the fix based on item type using commands from `.claude/pr-babysit.yaml`:

- **lint**: run the configured lint command. Stage and commit changed files.
- **snapshot**: run the configured record command with template substitution. Verify snapshot membership in `pr_diff_files`. Commit.
- **test**: re-run failing test to reproduce. If reproduced, attempt minimal fix. Re-run. Commit only if green.
- **merge_conflict**: `git fetch origin <base>`, `git merge origin/<base> --no-commit`. If all conflicts are in `safe_paths` -> resolve mechanically, commit. Else `git merge --abort`, report.
- **comment_fix**: delegate to `/fix-pr-comments --auto --comment-ids <id> --transform <type>`.

Then validate:

```python
validation_passed = run_check_locally(item)
if not validation_passed:
    subprocess.run(["git", "reset", "--hard", pre_fix_sha], cwd=repo)
    report(item, "fix failed validation")
    continue
```

Scope check (ensures fixes only touch files already in the PR diff, plus configured generated paths):

```python
import pr_babysit_git as G
if G.is_merge_commit(repo, "HEAD"):
    resolved = G.get_resolved_conflict_files(repo)
    ok, off = G.merge_scope_check(repo, pre_fix_sha, state.pr_diff_files,
                                  config["fixes"]["merge_conflict"]["safe_paths"],
                                  base_branch, resolved)
else:
    ok, off = G.scope_check(repo, pre_fix_sha, state.pr_diff_files,
                            config["scope"]["generated_paths"])
if not ok:
    subprocess.run(["git", "reset", "--hard", pre_fix_sha], cwd=repo)
    report(item, f"fix touched out-of-scope files: {off}")
    continue
```

Push (with non-FF retry):

```bash
if ! git push 2>/tmp/push-err; then
  if grep -q "non-fast-forward\|rejected" /tmp/push-err; then
    git fetch "$HEAD_REMOTE" "$HEAD_BRANCH"
    if ! git rebase "$HEAD_REMOTE/$HEAD_BRANCH"; then
      git rebase --abort && git reset --hard "$PRE_FIX_SHA"
      # report and continue
    fi
    git push || { git reset --hard "$PRE_FIX_SHA"; # report and continue; }
  fi
fi
```

Record success in audit:

```python
state["audit"].append({
    "comment_id": item.comment_id,
    "comment_thread_id": item.thread_id,
    "reviewer": item.reviewer,
    "classification": item.classification,
    "commit_sha": git_rev_parse_HEAD(),
    "fix_pushed_at": now_iso,
    "in_cooldown_until": None,
})
state["handled_comment_ids"].append(item.comment_id)
```

### Step 6 -- Report unfixable items

Print a summary of items that could not be auto-fixed:

```python
key = N.escalation_key(kind=item.kind, name=item.name)

if item.thread_id and N.is_in_cooldown(state.audit, item.thread_id):
    print(f"[session-log] {key} in cooldown, suppressing")
    continue

if not N.backoff_due(state, key, config["notifications"]["per_item_backoff_minutes"]):
    print(f"[session-log] {key} backoff window not elapsed")
    continue

print(f"NEEDS ATTENTION: {key} -- {reason}")
N.macos_notify(title="PR Babysit", message=f"{key}: {reason}")
N.record_escalation(state, key, reason)
```

Notifications are printed to the conversation. On macOS, a native notification is also sent via `osascript`.

### Step 7 -- Heartbeat + state update

```python
L.heartbeat(owner, repo, pr_number)
S.save_state(owner, repo, pr_number, state)
L.release(owner, repo, pr_number)
```

Print a concise completion line with the PR number, fixed count, reported count, and whether the PR remains open.

### Exit paths

| Trigger | Cleanup |
|---|---|
| PR merged | delete state + release lock + exit |
| PR closed | same |
| Skill error | release lock + exit |

## Configuration

Place `.claude/pr-babysit.yaml` at the repo root. Every fix block is opt-in -- missing blocks mean that category is reported but not auto-fixed.

See `references/config-example.yaml` for a full reference.

## References

- `references/classify-comment.md` -- comment classification rules
- `references/fix-policy.md` -- in-scope vs report decision tree
- `references/config-example.yaml` -- reference `.claude/pr-babysit.yaml`
