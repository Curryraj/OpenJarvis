# Workflow: <name>

> A workflow is a **named recipe** for one repeatable task. Copy this file to
> `workflows/<name>.md` and fill it in. Keep it short — it's a contract, not an essay.

- **Goal:** <one line — what this produces>
- **Agent:** <which team member runs it — see ../TEAM.md>
- **Trigger:** <when it runs — "on ask" / "on schedule (daily 08:00)" / "on new note">
- **Input / context:** <what it reads — e.g. the whole memory store, one project's notes>
- **Prompt:** <the exact instruction handed to the agent>
- **Output:** <where the result goes — chat / a log file / a note in the vault>

**Run it:**
```bash
cd ~/OneDrive/Desktop/OpenJarvis
uv run jarvis agents ask <agent> "<prompt>"
```

**Notes:** <gotchas, what to tune later>
