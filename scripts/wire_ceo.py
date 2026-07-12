"""Wire the CEO agent for real delegation.  usage:
    uv run python scripts/wire_ceo.py

Sets CEO's config.tools to include delegate_to_agent (the real cross-agent
dispatch tool — see tools/delegate_tool.py) and sets a standing instruction
naming the current roster, since config.instruction is what actually reaches
the model's input every tick (summary_memory only surfaces as a truncated
"previous tick" note, not a persistent role description).

Re-run any time the roster changes to refresh the instruction text.
"""
from openjarvis.agents.manager import AgentManager
from openjarvis.core.config import load_config
from openjarvis.core.paths import get_config_dir

cfg = load_config()
db = cfg.agent_manager.db_path or str(get_config_dir() / "agents.db")
mgr = AgentManager(db_path=db)

ceo = next((a for a in mgr.list_agents(include_archived=True) if a["name"] == "CEO"), None)
if ceo is None:
    raise SystemExit("CEO agent not found — create it first.")

roster = [
    a for a in mgr.list_agents(include_archived=True)
    if a["name"] != "CEO" and a.get("status") != "archived"
]
roster_lines = "\n".join(
    f"- {a['name']} ({a['agent_type']}): "
    f"{(a.get('summary_memory') or '').strip().split(chr(10))[0][:120] or 'no description yet'}"
    for a in roster
)

instruction = (
    "You are the CEO. You do not do specialist work yourself — you delegate.\n"
    "Your team:\n"
    f"{roster_lines}\n\n"
    "For any request that matches a specialist's job, call delegate_to_agent "
    "with that agent's exact name and a clear task description, then relay "
    "or combine its reply. Only answer directly for things no specialist "
    "covers (e.g. simple clarifying questions)."
)

c = dict(ceo.get("config") or {})
c["tools"] = ["delegate_to_agent"]
c["instruction"] = instruction
mgr.update_agent(ceo["id"], config=c)
print("OK: CEO wired for delegation.")
print(instruction)
