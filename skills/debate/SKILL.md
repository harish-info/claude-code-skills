---
name: debate
description: Runs a multi-round structured debate between Claude, Codex, and AGY on a technical question, then synthesizes a verdict. Use to explore tradeoffs, compare approaches, stress-test a decision, or get adversarial perspectives. Invoke as /debate <topic> under Claude Code or $debate <topic> under Codex.
user_invocable: true
tools: Bash, Read, Write, Agent, AskUserQuestion
---

# Debate

Up to three independent agents argue a topic, respond to each other, then the host agent synthesizes a verdict.

## Argument parsing

Take the arguments from whichever form the host used: Claude Code expands
`$ARGUMENTS` from `/debate <topic>`; Codex invokes the skill as `$debate <topic>`
and substitutes nothing, so read the topic from the request that triggered the
skill. Never treat a literal `$ARGUMENTS` as the topic — that means the host did
not expand it.

- `--adversarial` — assign explicit for/against/alternative positions instead of exploratory
- `--rounds N` — round count (1-5), skips the mode prompt. 1 = Quick, 3 = Standard, other values use the Standard flow with an adjusted round count
- Everything else is the topic

If no topic is given, ask what to debate.

## Roster

```bash
ROSTER=$(ls ~/.claude/skills/.shared/agent-roster.sh ~/.codex/skills/.shared/agent-roster.sh 2>/dev/null | head -1)
[ -n "$ROSTER" ] || { echo "roster helper not found"; exit 1; }
eval "$($ROSTER)"
echo "Host: $HOST | Peers: $PEERS"
echo "CLAUDE_CMD=$CLAUDE_CMD | CODEX_CMD=$CODEX_CMD | AGY_CMD=$AGY_CMD"
```

Shell state does not survive between tool calls: re-run these lines at the top of
every later snippet that uses a `firefly_*` wrapper. Host-native subagents do
not use these shell wrappers; Claude and Codex each use their installed host.

The roster is optimistic — it checks that each agent is installed, not that it
answers. An agent named here can still fail at dispatch; drop it to unavailable
and re-check the agent count before Round 1 rather than assuming the announced
roster holds.

The host debates as itself and also acts as orchestrator and synthesizer. Announce the roster (`"Debate agents: Claude, Codex, AGY"`). Minimum 2 agents; if only the host is available, use the self-debate fallback below.

| Debater | How to dispatch |
|---------|-----------------|
| Host = Claude Code | `Agent` tool, so the arguing context stays separate from the synthesizing one |
| Host = Codex | Argue inline in the current session |
| Peer Claude | `firefly_claude "$(cat /tmp/debate-claude-r<N>.txt)"` |
| Peer Codex | `(unset CLAUDECODE; firefly_codex task --prompt-file /tmp/debate-codex-r<N>.txt --effort medium)` (companion) or `(unset CLAUDECODE; firefly_codex --sandbox read-only - < /tmp/debate-codex-r<N>.txt)` (`codex exec`) |
| Peer AGY | `firefly_agy 10m -p "$(cat /tmp/debate-agy-r<N>.txt)"` |

Strip `CLAUDECODE` when launching Codex: Claude Code exports it, children inherit
it, and a Codex peer that sees it resolves its own host as Claude.

Write every peer's prompt to its own file first, with a **quoted** heredoc
delimiter. Debate prompts embed the user's topic and the brief — backticks, `$`,
and code snippets are routine. An unquoted delimiter runs command substitution as
the file is written; a prompt typed onto the command line runs it at dispatch:

```bash
cat > /tmp/debate-codex-r1.txt << 'PROMPT'
<the round prompt, verbatim>
PROMPT
```

One file per agent per round, so a later round never clobbers a file still being
read. Clean them up after the synthesis.

This is read-only argumentation: pass `--sandbox read-only` to `codex exec` and
never `--write`. Never pass `--sandbox`/`--dangerously-skip-permissions` to AGY —
both break its `--print-timeout` and it hangs forever.

## Mode selection

If `--rounds N` was passed, use N rounds. Otherwise ask (`AskUserQuestion` under Claude Code, a plain numbered question under Codex):

1. **Quick (1 round)** — all agents argue once, immediate synthesis. Good for simple topics or fast signal.
2. **Standard (3 rounds)** — opening, rebuttals, closing, then synthesis. Better for complex or high-stakes topics.

## Context gathering

Build a **debate brief** that every agent receives, so all start from the same baseline. Detect the topic type:

| Topic contains | Gather | Cap |
|----------------|--------|-----|
| "branch", "changes", "diff", "PR", "commit" | Branch name, `git log main..HEAD --oneline`, `git diff main..HEAD --stat`, key file diffs. Summarize intent in 1-2 sentences. | 800 diff lines |
| "plan", "spec", "design", or a `.md` path | Read the document; extract key decisions, constraints, open questions. | 1000 words |
| Specific files, functions, or modules | Read them; summarize surrounding architecture in 2-3 sentences plus relevant snippets. | 500 code lines |
| None of the above | Use the topic text as-is. If it clearly relates to the current repo, name a few relevant paths with a one-line summary — do not dump file contents. | — |

