# claude-code-skills

Claude Code skills for multi-agent code review and structured debates using Claude, Codex, and AGY.

## Skills

### multi-agent-review

Three-agent parallel code review. Claude (Tech Lead) adjudicates findings from Codex (Senior Dev) and AGY (Staff Engineer). Produces a unified verdict with severity ratings and optional fix delegation.

Usage: `/multi-agent-review` or `/multi-agent-review --challenge`

Flags:
- `--challenge` - adversarial review that questions design decisions and assumptions
- `--base <ref>` - base branch to diff against (auto-detects default branch)

### debate

Multi-round structured debate between Claude, Codex, and AGY on any topic. Each agent argues independently, responds to opponents, then the orchestrator synthesizes a verdict.

Usage: `/debate <topic>` or `/debate --adversarial <topic>`

Flags:
- `--adversarial` - assigns explicit for/against/alternative positions
- `--rounds N` - override round count (1-5)

Modes:
- Quick (1 round) - all agents argue once, immediate synthesis
- Standard (3 rounds) - opening positions, rebuttals, closing arguments

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
- [Codex CLI plugin](https://github.com/openai/codex) (optional, for Codex agent)
- [AGY (Antigravity CLI)](https://www.antigravity.dev/) (optional, for AGY agent)

Both skills degrade gracefully. Claude always runs. Codex and AGY are additive.

## Installation

Copy the `skills/` directory into your project or Claude Code config:

```bash
# project-level (recommended)
cp -r skills/ /path/to/your/project/.claude/skills/

# or user-level
cp -r skills/ ~/.claude/skills/
```

Then invoke with `/multi-agent-review` or `/debate <topic>` in Claude Code.

## License

MIT
