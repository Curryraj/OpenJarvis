# The Team

Your agent roster. **Active** = created and runnable now (`~/.openjarvis/agents.db`).
**Bench** = agent types that ship with OpenJarvis; activate any with `new_agent.py`.

_All run on your local model (qwen2.5:7b). No cloud._

## Active

| Agent | Type | Role | Tools | Status |
|---|---|---|---|---|
| **CEO** | `orchestrator` | Delegates & assigns — reads a request, picks the right agent, hands off, combines results. **Real delegation**, wired 2026-07-13 via `delegate_to_agent` (see below). **Fixed 2026-07-13:** root cause of unreliable/empty responses was `instruction` being embedded as text in the USER turn instead of the SYSTEM message — with tools attached, qwen2.5:7b/Ollama returned genuinely empty messages (no content, no tool_calls) 100% of the time with that layout, 0% with the identical text as a proper system message. Fixed in `executor.py` — see "Instruction routing fix" below. Verified 3/3 on previously-100%-failing prompts, including real Coder delegation with actual code execution. | `delegate_to_agent`, `memory_search` | idle |
| **second-brain** | `monitor_operative` | Owns the daily knowledge digest; retrieves from your notes + captured facts. **Changed 2026-07-13:** no longer relies on blind auto-injected memory context (see "Memory: on-demand, not auto-injected" below) — now calls `memory_search` itself. | `memory_search` | idle |
| **Researcher** | `deep_research` | Digs your notes + the live web, writes a researched summary. | **Playwright browser** (navigate, snapshot, click, find, screenshot) + `memory_search` | idle — verified reliable across multiple runs |
| **Coder** | `orchestrator` | Writes, edits, and runs code. Sandboxed to the project dir + `~/.openjarvis/workspace/`. Note: **not** `native_react` — that type's regex-based Thought/Action parsing was unreliable with qwen2.5:7b in testing (silent hallucinated "success" with no tool call on ~1/4 runs); `orchestrator`'s native function-calling mode (same mechanism Researcher uses) was reliable across 3/3 verified runs. | `file_read`, `file_write`, `apply_patch`, `shell_exec`, `code_interpreter`, `repl`, `think`, `memory_search` | idle — verified: write, run, read-modify-write, `git status` via shell_exec, all correct |
| **Assistant** | `simple` | Fast one-shot Q&A, no tools. | — | idle — verified |
| **Monitor** | `monitor_operative` | Watches OpenJarvis's own git log for new commits since its last check, using `memory_store`/`memory_retrieve` for cross-run state. Re-verified 2026-07-13 after the instruction-routing fix: correctly reported the real current commit hash (`97be019`), no hallucination. **Known limitation (unchanged):** doesn't consistently call `memory_retrieve` first — sometimes re-reports already-seen commits as "new" instead of correctly diffing. Not chased further. | `shell_exec`, `memory_store`, `memory_retrieve`, `think` | idle — real-data reporting verified; stateful dedup unreliable |

## Instruction routing fix (2026-07-13)

