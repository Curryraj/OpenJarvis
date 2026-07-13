"""Tests for tool wiring in AgentExecutor."""

from __future__ import annotations

from openjarvis.agents.executor import AgentExecutor
from openjarvis.agents.manager import AgentManager
from openjarvis.core.events import EventBus
from tests.agents.fake_engine import FakeEngine
from tests.agents.scenario_harness import FakeSystem


def _register_agent():
    """Re-register MonitorOperativeAgent (cleared by autouse fixture)."""
    from openjarvis.agents.monitor_operative import MonitorOperativeAgent
    from openjarvis.core.registry import AgentRegistry

    if not AgentRegistry.contains("monitor_operative"):
        AgentRegistry.register("monitor_operative")(MonitorOperativeAgent)


def test_executor_runs_with_tools_from_config(tmp_path):
    """Executor should resolve tool names from config and complete tick."""
    _register_agent()

    engine = FakeEngine([{"content": "test response"}])
    system = FakeSystem(engine=engine)

    mgr = AgentManager(db_path=str(tmp_path / "test.db"))
    agent = mgr.create_agent(
        "test",
        agent_type="monitor_operative",
        config={
            "system_prompt": "You are a test agent.",
            "tools": ["think"],
            "instruction": "test",
        },
    )
    mgr.send_message(agent["id"], "hello", mode="immediate")

    executor = AgentExecutor(manager=mgr, event_bus=EventBus())
    executor.set_system(system)

    executor.execute_tick(agent["id"])
    result_agent = mgr.get_agent(agent["id"])
    assert result_agent["status"] == "idle"
    assert result_agent["total_runs"] == 1
    mgr.close()


def test_executor_handles_missing_tools(tmp_path):
    """Executor should not crash if tool names don't exist in registry."""
    _register_agent()

    engine = FakeEngine([{"content": "test response"}])
    system = FakeSystem(engine=engine)

    mgr = AgentManager(db_path=str(tmp_path / "test.db"))
    agent = mgr.create_agent(
        "test",
        agent_type="monitor_operative",
        config={
            "system_prompt": "You are a test agent.",
            "tools": ["nonexistent_tool_xyz"],
            "instruction": "test",
        },
    )
    mgr.send_message(agent["id"], "hello", mode="immediate")

    executor = AgentExecutor(manager=mgr, event_bus=EventBus())
    executor.set_system(system)

    executor.execute_tick(agent["id"])
    result_agent = mgr.get_agent(agent["id"])
    assert result_agent["status"] == "idle"
    assert result_agent["total_runs"] == 1
    mgr.close()


def test_executor_handles_string_tools(tmp_path):
    """Executor should handle comma-separated tool string as well as list."""
    _register_agent()

    engine = FakeEngine([{"content": "test response"}])
    system = FakeSystem(engine=engine)

    mgr = AgentManager(db_path=str(tmp_path / "test.db"))
    agent = mgr.create_agent(
        "test",
        agent_type="monitor_operative",
        config={
            "system_prompt": "You are a test agent.",
            "tools": "think,calculator",
            "instruction": "test",
        },
    )
    mgr.send_message(agent["id"], "hello", mode="immediate")

    executor = AgentExecutor(manager=mgr, event_bus=EventBus())
    executor.set_system(system)

    executor.execute_tick(agent["id"])
    result_agent = mgr.get_agent(agent["id"])
    assert result_agent["status"] == "idle"
    mgr.close()


def test_executor_routes_instruction_through_system_prompt(tmp_path):
    """config["instruction"] must land in the SYSTEM message, not be embedded
    as text inside the USER turn.

    Reproduced live: with tools attached, qwen2.5:7b via Ollama returned a
    genuinely empty message (no content, no tool_calls) 100% of the time
    when instructional text ("Standing instruction: You are the CEO...")
    was embedded in the user turn, vs. 0% when the identical text was a
    proper system message. This locks in the fix at the executor level.
    """
    _register_agent()

    engine = FakeEngine([{"content": "test response"}])
    system = FakeSystem(engine=engine)

    mgr = AgentManager(db_path=str(tmp_path / "test.db"))
    agent = mgr.create_agent(
        "test",
        agent_type="monitor_operative",
        config={
            "tools": ["think"],
            "instruction": "You are the CEO. You delegate to specialists.",
        },
    )
    mgr.send_message(agent["id"], "What is 2+2?", mode="immediate")

    executor = AgentExecutor(manager=mgr, event_bus=EventBus())
    executor.set_system(system)
    executor.execute_tick(agent["id"])

    messages = engine.last_messages
    system_msgs = [m for m in messages if m.role.value == "system"]
    user_msgs = [m for m in messages if m.role.value == "user"]

    assert any(
        "You are the CEO" in m.content for m in system_msgs
    ), "instruction must be in a SYSTEM message"
    assert not any(
        "Standing instruction" in m.content for m in user_msgs
    ), "instruction must not be embedded as text in the USER turn"
    mgr.close()


def test_executor_combines_system_prompt_and_instruction(tmp_path):
    """When both system_prompt and instruction are configured, both should
    reach the model via the system message (instruction appended)."""
    _register_agent()

    engine = FakeEngine([{"content": "test response"}])
    system = FakeSystem(engine=engine)

    mgr = AgentManager(db_path=str(tmp_path / "test.db"))
    agent = mgr.create_agent(
        "test",
        agent_type="monitor_operative",
        config={
            "system_prompt": "You are OpenJarvis.",
            "tools": ["think"],
            "instruction": "You are the CEO. You delegate to specialists.",
        },
    )
    mgr.send_message(agent["id"], "What is 2+2?", mode="immediate")

    executor = AgentExecutor(manager=mgr, event_bus=EventBus())
    executor.set_system(system)
    executor.execute_tick(agent["id"])

    system_msgs = [m for m in engine.last_messages if m.role.value == "system"]
    combined = "\n".join(m.content for m in system_msgs)
    assert "You are OpenJarvis." in combined
    assert "You are the CEO" in combined
    mgr.close()
