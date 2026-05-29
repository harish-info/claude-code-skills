---
name: debate
description: Multi-round structured debate between Claude, Codex, and AGY. Use to explore tradeoffs, compare approaches, stress-test ideas, or get adversarial perspectives on a technical decision. Invoke /debate <topic>.
tools: Bash, Read, Write, Agent, AskUserQuestion
---

# Debate

Orchestrate a structured debate between up to three independent LLM agents (Claude, Codex, AGY) on a user-provided topic. Each model argues independently, responds to each other, then the orchestrator synthesizes a verdict.

## Argument parsing

Raw arguments: `$ARGUMENTS`

Parse:
- `--adversarial` — assign explicit for/against/alternative positions instead of exploratory
- `--rounds N` — override round count (1-5), skips mode selection prompt. 1 = Quick, 3 = Standard, other values use Standard flow with adjusted round count
- Everything else is the debate topic

If no topic is provided, ask the user what they want to debate.

## Agent detection

Run these checks in parallel at startup:

**Claude** — always available (Agent tool).

**Codex:**
```bash
CODEX_ROOT="$(find ~/.claude/plugins/cache/openai-codex -name codex-companion.mjs -path '*/scripts/*' 2>/dev/null | head -1 | xargs dirname | xargs dirname)"
```
Available if `CODEX_ROOT` is non-empty.

**AGY:**
```bash
# Kill stale AGY processes from previous sessions before detection
pkill -f "agy.*(--sandbox|--print).*/tmp/debate-agy" 2>/dev/null || true
which agy 2>/dev/null && agy --print-timeout 30s -p "respond with only the word READY" 2>&1 | grep -qi "ready"
```
Available if the grep succeeds. AGY runs via `agy -p "prompt"` in headless mode. Do NOT use `--sandbox` or `--dangerously-skip-permissions` as both break AGY's `--print-timeout` mechanism, causing indefinite hangs. Use bare `-p` with `--print-timeout` instead.

Announce the roster: `"Debate agents: Claude, Codex, AGY"` or list whichever are available. Minimum 2 agents required. If only Claude is available, use Claude-vs-Claude with opposing personas (see Fallback section).

## Mode selection

If `--rounds N` was passed, skip this step and use N rounds.

Otherwise, ask the user:

```
AskUserQuestion({
  questions: [{
    question: "What kind of debate do you want?",
    header: "Mode",
    options: [
      { label: "Quick (1 round)", description: "All agents argue once, immediate synthesis. Good for simple topics or fast signal." },
      { label: "Standard (3 rounds)", description: "Opening positions, rebuttals, closing arguments + synthesis. Better for complex or high-stakes topics." }
    ],
    multiSelect: false
  }]
})
```

Map: Quick → 1 round. Standard → 3 rounds.

## Context gathering

Build a **debate brief** based on topic type. All agents receive the same brief for fairness and to ensure they start from the same baseline (all three can independently explore the repo for additional context).

### Detection heuristics and context rules

**Branch context** — topic contains "branch", "changes", "diff", "PR", or "commit":
```bash
# Gather in parallel
git log main..HEAD --oneline
git diff main..HEAD --stat
git diff main..HEAD -- <key files only, cap at 800 lines total>
```
Include: branch name, commit list, diff stat, key diffs. Summarize intent in 1-2 sentences.

**Plan/Spec context** — topic contains "plan", "spec", "design", or references a `.md` file:
Read the referenced document. Extract the key decisions, constraints, and open questions. Cap at 1000 words.

**Code context** — topic references specific files, functions, or modules:
Read those files. Summarize the surrounding architecture in 2-3 sentences. Include relevant code snippets (cap 500 lines).

**Idea/General** — none of the above:
Use the topic text as-is. If the topic clearly relates to the current repo, briefly identify relevant files/context (a few paths and a one-line summary — do not dump file contents).

Store the gathered context as `DEBATE_BRIEF`. This gets injected into every agent prompt.

## Prompt rules

Every agent prompt (opening, rebuttal, closing) includes these instructions:

```
RULES:
- Start with your thesis in the first sentence. No preamble.
- Cite specific evidence from the context — files, decisions, constraints, code.
- Do not concede unless you genuinely cannot counter the argument.
- Reference concrete details, not abstract principles.
- No conversational filler ("great question", "I appreciate", "my colleague").
```

### Word limits (scale with context type)

| Context type | Opening | Rebuttal | Closing |
|-------------|---------|----------|---------|
| Idea/General | 300 | 250 | 200 |
| Branch/Plan/Code | 450 | 300 | 250 |

### Position assignment

**Exploratory mode** (default): each agent argues their genuine recommendation.
Add to prompt: `"Take your honest position on this topic. Do not hedge or try to be balanced — that is the synthesizer's job."`