Every managed agent's `config["instruction"]` (its standing role/task text) used to be embedded
as plain text inside the USER turn (`"Standing instruction: {instruction}"`,
`executor.py`). Root-caused via direct Ollama HTTP calls with controlled variables: with function-
calling tools attached, qwen2.5:7b returns a message with **empty content AND no tool_calls**
(~30 completion tokens silently discarded by Ollama's chat template) **100% of the time** when
instructional text lives in the user turn — **0% of the time** with the identical text as a proper
system message. This was the actual dominant cause of CEO's (and any instruction-having managed
agent's) unreliable/empty responses — bigger than the earlier-diagnosed "small-model stalls on
natural phrasing" theory. Fixed: `instruction` (merged with `system_prompt` if both set) now flows
into `agent_kwargs["system_prompt"]` before agent construction; the user-turn `input_text` only
carries the date/tick-note/pending-message scaffolding. Regression tests:
`tests/agents/test_executor_tools.py::test_executor_routes_instruction_through_system_prompt` +
`test_executor_combines_system_prompt_and_instruction`. Also fixed a related bug found in the same
pass: `OrchestratorAgent._run_function_calling` (`orchestrator.py`) built messages without ever
forwarding `self._system_prompt` — only the `structured` mode did — so even a correctly-supplied
`system_prompt` kwarg was silently dropped for CEO/Coder's default function-calling mode.

**Note:** `monitor_operative`-type agents (Monitor, second-brain) build a rich default system
prompt (tool descriptions + strategy + a "retrieve before answering" rule) when `self._system_prompt`
is unset, but use *only* the configured value verbatim when it *is* set — so an agent with both a
custom `instruction` and this type loses that default scaffolding now (previously it always got the
default, since `instruction` never reached `system_prompt` at all). Monitor was re-verified working
correctly despite this; flagging as a known nuance, not a regression severe enough to chase tonight.

## Stall-detection fix (2026-07-13, superseded in importance by the instruction-routing fix above)

Separately, qwen2.5:7b sometimes emits a promissory sentence ("Let me calculate that for you.") as
a *complete* generation (`finish_reason=stop`, no tool_calls, non-empty content) instead of
finishing the work — reproduced ~50% on ambiguous prompts before the instruction-routing fix above
(which turned out to be the bigger factor). Fixed in `orchestrator.py`: `_looks_like_stall()`
detects when content ends with an unfinished promise (anchored to end-of-string, so a real answer
that happens to *open* with "Let me calculate..." isn't flagged) and injects one bounded nudge-and-
retry turn before accepting the response as final. 6/6 resolved in isolated testing. Regression
tests: `tests/agents/test_orchestrator.py::TestOrchestratorStallDetection`.

## Memory: on-demand, not auto-injected (2026-07-13)

Every agent used to get a blind FAISS-retrieval dump auto-injected into **every** turn
(`[agent] context_from_memory` in `config.toml`, gated in `executor.py`) regardless of relevance —
traced to CEO's "sum of first 10 Fibonacci numbers" prompt getting buried under a 13KB dump of an
unrelated git-hash-hallucination debugging note (semantically-nearest-but-irrelevant top-5 FAISS
match). Turned OFF (`context_from_memory = false` in `~/.openjarvis/config.toml`) for all agents;
CEO, second-brain, and Researcher were given the `memory_search` tool so they can pull from the
shared knowledge base on demand instead (same underlying FAISS store — nothing is fragmented, it's
just no longer force-fed every turn). Coder already had `memory_search`; Monitor already had
`memory_retrieve`. Assistant (`simple` type) supports no tools at all, so it simply lost the
auto-inject with no replacement — matches its documented scope ("quick asks that do not need
research"), no action taken.

## CEO delegation (real, not a stub)

`agent_spawn`/`agent_send` (tools/agent_tools.py) are an in-memory simulation — spawning
writes to a dict, sending fires an event nobody consumes; neither ever runs real inference.
**`delegate_to_agent`** (tools/delegate_tool.py) is the real mechanism: it resolves a managed
agent by name, sends it a message, runs one genuine tick via a fresh `SystemBuilder`, and
returns the actual reply — the same path as `jarvis agents ask <name> <message>`. Depth-capped
at 2 to prevent delegation cycles. The CEO's `config.instruction` (not `summary_memory` — that
field gets overwritten by each tick's own response) carries a standing roster description; a
per-agent `config["role"]` (set via `new_agent.py`'s role arg) is the stable source for that
description. Re-run `scripts/wire_ceo.py` after adding/changing any agent to refresh it.

## Bench (available to activate)

| Suggested name | Type | What it's good at |
|---|---|---|
| ~~Researcher~~ | `deep_research` | ✅ **activated** — see the Active table above. |
| ~~Coder~~ | `orchestrator` | ✅ **activated** — see note above on why `orchestrator`, not `native_react`. |
| ~~Assistant~~ | `simple` | ✅ **activated** — see the Active table above. |
| ~~Monitor~~ | `monitor_operative` | ✅ **activated** — see note above on the stateful-dedup limitation. |
| Briefer | `morning_digest` | Structured briefing (messages/calendar/world) — needs those sources wired. |

_Advanced (research-grade, heavier — ignore for now): `toolorchestra`, `skillorchestra`, `conductor`, `archon`, `minions`, `react`, `operative`._

## Fixed (2026-07-13): git_log / git_diff / git_status / git_commit

Previously broken — see history for the original bug. Root cause: `get_rust_module()` was called
*outside* the `try` block in three of the four tools, so the `ImportError` (no Rust extension
built on this machine) bypassed the `except` and surfaced as an uncaught exception, which made the
small local model hallucinate a fake result instead of reporting failure. Fixed in `git_tool.py`:
the call now happens inside `try`, and all four tools fall back to real `git` CLI via subprocess
when the Rust extension isn't available. **Verified working end-to-end** — Coder/Monitor no longer
need `shell_exec` for git specifically (still useful for everything else). Rust extension build
still not done (would restore the faster native path) — low priority now that CLI fallback works.

## Add / change an agent

```bash
cd ~/OneDrive/Desktop/OpenJarvis
# add:
uv run python scripts/new_agent.py Researcher deep_research qwen2.5:7b "Digs my notes + web, writes a researched summary."
# list:
uv run jarvis agents list
# talk to one:
uv run jarvis agents ask Researcher "What do my notes say about X?"
# retire one:
uv run jarvis agents delete <name-or-id>
```

> When you add or change an agent, update this table so this file stays the source of truth.

## Tools (MCP servers)

Configured in `~/.openjarvis/config.toml` under `[tools.mcp]`. External tools give agents "hands".

| Tool | Status | Notes |
|---|---|---|
| **Playwright** (browser) | ✅ active | Real browser for the Researcher. Windows: launched via `cmd /c npx @playwright/mcp`. Chromium installed. Launches on every agent run (few sec) — comment out `servers` in config to disable. |
| **Brave Search** | ⏳ needs your key | See steps below. |

### To add Brave Search (you do the key, I wire the rest)
1. Get a **free** API key: <https://brave.com/search/api/> → create account → copy the key.
2. Set it as a user env var (PowerShell): `setx BRAVE_API_KEY "your-key-here"` then restart the shell.
   *(This build's MCP loader has no per-server `env`, so the key must live in the environment.)*
3. Tell me "add Brave" and I'll append its server to `[tools.mcp]` and give the Researcher `brave_web_search`.

_Rule of thumb: keep ≤6 MCP servers active (context bloat)._
