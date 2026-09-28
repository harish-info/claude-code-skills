# Codex peer troubleshooting

Read this only when the Codex peer fails or returns empty output while Claude Code is the host. Diagnose before retrying — a blind retry wastes a full review cycle.

```bash
CODEX_ROOT="$(find "$HOME/.claude/plugins/cache/openai-codex" -name codex-companion.mjs \
  -path '*/scripts/*' 2>/dev/null | sort -V | tail -1 | xargs dirname | xargs dirname)"
if [ -z "$CODEX_ROOT" ]; then
  echo "PLUGIN_MISSING"
else
  node "$CODEX_ROOT/scripts/codex-companion.mjs" setup --json
fi
```

`sort -V | tail -1` picks the newest installed plugin version. Several versions are usually present side by side, so `head -1` would pick an arbitrary one.

| Diagnosis | Action |
|-----------|--------|
| `PLUGIN_MISSING` | Tell the user to run `/plugin marketplace add openai/codex-plugin-cc`, then `/plugin install codex@openai-codex`, then `/reload-plugins`, then re-run the review. **Stop.** |
| `node.available: false` | Node.js is not installed. Tell the user to install it (e.g. `brew install node`) and re-run. **Stop.** |
| `codex.available: false` | Codex CLI is not installed. If `npm.available: true`, offer to run `npm install -g @openai/codex`; re-run the diagnostic to verify, then continue. |
| `auth.loggedIn: false` | "Codex is installed but not logged in. Run `!codex login` to authenticate, then re-run the review." **Stop.** |
| `sessionRuntime.mode` is not `"shared"`, or the socket endpoint is unreachable | The shared runtime is not active. Tell the user to run `/plugin reload codex@openai-codex`, then re-run. **Stop.** |
| `ready: false`, nothing specific flagged | Unknown setup failure. Show the full JSON and ask the user to check the plugin installation. |
| `ready: true` but Codex still failed | Retry once in the foreground with a 5-minute timeout. If that also fails, mark Codex unavailable and continue with the remaining agents. |

## Checking progress mid-run

```bash
node "$CODEX_ROOT/scripts/codex-companion.mjs" status
```

## Fallback

If the companion runtime is unavailable but the `codex` binary is on PATH, the roster helper falls back to `CODEX_KIND=cli` and dispatch becomes `codex exec "<prompt>"`. That path has no shared session and no `review` subcommand shortcut — send the full review prompt as text.
