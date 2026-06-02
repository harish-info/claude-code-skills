---
name: debate
description: Multi-round structured debate between Claude, Codex, and AGY. Use to explore tradeoffs, compare approaches, stress-test ideas, or get adversarial perspectives on a technical decision. Invoke /debate <topic>.
tools: Bash, Read, Write, Agent, AskUserQuestion
---

# Debate

Run a structured debate between Claude, Codex, and AGY. Agents argue independently; the orchestrator synthesizes a verdict.

## Arguments

- `$ARGUMENTS` minus flags is the topic.
- `--adversarial`: assign FOR / AGAINST / THIRD ALTERNATIVE.
- `--rounds N`: use N rounds, 1-5. `1` means quick. If omitted, ask Quick (1) vs Standard (3).
- If topic is missing, ask the user.

## Agent Setup

- Claude: always available through `Agent`.
- Codex: available when `CODEX_ROOT="$(find ~/.claude/plugins/cache/openai-codex -name codex-companion.mjs -path '*/scripts/*' 2>/dev/null | head -1 | xargs dirname | xargs dirname)"` is non-empty.
- AGY: available when `which agy && agy --print-timeout 30s -p "respond with only the word READY" | grep -qi ready`.
- Kill stale AGY debate processes first. Never use AGY `--sandbox` or `--dangerously-skip-permissions`; use `agy --print-timeout 10m -p`.
- Minimum two agents. If only Claude is available, run two Claude personas with opposing positions.

Announce the roster.

## Context Brief

Give every agent the same `DEBATE_BRIEF`.

- Branch/PR/diff topic: include branch, `git log main..HEAD --oneline`, `git diff --stat`, and key diffs capped at 800 lines.
- Plan/spec topic: read the referenced doc and summarize decisions, constraints, open questions.
- Code topic: read referenced files and summarize architecture plus relevant snippets.
- General idea: use the topic as-is plus minimal repo context if obvious.

## Prompt Rules

Every agent prompt must say:

```text
Start with your thesis. No preamble.
Cite concrete evidence from the brief.
Do not hedge for balance; the synthesizer handles balance.
No filler.
Word limit: opening 300-450, rebuttal 250-300, closing 200-250.
```

Adversarial mode adds: `You have been assigned a position: [POSITION]. Argue it strongly even if you disagree.`

## Rounds

1. Opening: dispatch all agents in parallel.
2. Rebuttal: give each agent all other openings and ask for strongest counterargument.
3. Closing: give each agent rebuttals and ask for final recommendation.

For `--rounds 1`, skip rebuttal/closing and synthesize after openings. For other N, repeat rebuttal as needed.

Use prompt files for Codex:

```bash
node "$CODEX_ROOT/scripts/codex-companion.mjs" task --prompt-file /tmp/debate-codex.txt --effort medium
```

Use inline prompt for AGY:

```bash
agy --print-timeout 10m -p "<prompt>"
```

## Synthesis

Output:

```markdown
## Verdict
<thesis>

## Strongest Arguments
- Claude: ...
- Codex: ...
- AGY: ...

## Decision
- Recommendation:
- Why:
- Risks:
- Next action:
```

Name unavailable agents and why. Do not invent their views.
