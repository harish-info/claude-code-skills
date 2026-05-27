# Review Comment Classification Heuristics

Detailed rules for comment classification. Behavior depends on `config.fixes.comment_fix.trigger_mode`.

## Mode 1: `explicit_tag` (default)

Only act on comments whose body contains `@pr-babysit` or `@pr-babysit fix this`.
All other comments — even imperatives, even on PR-diff lines — escalate.

## Mode 2: `narrow_whitelist` (opt-in)

Act without an explicit tag, but only on this allowlist of transforms:

- **rename_local** — rename a local symbol (variable, parameter, private function). No public-API renames.
- **remove_unused** — remove unused code (import, variable, parameter) flagged by name in the comment.
- **formatting** — pure formatting / import order. No logic changes.
- **api_swap** — replace one API call with a named explicit equivalent (e.g., "use WarpText instead of Text").

For any whitelist match, ALL of these must hold or the comment escalates:

| Check | Why |
|---|---|
| Comment is on a line in the PR diff | Out-of-diff comments touch surrounding code |
| Comment body contains no `?` | Question masquerading as imperative |
| Comment is < 200 chars | Long comments encode intent |
| Proposed fix diff is single-file and <= 10 lines | Larger changes need a human |
| Dry-run fix passes the validation gate | Don't ship broken |
| Comment is from a human reviewer, not a bot | Bots are routed to CI failure handling |
| No prior bot fix in the same thread within last 24h (cooldown) | Prevents edit-revert loops |

Reviewer approval -> no action; loop continues until merge.
