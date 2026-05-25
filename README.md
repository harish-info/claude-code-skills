# claude-code-skills

Skills for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) that orchestrate multiple AI agents (Claude, Codex, AGY) to work together on code review and technical decision-making.

## What are Claude Code skills?

Skills are markdown files that teach Claude Code new workflows. When you type a slash command like `/multi-agent-review`, Claude Code loads the skill and follows its instructions. These skills dispatch multiple AI agents in parallel and synthesize their outputs.

## Skills

### multi-agent-review

Three-agent parallel code review. Claude Code acts as Tech Lead, dispatching Codex (Senior Dev) and AGY (Staff Engineer) to independently review your branch. All findings are collected, deduplicated, and adjudicated into a single verdict.

```
/multi-agent-review
/multi-agent-review --challenge
/multi-agent-review --base develop
```

| Flag | Effect |
|------|--------|
| `--challenge` | Adversarial review that questions design decisions and assumptions |
| `--base <ref>` | Base branch to diff against (auto-detects default branch) |

Output includes:
- Unified findings table with per-agent attribution
- Severity ratings (Blocker / Bug / Improvement / Nit)
- Verdict (Ship it / Needs fixes / Needs rework)
- Optional fix delegation to any available agent

### debate

Multi-round structured debate between Claude, Codex, and AGY on any technical topic. Each agent argues independently, responds to opponents, then the orchestrator synthesizes a verdict with consensus and divergence points.

```
/debate should we use GraphQL or REST for the new API
/debate --adversarial monorepo vs polyrepo
/debate --rounds 1 is this migration safe
```

| Flag | Effect |
|------|--------|
| `--adversarial` | Assigns explicit for/against/alternative positions |
| `--rounds N` | Override round count: 1 (quick) to 5 (deep) |

Modes:
- **Quick (1 round)** - all agents argue once, immediate synthesis
- **Standard (3 rounds)** - opening positions, rebuttals, closing arguments

## Agents

| Agent | Runtime | Role |
|-------|---------|------|
| Claude | Claude Code (built-in) | Always available. Acts as orchestrator and participant. |
| Codex | [Codex CLI plugin](https://github.com/openai/codex) | OpenAI's coding agent. Optional. |
| AGY | [Antigravity CLI](https://www.antigravity.dev/) | Google's Gemini-powered agent. Optional. |

Both skills degrade gracefully. Claude always runs. Codex and AGY are additive.

## Installation

Copy the `skills/` directory into your project or Claude Code config:

```bash
# project-level
cp -r skills/ /path/to/your/project/.claude/skills/

# or user-level
cp -r skills/ ~/.claude/skills/
```

Then invoke with `/multi-agent-review` or `/debate <topic>` in Claude Code.