**Adversarial mode** (`--adversarial`): assign positions randomly across available agents.
- 3 agents: one argues FOR, one argues AGAINST, one argues for a THIRD ALTERNATIVE
- 2 agents: one argues FOR, one argues AGAINST

Add to prompt: `"You have been assigned a position: [POSITION]. Argue this position as strongly as possible, even if you personally disagree. Find the strongest possible case for this side."`

## Execution

### Quick mode (1 round)

**Step 1 — All agents argue in parallel:**

Dispatch all available agents simultaneously (single message, multiple tool calls):

**Claude** — Agent tool:
```
Agent({
  description: "Debate: Claude position",
  prompt: "You are participating in a structured debate as CLAUDE.\n\n{POSITION_INSTRUCTION}\n\nTopic: {topic}\n\n{DEBATE_BRIEF}\n\n{RULES}\n\nWord limit: {OPENING_LIMIT} words."
})
```

**Codex** — write prompt file, call codex-companion:
```bash
cat > /tmp/debate-codex.txt << 'PROMPT'
You are participating in a structured debate as CODEX.

{POSITION_INSTRUCTION}

Topic: {topic}

{DEBATE_BRIEF}

{RULES}

Word limit: {OPENING_LIMIT} words.
PROMPT

node "${CODEX_ROOT}/scripts/codex-companion.mjs" task --prompt-file /tmp/debate-codex.txt --effort medium
```

**AGY** — headless CLI:
```bash
agy --print-timeout 10m -p "You are participating in a structured debate as AGY.

{POSITION_INSTRUCTION}

Topic: {topic}

{DEBATE_BRIEF}

{RULES}

Word limit: {OPENING_LIMIT} words."
```

Capture outputs as `claude_r1`, `codex_r1`, `agy_r1`.

**Step 2 — Synthesize** (see Synthesis section).

### Standard mode (3 rounds)

**Round 1 — Opening positions (parallel):**

Same as Quick mode Step 1. Dispatch all agents in parallel with opening prompts.

After Round 1, display a brief update: `"Round 1 complete. Positions: Claude — {one-line summary}, Codex — {one-line summary}, AGY — {one-line summary}"`

**Convergence check:** If all agents reached the same core conclusion in Round 1, announce: `"All agents converged on: {conclusion}. Proceeding to rebuttals to stress-test the agreement."` Do NOT skip rounds — convergence on conclusion doesn't mean convergence on reasoning.

**Round 2 — Rebuttals (parallel):**

Each agent receives all opponents' Round 1 arguments and responds.

**Claude:**
```
Agent({
  description: "Debate round 2: Claude rebuttal",
  prompt: "You are in round 2 of a structured debate as CLAUDE.\n\nTopic: {topic}\n\n{DEBATE_BRIEF}\n\nYour Round 1 position:\n{claude_r1}\n\nOpponent positions:\nCODEX said: {codex_r1}\nAGY said: {agy_r1}\n\nRespond to the strongest opposing argument. Concede only what you must. Strengthen your remaining points. Identify where you converge or diverge.\n\n{RULES}\n\nWord limit: {REBUTTAL_LIMIT} words."
})
```

**Codex:**
```bash
cat > /tmp/debate-codex-r2.txt << 'PROMPT'
You are in round 2 of a structured debate as CODEX.

Topic: {topic}

{DEBATE_BRIEF}

Your Round 1 position:
{codex_r1}

Opponent positions:
CLAUDE said: {claude_r1}
AGY said: {agy_r1}

Respond to the strongest opposing argument. Concede only what you must. Strengthen your remaining points. Identify where you converge or diverge.

{RULES}

Word limit: {REBUTTAL_LIMIT} words.
PROMPT

node "${CODEX_ROOT}/scripts/codex-companion.mjs" task --prompt-file /tmp/debate-codex-r2.txt --effort medium
```

**AGY:**
```bash
agy --print-timeout 10m -p "You are in round 2 of a structured debate as AGY.

Topic: {topic}

{DEBATE_BRIEF}

Your Round 1 position:
{agy_r1}

Opponent positions:
CLAUDE said: {claude_r1}
CODEX said: {codex_r1}

Respond to the strongest opposing argument. Concede only what you must. Strengthen your remaining points. Identify where you converge or diverge.

{RULES}

Word limit: {REBUTTAL_LIMIT} words."
```

Capture outputs as `claude_r2`, `codex_r2`, `agy_r2`.

**Round 3 — Closing arguments (parallel):**

Each agent sees all Round 2 rebuttals and writes their final position.

