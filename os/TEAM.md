# The Team

Your agent roster. **Active** = created and runnable now (`~/.openjarvis/agents.db`).
**Bench** = agent types that ship with OpenJarvis; activate any with `new_agent.py`.

_All run on your local model (qwen2.5:7b). No cloud._

## Active

| Agent | Type | Role | Tools | Status |
|---|---|---|---|---|
| **CEO** | `orchestrator` | Delegates & assigns — reads a request, picks the right agent, hands off, combines results. **Real delegation**, wired 2026-07-13 via `delegate_to_agent` (see below). **Fixed 2026-07-13:** root cause of unreliable/empty responses was `instruction` being embedded as text in the USER turn instead of the SYSTEM message — with tools attached, qwen2.5:7b/Ollama returned genuinely empty messages (no content, no tool_calls) 100% of the time with that layout, 0% with the identical text as a proper system message. Fixed in `executor.py` — see "Instruction routing fix" below. Verified 3/3 on previously-100%-failing prompts, including real Coder delegation with actual code execution. | `delegate_to_agent`, `memory_search` | idle |
| **second-brain** | `monitor_operative` | Owns the daily knowledge digest; retrieves from your notes + captured facts. **Changed 2026-07-13:** no longer relies on blind auto-injected memory context (see "Memory: on-demand, not auto-injected" below) — now calls `memory_search` itself. | `memory_search` | idle |
| **Researcher** | `deep_research` | Digs your notes + the live web, writes a researched summary. **Changed 2026-07-20:** system-prompt override added — see "Researcher system-prompt override" below. | `web_search` (primary) + **Playwright browser** (navigate, snapshot, click, find, screenshot) + `memory_search`, `think` | idle — verified reliable across multiple runs |
| **Coder** | `orchestrator` | Writes, edits, and runs code. Sandboxed to the project dir + `~/.openjarvis/workspace/`. Note: **not** `native_react` — that type's regex-based Thought/Action parsing was unreliable with qwen2.5:7b in testing (silent hallucinated "success" with no tool call on ~1/4 runs); `orchestrator`'s native function-calling mode (same mechanism Researcher uses) was reliable across 3/3 verified runs. | `file_read`, `file_write`, `apply_patch`, `shell_exec`, `code_interpreter`, `repl`, `think`, `memory_search` | idle — verified: write, run, read-modify-write, `git status` via shell_exec, all correct |
| **Assistant** | `simple` | Fast one-shot Q&A, no tools. | — | idle — verified |
| **Monitor** | `monitor_operative` | Watches OpenJarvis's own git log for new commits since its last check. **Dedup fixed 2026-07-13** — see "Monitor dedup fix" below. Checkpoint is now a plain file (`~/.openjarvis/monitor_last_commit.txt`) + a real `git log <hash>..HEAD` range diff, not the shared FAISS store. | `shell_exec`, `think` | idle — dedup mechanism verified correct across 6 trials |

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

## Monitor dedup fix (2026-07-13)

Root cause of "sometimes re-reports already-seen commits as new" was structural, not a small-model
quirk: Monitor's checkpoint was written via `memory_store`/read via `memory_retrieve` — i.e. the
shared semantic FAISS store. Two independent problems there: (1) the daily `OpenJarvis-Refresh`
scheduled task (07:45) does `FAISSMemory().clear()` then rebuilds from curated markdown + captured
auto-facts ONLY — Monitor's raw checkpoint documents are neither, so **every single day's refresh
silently deleted Monitor's checkpoint**. (2) Even without the wipe, `memory_retrieve("Monitor last
checked commit")` is a semantic-similarity search across the whole shared store (174+ docs) — tested
directly, it never once surfaced Monitor's own stored checkpoint text, not even querying the literal
commit hash; it returned unrelated Obsidian notes instead. A vector store is the wrong data structure
for exact per-agent state.

**Fix:** Monitor's instruction now uses `shell_exec` (already granted) for a 4-step file-based
checkpoint instead: (1) read `~/.openjarvis/monitor_last_commit.txt` (or detect first-run via a
`NONE` sentinel), (2) `git log <hash>..HEAD --oneline` for a real, exact git range diff instead of
asking the model to eyeball-compare two lists, (3) summarize only if non-empty, (4) always write the
current `git log -1 --format=%H` back to the checkpoint file. Dropped `memory_store`/`memory_retrieve`
from its tools — no longer needed, and a smaller tool list is one less thing to mis-route on.
`memory_search`/`memory_retrieve` were never inherently unsuited to knowledge lookup — the bug was
using them for exact single-value state, not knowledge retrieval.

**Windows gotcha found+fixed along the way:** cmd.exe's `type` builtin rejects forward-slash paths
("The syntax of the command is incorrect") but accepts backslash paths fine — verified directly
before writing the final instruction, not guessed. Also confirmed `%USERPROFILE%` is unusable here:
`shell_exec` runs with a minimal sanitized env (`PATH,HOME,USER,LANG,TERM` only) that doesn't include
it — used the literal absolute path instead.