Store this as `DEBATE_BRIEF` and inject it into every prompt.

## The debate prompt

One template covers every agent and every round. Fill the slots; nothing else changes between agents.

```
You are participating in a structured debate as {AGENT_NAME}.

{POSITION_INSTRUCTION}

Topic: {topic}

{DEBATE_BRIEF}

{ROUND_BLOCK}

RULES:
- Start with your thesis in the first sentence. No preamble.
- Cite specific evidence from the context — files, decisions, constraints, code.
- Do not concede unless you genuinely cannot counter the argument.
- Reference concrete details, not abstract principles.
- No conversational filler ("great question", "I appreciate", "my colleague").

Word limit: {LIMIT} words.
```

### `{ROUND_BLOCK}` per round

| Round | Block |
|-------|-------|
| 1 — Opening | *(empty)* |
| 2 — Rebuttal | `Your Round 1 position:`<br>`{own_r1}`<br><br>`Opponent positions:`<br>`{each opponent}: {their_r1}`<br><br>`Respond to the strongest opposing argument. Concede only what you must. Strengthen your remaining points. Identify where you converge or diverge.` |
| 3 — Closing | `Your Round 2 rebuttal:`<br>`{own_r2}`<br><br>`All Round 2 rebuttals:`<br>`{each opponent}: {their_r2}`<br><br>`This is the final round. State your final position. Acknowledge valid points your opponents made. Identify the key remaining disagreement. What should the user actually do?` |

### `{LIMIT}` per round

| Context type | Opening | Rebuttal | Closing |
|--------------|---------|----------|---------|
| Idea/General | 300 | 250 | 200 |
| Branch/Plan/Code | 450 | 300 | 250 |

### `{POSITION_INSTRUCTION}`

**Exploratory** (default): `Take your honest position on this topic. Do not hedge or try to be balanced — that is the synthesizer's job.`

**Adversarial** (`--adversarial`): assign positions randomly across available agents — 3 agents get FOR / AGAINST / THIRD ALTERNATIVE, 2 agents get FOR / AGAINST. Then: `You have been assigned a position: [POSITION]. Argue this position as strongly as possible, even if you personally disagree. Find the strongest possible case for this side.`

## Execution

Dispatch all agents for a round **in parallel**, wait for the round to complete, then start the next. Capture outputs as `{agent}_r{N}`. When the host is Codex it argues inline, so it is not parallel with itself: background the peer calls first, then write your own argument while they run.

After Round 1 in Standard mode, show a one-line summary per agent. **Convergence check:** if all agents reached the same conclusion, announce it and still run the remaining rounds — agreement on a conclusion is not agreement on reasoning.

Re-inject the topic every round to prevent drift. If an agent fails mid-debate, continue with the rest and note the failure. Clean up `/tmp/debate-*` afterwards.

## Synthesis

The host produces the synthesis directly — do not dispatch a subagent, you already have every round. When the host also debated, treat your own argument with exactly the same scrutiny as the others.

```markdown
## Debate: {topic}

**Agents:** {list} | **Mode:** {Quick (1 round) | Standard (3 rounds)}

### Positions (Round 1)
**{Agent}:** {2-3 sentence summary}   ← one line per agent

### Key exchanges                      ← Standard mode only
- {sharpest point of disagreement and how it evolved}
- {strongest concession made by any agent}
- {argument that shifted or strengthened across rounds}

### Final positions (Round 3)          ← Standard mode only
**{Agent}:** {1-2 sentence final stance}

### Verdict
**Consensus:** {where agents agreed}
**Divergence:** {remaining disagreements}
**Recommendation:** {your synthesis — what the user should actually do}
**Verify:** {concrete things to check before acting}
```

## Rules

- Do NOT take a side during the rounds — let each agent argue independently.
- Do NOT edit the agents' outputs — represent them faithfully.
- Read-only: no `--write` on Codex calls.
- If AGY returns a 503 or error mid-debate, drop it for the remaining rounds and continue. No retry.

## Fallback cascade

Automatic, no prompt needed.

- **3 agents** → three-way debate.
- **2 agents** → two-way. Announce who is missing, reference one opponent instead of two, and use FOR/AGAINST only in adversarial mode.
- **1 agent (host only)** → self-debate with two opposing personas:
  - **SKEPTIC**: "You believe this approach will fail. Find every flaw, risk, and hidden assumption. Argue against it forcefully."
  - **ADVOCATE**: "You believe this is the right approach. Defend it with specific evidence and address likely objections."
  Under Claude Code, run these as two separate subagents. Under Codex, argue each persona in turn before synthesizing.
