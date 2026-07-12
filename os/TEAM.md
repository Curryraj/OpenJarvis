# The Team

Your agent roster. **Active** = created and runnable now (`~/.openjarvis/agents.db`).
**Bench** = agent types that ship with OpenJarvis; activate any with `new_agent.py`.

_All run on your local model (qwen2.5:7b). No cloud._

## Active

| Agent | Type | Role | Tools | Status |
|---|---|---|---|---|
| **CEO** | `orchestrator` | Delegates & assigns — reads a request, picks the right agent, hands off, combines results. **Real delegation**, wired 2026-07-13 via `delegate_to_agent` (see below). **Known limitation:** reliable when the request explicitly names the tool/agent ("Use delegate_to_agent to ask Coder to..."); on natural phrasing ("What's the sum of...") qwen2.5:7b sometimes just says "let me do that" and stops, without ever calling the tool, or answers directly. This is a model reasoning-capability gap, not a wiring bug — the tool itself works every time it's actually called (verified via direct Python calls and via target agents' own message logs). If autonomous routing quality matters more than the extra RAM/speed cost, CEO specifically is a candidate for a larger model — but that reintroduces the resource cost this session deliberately avoided for Researcher, so left as-is pending your call. | `delegate_to_agent` | idle |
| **second-brain** | `monitor_operative` | Owns the daily knowledge digest; retrieves from your notes + captured facts. | memory | idle |
| **Researcher** | `deep_research` | Digs your notes + the live web, writes a researched summary. | **Playwright browser** (navigate, snapshot, click, find, screenshot) + memory | idle — verified reliable across multiple runs |
| **Coder** | `orchestrator` | Writes, edits, and runs code. Sandboxed to the project dir + `~/.openjarvis/workspace/`. Note: **not** `native_react` — that type's regex-based Thought/Action parsing was unreliable with qwen2.5:7b in testing (silent hallucinated "success" with no tool call on ~1/4 runs); `orchestrator`'s native function-calling mode (same mechanism Researcher uses) was reliable across 3/3 verified runs. | `file_read`, `file_write`, `apply_patch`, `shell_exec`, `code_interpreter`, `repl`, `think`, `memory_search` | idle — verified: write, run, read-modify-write, `git status` via shell_exec, all correct |
| **Assistant** | `simple` | Fast one-shot Q&A, no tools. | — | idle — verified |
| **Monitor** | `monitor_operative` | Watches OpenJarvis's own git log for new commits since its last check, using `memory_store`/`memory_retrieve` for cross-run state. **Known limitation:** reliably reports real commit data now (the hallucination bug below is fixed), but doesn't consistently call `memory_retrieve` first — sometimes re-reports already-seen commits as "new" instead of correctly diffing. Same class of small-model inconsistency as CEO's autonomous routing; not chased further tonight. | `shell_exec`, `memory_store`, `memory_retrieve`, `think` | idle — real-data reporting verified; stateful dedup unreliable |

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

## Known broken: git_log / git_diff / git_status / git_commit

These native tools (`tools/git_tool.py`) require a compiled Rust extension (`openjarvis_rust`,
the `desktop-native` optional group) that isn't built on this machine — no Rust/C++ toolchain
installed (a multi-GB install deliberately avoided earlier when setting up FAISS memory, same
reason). Calling them throws an uncaught `ModuleNotFoundError` inside the tool, which
`ToolExecutor` catches into a generic error message the CLI trace doesn't surface — and the small
local model tends to hallucinate a fake result rather than report the failure (confirmed: got a
fabricated, nonexistent commit hash from Monitor before this was found). Worked around by giving
Coder and Monitor `shell_exec` (real `git` CLI) instead — works fine, `git` itself is installed.
Real fix (not done) is either building the Rust extension, or making `git_tool.py` fail with a
clear `ToolResult(success=False, ...)` instead of an uncaught exception.

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