**Verified:** the file-checkpoint mechanism itself is 100% correct in isolation (scripted, non-agent
test: first-run detection, write, read-back, and range-diff against both a fresh and a stale hash all
gave exactly the right answer). Driven through the real agent across 6 tick-pairs (first-run tick +
immediate follow-up tick): 5/6 correctly recognized nothing was new; one tick skipped the checkpoint
read and re-reported old commits (same class of small-model step-skipping seen elsewhere in this
project, e.g. CEO's autonomous routing) — the mechanism didn't fail, the model occasionally doesn't
follow it. Net: a deterministic, always-reproduced structural bug is now fixed; what's left is the
same honest small-model reliability variance already documented for CEO, not something chased
further tonight.

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

## Researcher system-prompt override (2026-07-20)

Researcher kept answering broad questions with generic soft-skill filler instead of the concrete
figures its own searches had already returned. First guess was "small model limits". Wrong — the
real cause was structural, found by reading `agents/deep_research.py`:

1. **The shipped `deep_research` system prompt describes a different agent.** It is written for
   upstream's personal-knowledge-base product and instructs the model to use `knowledge_search`,
   `knowledge_sql`, and `scan_chunks` — **none of which our Researcher has** — while never
   mentioning `web_search`, the tool it actually depends on. The model was being told to reach for
   tools that don't exist in its toolset.
2. **`config["instruction"]` / `config["system_prompt"]` do NOT work on this agent type.**
   `DeepResearchAgent.run()` unconditionally overwrites the `system_prompt` kwarg with
   `load_system_prompt_override("deep_research") or _build_system_prompt()`. So the
   instruction-routing fix (2026-07-13) that made CEO work does **not** reach `deep_research`
   agents — setting `instruction` on Researcher is silently discarded. Same silent-drop class as
   the orchestrator bug, different code path.

**Fix = the supported override file**, not a code patch and not an agent config edit:
`~/.openjarvis/agents/deep_research/system_prompt.md`, read by `prompt_loader.py`. It lives
**outside the git repo**, so unlike the vendored `faiss_backend.py` patch it survives
`git pull` / `self-update`.

Generated by **`scripts/write_researcher_prompt.py`** (re-runnable). It is a generator rather than
a static file because the override is a FULL replacement and the built-in prompt injects the
current date — re-run it to refresh the date, or wire it into the daily `OpenJarvis-Refresh` task.

The override (a) names Researcher's real tools and explicitly says the `knowledge_*` tools don't
exist, and (b) adds output rules: search before answering, narrow beats broad, concrete figures
over adjectives, never pad with generic filler, state plainly what you could NOT find, never
invent a citation, separate vault claims from web claims, flag conflicting sources.

**Knob left alone:** the override keeps the built-in's leading `/no_think` directive, to avoid
changing two variables at once. Worth A/B testing later — a multi-step research agent may do
better with thinking enabled.

### Few-shot exemplars (2026-07-20)

The prose rules above only half-worked: the *positive* ones landed (search unprompted, give
concrete figures) while the *restraint* ones did not (still fired one broad search, still padded
with soft-skill filler, never once said "I couldn't find X"). Typical for a 7b — showing beats
telling. So two exemplars were added at `~/.openjarvis/agents/deep_research/few_shot.json`,
loaded by the same `prompt_loader.py`.

**How they're injected:** `deep_research.py` inserts each pair as plain USER/ASSISTANT messages
immediately before the real user turn. There are **no tool-call traces** in that format, so
few-shot here can only teach the *shape of the answer* — it cannot demonstrate "make three narrow
searches instead of one". The single-broad-search habit needs a different lever.

**The two exemplars are deliberately paired** on the same topic (UK public EV chargers):
1. an answerable question → concrete figures first, named source, flags a real definitional
   change that breaks comparisons, sources list, zero filler;
2. a **deliberately unanswerable** one (a 2035 projection) → states plainly that no published
   figure was found, names what was searched, gives the verified baseline instead, and explicitly
   refuses to extrapolate a number that would look sourced but isn't.

The pairing is the point: one question that should be answered and one that should not, so the
model learns to *discriminate* rather than to always hedge or always assert.

⚠️ **Staleness liability.** Exemplar content is injected on every Researcher turn, so any figure
in it is a fact the model sees constantly and may parrot. Both exemplars therefore use **real,
verified** numbers (119,080 UK public EV chargers at 2026-04-01, 27,372 rapid, 121,171 by end
June — DfT via Zapmap) rather than plausible-looking invented ones. **These will go stale.** When
they do, either refresh the figures or pick a topic that doesn't drift. Never put a made-up number
in an exemplar.

The EV topic was chosen because it is far from Jaiydaan's actual research subjects — if the model
ever parrots an exemplar figure into an unrelated answer, it is obvious rather than camouflaged.

## Bench (available to activate)

| Suggested name | Type | What it's good at |
|---|---|---|
| ~~Researcher~~ | `deep_research` | ✅ **activated** — see the Active table above. |
| ~~Coder~~ | `orchestrator` | ✅ **activated** — see note above on why `orchestrator`, not `native_react`. |
| ~~Assistant~~ | `simple` | ✅ **activated** — see the Active table above. |
| ~~Monitor~~ | `monitor_operative` | ✅ **activated** — see "Monitor dedup fix" above. |
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