**Claude:**
```
Agent({
  description: "Debate round 3: Claude closing",
  prompt: "You are in the final round of a structured debate as CLAUDE.\n\nTopic: {topic}\n\n{DEBATE_BRIEF}\n\nYour Round 2 rebuttal:\n{claude_r2}\n\nAll Round 2 rebuttals:\nCODEX said: {codex_r2}\nAGY said: {agy_r2}\n\nThis is the final round. State your final position on the topic. Acknowledge valid points your opponents made. Identify the key remaining disagreement. What should the user actually do?\n\n{RULES}\n\nWord limit: {CLOSING_LIMIT} words."
})
```

**Codex:**
```bash
cat > /tmp/debate-codex-r3.txt << 'PROMPT'
You are in the final round of a structured debate as CODEX.

Topic: {topic}

{DEBATE_BRIEF}

Your Round 2 rebuttal:
{codex_r2}

All Round 2 rebuttals:
CLAUDE said: {claude_r2}
AGY said: {agy_r2}

This is the final round. State your final position on the topic. Acknowledge valid points your opponents made. Identify the key remaining disagreement. What should the user actually do?

{RULES}

Word limit: {CLOSING_LIMIT} words.
PROMPT

node "${CODEX_ROOT}/scripts/codex-companion.mjs" task --prompt-file /tmp/debate-codex-r3.txt --effort medium
```

**AGY:**
```bash
agy --print-timeout 10m -p "You are in the final round of a structured debate as AGY.

Topic: {topic}

{DEBATE_BRIEF}

Your Round 2 rebuttal:
{agy_r2}

All Round 2 rebuttals:
CLAUDE said: {claude_r2}
CODEX said: {codex_r2}

This is the final round. State your final position on the topic. Acknowledge valid points your opponents made. Identify the key remaining disagreement. What should the user actually do?

{RULES}

Word limit: {CLOSING_LIMIT} words."
```

Capture outputs as `claude_r3`, `codex_r3`, `agy_r3`.

## Synthesis

After all rounds complete, YOU (the orchestrator) produce the final synthesis. Do not dispatch a subagent — you have all the context.

Read through all rounds and write:

### Quick mode output

```markdown
## Debate: {topic}

**Agents:** {list} | **Mode:** Quick (1 round)

### Positions
**Claude:** {2-3 sentence summary}
**Codex:** {2-3 sentence summary}
**AGY:** {2-3 sentence summary}

### Verdict
**Consensus:** {bullet points where agents agreed}
**Divergence:** {bullet points of disagreement}
**Recommendation:** {your synthesis — what should the user do}
**Verify:** {concrete things to check before acting}
```

### Standard mode output

```markdown
## Debate: {topic}

**Agents:** {list} | **Mode:** Standard (3 rounds)

### Positions (Round 1)
**Claude:** {2-3 sentence summary}
**Codex:** {2-3 sentence summary}
**AGY:** {2-3 sentence summary}

### Key exchanges
- {most interesting point of disagreement and how it evolved}
- {strongest concession made by any agent}
- {argument that shifted or strengthened across rounds}

### Final positions (Round 3)
**Claude:** {1-2 sentence final stance}
**Codex:** {1-2 sentence final stance}
**AGY:** {1-2 sentence final stance}

### Verdict
**Consensus:** {bullet points where agents converged}
**Divergence:** {remaining disagreements}
**Recommendation:** {your synthesis — what should the user do, weighing all perspectives}
**Verify:** {concrete things to check before acting on this recommendation}
```

## Rules

- Do NOT take a side during rounds — let each agent argue independently
- Do NOT edit the agents' outputs — present them faithfully in the synthesis
- Do NOT use `--write` on Codex calls — this is read-only argumentation
- Re-inject the topic in every round's prompt to prevent drift
- If an agent fails mid-debate (timeout, error), continue with remaining agents and note the failure
- Clean up `/tmp/debate-codex*` files after completion (AGY prompts are passed inline, no temp files)

## Fallback cascade

Automatic, no user prompt needed:

**3 agents available** → normal three-way debate.

**2 agents available** → two-way debate. Announce which agent is missing. Adjust prompts to reference one opponent instead of two. Adversarial mode uses FOR/AGAINST only (no third alternative).

**1 agent (only Claude)** → Claude-vs-Claude. Dispatch two Claude subagents:
- Agent A: `"You are a SKEPTIC. You believe this approach will fail. Find every flaw, risk, and hidden assumption. Argue against it forcefully."`
- Agent B: `"You are an ADVOCATE. You believe this is the right approach. Defend it with specific evidence and address likely objections."`

**AGY-specific handling:** If AGY returns a 503 or error during a round, log it and continue without AGY for remaining rounds. Do not retry — the debate doesn't need to block on transient API issues.
