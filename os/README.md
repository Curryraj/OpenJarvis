# Agentic OS — Control Room

This folder is the **human-readable map** of your local agent OS. The agents actually
live in `~/.openjarvis/agents.db`; your knowledge lives in the Obsidian vault. This is
where *you* see and steer it.

```
os/
├── README.md        ← you are here — how the whole thing works
├── TEAM.md          ← the roster: CEO + agents (active) + bench (available)
├── workflows/       ← reusable task recipes (one file each)
│   ├── _template.md
│   └── daily-digest.md
└── projects/        ← per-project goals + which workflows they use
    └── _template.md
```

## The model (how the team works)

```
YOU → CEO (delegates) → the right specialist agent → shared Memory + Tools → result
```

- **CEO** decides *who* does the work. You don't have to know which agent — ask the CEO.
- **Specialists** each do one thing well (research, code, digest, monitor).
- **Everyone shares** the same memory (your notes + captured facts) and tools.

## How to run a task

```bash
cd ~/OneDrive/Desktop/OpenJarvis

# Let the CEO route it (delegation):
uv run jarvis agents ask CEO "Research what my notes say about the LLM wiki pattern and summarize."

# Or go straight to a specialist:
uv run jarvis agents ask second-brain "Give me today's digest."
```

## How to grow it (the groundwork)

1. **Add an agent** → `scripts/new_agent.py` (see TEAM.md), then add a row to TEAM.md.
2. **Add a workflow** → copy `workflows/_template.md` to `workflows/<name>.md` and fill it in.
   A *workflow* = a named recipe: which agent, what trigger, what prompt, what output.
3. **Start a project** → copy `projects/_template.md` to `projects/<project>.md`,
   list its goal and which workflows it uses.

## Where the real parts live

| Piece | Location |
|---|---|
| Agents | `~/.openjarvis/agents.db` (via `jarvis agents …`) |
| Memory (retrieval) | `~/.openjarvis/faiss_index.faiss` — rebuild: `scripts/refresh_memory.py` |
| Captured facts | `~/.openjarvis/memory_facts.jsonl` (`jarvis memory list`) |
| Knowledge source | Obsidian vault `~/Downloads/working-55` (wiki + raw + handoffs) |
| Automation | Windows Task Scheduler: `OpenJarvis-Refresh`, `OpenJarvis-Digest` |
| Logs | `~/.openjarvis/logs/` |
