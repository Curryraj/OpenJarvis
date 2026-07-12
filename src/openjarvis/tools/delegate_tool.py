"""Real cross-agent delegation for managed agents.

``agent_spawn``/``agent_send`` in ``agent_tools.py`` are an in-memory
simulation layer — spawning writes to a dict and sending fires an event
no one consumes; neither actually runs inference. This tool instead
drives a *managed* agent (the ``agents.db`` roster, e.g. "Researcher",
"second-brain") through one real tick — the same path as
``jarvis agents ask <name> <message>`` — and returns its actual reply.
"""

from __future__ import annotations

import threading
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

# Delegation can chain (CEO -> Coder -> Researcher), but must not cycle
# back through an orchestrator indefinitely. Depth is process-local and
# per-thread since each delegated tick may run tool calls on its own
# ThreadPoolExecutor worker.
_MAX_DELEGATION_DEPTH = 2
_depth = threading.local()


@ToolRegistry.register("delegate_to_agent")
class DelegateToAgentTool(BaseTool):
    """Hand a task to another managed agent and block for its reply."""

    tool_id = "delegate_to_agent"
    is_local = True

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="delegate_to_agent",
            description=(
                "Hand a task to another managed agent by name (e.g. "
                "'Researcher', 'second-brain', 'Coder') and get its reply "
                "back. Use this to route work to whichever specialist is "
                "best suited, instead of trying to do everything yourself."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "Name of the target managed agent.",
                    },
                    "task": {
                        "type": "string",
                        "description": "The task or question to hand off.",
                    },
                },
                "required": ["agent_name", "task"],
            },
            category="agents",
            timeout_seconds=300.0,
        )

    def execute(self, **params: Any) -> ToolResult:
        agent_name = params.get("agent_name", "")
        task = params.get("task", "")
        if not agent_name:
            return ToolResult(
                tool_name="delegate_to_agent",
                content="No agent_name provided.",
                success=False,
            )
        if not task:
            return ToolResult(
                tool_name="delegate_to_agent",
                content="No task provided.",
                success=False,
            )

        depth = getattr(_depth, "value", 0)
        if depth >= _MAX_DELEGATION_DEPTH:
            return ToolResult(
                tool_name="delegate_to_agent",
                content=(
                    f"Delegation depth limit ({_MAX_DELEGATION_DEPTH}) "
                    "reached — refusing to delegate further to avoid a cycle."
                ),
                success=False,
            )

        system = None
        try:
            from openjarvis.agents.manager import AgentManager
            from openjarvis.core.config import load_config
            from openjarvis.core.paths import get_config_dir
            from openjarvis.system import SystemBuilder

            config = load_config()
            db_path = config.agent_manager.db_path or str(
                get_config_dir() / "agents.db"
            )
            manager = AgentManager(db_path=db_path)

            target = manager.get_agent(agent_name)
            if target is None:
                target = next(
                    (
                        a
                        for a in manager.list_agents(include_archived=True)
                        if a["name"] == agent_name
                    ),
                    None,
                )
            if target is None:
                return ToolResult(
                    tool_name="delegate_to_agent",
                    content=f"Agent not found: {agent_name}",
                    success=False,
                )

            agent_id = target["id"]
            manager.send_message(agent_id, task, mode="immediate")

            system = SystemBuilder().build()
            executor = system.agent_executor
            if executor is None:
                return ToolResult(
                    tool_name="delegate_to_agent",
                    content="Agent executor not available.",
                    success=False,
                )
            executor._confirm_callback = lambda _prompt: True

            _depth.value = depth + 1
            try:
                executor.execute_tick(agent_id)
            finally:
                _depth.value = depth

            msgs = manager.list_messages(agent_id)
            responses = [m for m in msgs if m["direction"] == "agent_to_user"]
            if not responses:
                return ToolResult(
                    tool_name="delegate_to_agent",
                    content=f"No response from '{agent_name}'.",
                    success=False,
                )

            return ToolResult(
                tool_name="delegate_to_agent",
                content=responses[0]["content"],
                success=True,
                metadata={"agent_name": agent_name, "agent_id": agent_id},
            )
        except Exception as exc:
            return ToolResult(
                tool_name="delegate_to_agent",
                content=f"Delegation error: {exc}",
                success=False,
            )
        finally:
            if system is not None:
                try:
                    system.close()
                except Exception:
                    pass


__all__ = ["DelegateToAgentTool"]
