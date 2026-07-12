# Workflow: daily-digest

- **Goal:** A short briefing of what's in the knowledge base — themes, open threads, one connection.
- **Agent:** second-brain (`monitor_operative`)
- **Trigger:** on ask (reactive). *Also wired to a daily 08:00 schedule — optional, can be turned off.*
- **Input / context:** the whole memory store (wiki + raw sources + handoffs + captured facts), auto-injected.
- **Prompt:** "Daily knowledge digest. Using ONLY the retrieved context, write a briefing UNDER 150 words: (1) 2–3 key themes, (2) open threads/next-actions, (3) one non-obvious connection. Cite note titles. No preamble."
- **Output:** chat, and `~/.openjarvis/logs/digest.log` when run by the scheduler.

**Run it:**
```bash
cd ~/OneDrive/Desktop/OpenJarvis
uv run jarvis agents ask second-brain "Daily knowledge digest ..."
```

**Notes:** retrieval is prompt-driven (semantically-nearest notes, not strictly "recent") — a future
refinement. Refresh the store first with `scripts/refresh_memory.py` if you've added notes.
