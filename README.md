# claude-code-skills

Skills for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) that automate PR workflows and orchestrate multiple AI agents for code review and technical decision-making.

## What are Claude Code skills?

Skills are markdown files that teach Claude Code new workflows. When you type a slash command like `/pr-babysit`, Claude Code loads the skill and follows its instructions.

## Skills

### pr-babysit

Automated PR babysitting. Monitors your open PRs, auto-fixes what it safely can (lint failures, test failures, merge conflicts, review comments), and reports what needs your attention.

Each invocation runs a single one-shot pass. For continuous monitoring, pair it with `/loop`.

```
# one-shot: check current branch's PR
/pr-babysit

# one-shot: check a specific PR
/pr-babysit https://github.com/owner/repo/pull/123

# one-shot: sweep all your open PRs
/pr-babysit --mine

# classify only, no fixes
/pr-babysit --dry-run

# recurring: check every 15 minutes
/loop 15m /pr-babysit https://github.com/owner/repo/pull/123

# recurring: sweep all your PRs every 20 minutes
/loop 20m /pr-babysit --mine
```

| Flag | Effect |
|------|--------|
| `<url>` | Target a specific PR |
| `--mine` | Sweep all your open non-draft PRs |
| `--dry-run` | Classify and report only, no fixes or pushes |
| `--takeover` | Reclaim lock from another session |

**Configuration:** place a `.claude/pr-babysit.yaml` in your repo root to define which CI failures are auto-fixable and what commands to run. See `skills/pr-babysit/references/config-example.yaml` for a full reference.

What it auto-fixes:
- Lint failures (on files in the PR diff)
- Test failures (on files in the PR diff)
- Merge conflicts (in configured safe paths like lockfiles)
- Review comments (tagged with `@pr-babysit` or matching a narrow whitelist)

What it reports but won't touch:
- CI failures on files outside the PR diff
- Ambiguous review comments
- Build/infrastructure failures
- Merge conflicts in non-safe paths

### fix-pr-comments

Fetches review comments from a GitHub PR, categorizes them by severity (High/Medium/Minor/Skip), presents them in a table, asks what to fix, then applies scoped fixes.

```
# fix comments on current branch's PR
/fix-pr-comments

# fix comments on a specific PR
/fix-pr-comments https://github.com/owner/repo/pull/123
```

Works with GitHub.com and GitHub Enterprise. Also supports a headless `--auto` mode for programmatic callers like pr-babysit.

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

### gaslight

A hard adversarial re-check of work you just finished. Agents tend to perform better when you "gaslight" them — insisting their finished work is wrong pushes them out of generation mode (which satisfices and stops at "good enough") and into an adversarial exploration/verification phase, where they hunt for problems instead of defending their output. This skill weaponizes that effect deliberately by treating the just-completed work as if it contains at least one real bug. A hard boundary prevents the pressure from backfiring: the agent may only report or fix issues it can prove with evidence — inventing a bug or "fixing" working code is explicitly disallowed.

```
/gaslight
```

Use it right after declaring a feature or fix done, to surface edge cases, error paths, and wrong assumptions the first pass missed. If a rigorous pass finds nothing, the correct answer is "no bug found" with proof — it will not manufacture one.

## Agents

| Agent | Runtime | Role |
|-------|---------|------|
| Claude | Claude Code (built-in) | Always available. Acts as orchestrator and participant. |
| Codex | [Codex CLI plugin](https://github.com/openai/codex) | OpenAI's coding agent. Optional. |
| AGY | [Antigravity CLI](https://www.antigravity.dev/) | Google's Gemini-powered agent. Optional. |

multi-agent-review and debate degrade gracefully. Claude always runs. Codex and AGY are additive. pr-babysit and fix-pr-comments use Claude only.

## Installation

Copy the `skills/` directory into your project or Claude Code config:

```bash
# project-level
cp -r skills/ /path/to/your/project/.claude/skills/

# or user-level
cp -r skills/ ~/.claude/skills/
```

Then invoke any skill with its slash command in Claude Code.
