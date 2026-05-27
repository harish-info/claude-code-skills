# Fix Policy — In-Scope vs Escalate Decision Tree

One-line summary per check type.

| Failure | In-scope criterion | Auto-fix | Escalate |
|---|---|---|---|
| Lint | File in PR diff | Run configured lint command, push if green | Untouched file |
| Snapshot | `auto_record: true` AND source or test file in PR diff | Method-level re-record, verify membership | Otherwise (default: always escalate) |
| Unit test | Test file or file-under-test in PR diff | Reproduce with `{{test_method}}`, fix obvious bugs | Assertion ambiguity, CI-only failures |
| Build/other CI | — | Never | Always |
| Merge conflict | Conflicts only in `safe_paths` | Resolve mechanically, validate, push | Otherwise |
| Review comment | Per `trigger_mode` (see classify-comment.md) | Per whitelist | Anything ambiguous |

Plus universal guardrails:
- **Scope check**: frozen `pr_diff_files` ensures fixes only touch files already in the PR diff
- **Merge-commit check**: merge commits verify resolved files against safe_paths
- **Validation gate**: every fix must pass local re-verification before push
- **Remote-head sync**: fetch latest remote head before push to avoid conflicts
- **Edit-revert cooldown**: prevents fix-revert loops on the same comment thread

Push policy: plain `git push` only. Non-FF triggers fetch + rebase + re-validate + retry once.
