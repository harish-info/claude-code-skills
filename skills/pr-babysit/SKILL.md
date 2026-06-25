---
name: pr-babysit
description: Runs one babysitting pass on an open GitHub PR — syncs, fixes what is safe (CI, simple review comments, merge conflicts), escalates the rest, exits clean on merge/close. For recurrence use Claude's /loop (e.g. /loop 15m /pr-babysit <url>). Invoke /pr-babysit [<url>|--mine|--dry-run].
user_invocable: true
tools: Bash, Read, Edit, Write, Grep, Glob, AskUserQuestion
---

# PR Babysit

Runs **one** pass over a PR: sync the branch, fix what can be fixed safely, escalate the
rest, and exit cleanly when the PR is merged or closed. One pass only — no built-in loop.

## Invocation

| Form | Behavior |
|------|----------|
| `/pr-babysit` | One pass for the current branch's PR |
| `/pr-babysit <url>` | One pass for a specific PR (incl. drafts) |
| `/pr-babysit --mine` | One pass over each of your open non-draft PRs |
| `/pr-babysit --dry-run` | Read-only: classify and print the worklist, no fixes/commits/push |

## Recurrence (use Claude's /loop)

There is no `--watch`. To babysit on an interval, wrap this skill with the built-in `/loop`:

```
/loop 15m /pr-babysit https://github.com/org/repo/pull/123
```

`/loop` is session-scoped and stops when you stop it or end the session — that is the
intended bound. Set the interval to taste.

## One pass

1. **Resolve the PR.** From the arg, current branch (`gh pr view --json ...`), or `--mine`
   (`gh pr list --author @me --state open`). For enterprise hosts pass `--hostname` / set
   `GH_HOST` (gh defaults to github.com and silently 404s otherwise).
2. **Sync.** `git fetch` the PR head; if it advanced since your last local state, re-read the
   diff before doing anything. Never act on a stale checkout.
3. **Gather state** in parallel: `gh pr checks`, reviews, and inline review comments
   (`gh api --paginate`). Note `mergeStateStatus` for conflicts.
4. **Build the worklist** — classify each item as *fixable* or *escalate* (see policy below).
5. **Fix sequentially, fail-fast.** After each fix: re-run the relevant check/build locally,
   confirm the change stays in scope (only touches files already in the PR diff, or generated
   paths), commit, and push. On a non-fast-forward push, rebase on the latest head and retry
   once; if it still races, stop and escalate.
6. **Escalate** anything not safely fixable: leave a concise note (PR comment or your output)
   describing what is blocked and why. Don't guess at intent.
7. **Exit.** If the PR is merged or closed, say so and stop. Otherwise report what was fixed,
   what was pushed, and what was escalated.

## Fix policy

**Safe to auto-fix** (only when the failure/comment maps cleanly onto files already in the diff):
- Formatting / lint autofixes (e.g. detekt, ktlint, prettier) — apply the tool's own fix.
- Snapshot/golden updates (e.g. paparazzi) when the diff explains the change.
- Unit test breakages with an obvious, in-scope cause.
- Merge conflicts that resolve mechanically and stay scoped to the PR's own changes.
- Review comments that are explicit, single-file, small (≤ ~10 lines), and unambiguous.

**Always escalate** (never auto-fix):
- Build failures, unfamiliar CI failures, anything needing design judgment.
- Comments that ask a question, span multiple files, or are ambiguous.
- Any fix that would touch files outside the PR diff.
- Conflicts that require understanding intent to resolve.

## Guardrails

- **Scope check** every fix: changed files must already be in the PR diff (or be generated
  output of a diffed source). If a fix wants to wander, escalate instead.
- **Validate before push**: re-run the check the fix targets; a fix that doesn't go green is
  not a fix.
- **Re-sync before push**: always push onto the current remote head.
- **No loops, no thrash**: one pass. If you already pushed a fix for an item this pass, don't
  re-fix it. Recurrence is `/loop`'s job, not this skill's.
- **Confirm before merging**: this skill does not auto-merge. If a PR looks merge-ready, say so
  and let the operator (or a reviewer) merge.
