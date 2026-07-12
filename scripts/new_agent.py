"""Add a team member cleanly.  usage:
    uv run python scripts/new_agent.py <name> <type> [model] ["role description"]
e.g.
    uv run python scripts/new_agent.py Researcher deep_research qwen2.5:7b "Digs my notes + web, writes a researched summary."

Creates (or updates) a persistent agent and pins model=qwen2.5:7b so the tick
actually runs — the framework otherwise pins the uninstalled 'gemma4:31b'.

Role is stored in config["role"], NOT summary_memory — summary_memory gets
overwritten with the agent's last actual response after every tick, so it
can't hold a stable role description (see scripts/wire_ceo.py, which reads
config["role"] to build the CEO's roster listing).
"""
import sys
from openjarvis.agents.manager import AgentManager
from openjarvis.core.config import load_config
from openjarvis.core.paths import get_config_dir

if len(sys.argv) < 3:
    print(__doc__); raise SystemExit(1)

name, atype = sys.argv[1], sys.argv[2]
model = sys.argv[3] if len(sys.argv) > 3 else "qwen2.5:7b"
role = sys.argv[4] if len(sys.argv) > 4 else ""

cfg = load_config()
db = cfg.agent_manager.db_path or str(get_config_dir() / "agents.db")
mgr = AgentManager(db_path=db)

existing = next((a for a in mgr.list_agents(include_archived=True) if a["name"] == name), None)
aid = existing["id"] if existing else mgr.create_agent(name=name, agent_type=atype)["id"]
ag = mgr.get_agent(aid)
c = dict(ag.get("config") or {}); c["model"] = model
if role:
    c["role"] = role
mgr.update_agent(aid, config=c)
# Also seed summary_memory on first creation only, so `agent info`/early
# ticks have something reasonable before the agent's first real response.
if role and not (existing and (existing.get("summary_memory") or "").strip()):
    mgr.update_summary_memory(aid, role)
print(f"OK: agent '{name}'  type={atype}  model={model}  id={aid}")
