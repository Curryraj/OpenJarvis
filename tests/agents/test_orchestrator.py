"""Tests for the OrchestratorAgent."""

from __future__ import annotations

from unittest.mock import MagicMock

from openjarvis.agents._stubs import AgentContext
from openjarvis.agents.orchestrator import OrchestratorAgent, _looks_like_stall
from openjarvis.core.events import EventBus, EventType
from openjarvis.core.types import Conversation, Message, Role, ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _CalculatorStub(BaseTool):
    tool_id = "calculator"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="calculator",
            description="Math calculator.",
            parameters={
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        )

    def execute(self, **params) -> ToolResult:
        expr = params.get("expression", "0")
        try:
            val = eval(expr)  # noqa: S307 — safe in tests
        except Exception as e:
            return ToolResult(tool_name="calculator", content=str(e), success=False)
        return ToolResult(tool_name="calculator", content=str(val), success=True)


class _ThinkStub(BaseTool):
    tool_id = "think"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="think",
            description="Thinking tool.",
            parameters={
                "type": "object",
                "properties": {"thought": {"type": "string"}},
            },
        )

    def execute(self, **params) -> ToolResult:
        return ToolResult(
            tool_name="think",
            content=params.get("thought", ""),
            success=True,
        )


def _make_engine_no_tools(content: str = "Final answer.") -> MagicMock:
    """Engine that never returns tool calls."""
    engine = MagicMock()
    engine.engine_id = "mock"
    engine.generate.return_value = {
        "content": content,
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        "model": "test-model",
        "finish_reason": "stop",
    }
    return engine


def _make_engine_with_tool_call(
    tool_name: str = "calculator",
    arguments: str = '{"expression":"2+2"}',
    tool_call_id: str = "call_1",
    final_content: str = "The answer is 4.",
) -> MagicMock:
    """Engine that returns one tool call then a final answer."""
    engine = MagicMock()
    engine.engine_id = "mock"
    engine.generate.side_effect = [
        # First call: tool call
        {
            "content": "",
            "tool_calls": [
                {"id": tool_call_id, "name": tool_name, "arguments": arguments}
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            "model": "test-model",
            "finish_reason": "tool_calls",
        },
        # Second call: final answer
        {
            "content": final_content,
            "usage": {"prompt_tokens": 15, "completion_tokens": 5, "total_tokens": 20},
            "model": "test-model",
            "finish_reason": "stop",
        },
    ]
    return engine


def _make_engine_multi_tool() -> MagicMock:
    """Engine that calls multiple tools in one turn."""
    engine = MagicMock()
    engine.engine_id = "mock"
    engine.generate.side_effect = [
        {
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "name": "calculator",
                    "arguments": '{"expression":"2+2"}',
                },
                {
                    "id": "call_2",
                    "name": "think",
                    "arguments": '{"thought":"thinking..."}',
                },
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            "model": "test-model",
            "finish_reason": "tool_calls",
        },
        {
            "content": "Done.",
            "usage": {"prompt_tokens": 20, "completion_tokens": 3, "total_tokens": 23},
            "model": "test-model",
            "finish_reason": "stop",
        },
    ]
    return engine


def _stall_response(content: str = "Let me calculate that for you.") -> dict:
    """A complete (finish_reason=stop) generation with no tool_calls that
    only announces intent -- reproduces the qwen2.5:7b stall behavior."""
    return {
        "content": content,
        "tool_calls": None,
        "usage": {"prompt_tokens": 5, "completion_tokens": 8, "total_tokens": 13},
        "model": "test-model",
        "finish_reason": "stop",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOrchestratorAgent:
    def test_agent_id(self):
        engine = _make_engine_no_tools()
        agent = OrchestratorAgent(engine, "test-model")
        assert agent.agent_id == "orchestrator"

    def test_no_tools_single_turn(self):
        engine = _make_engine_no_tools("Hello!")
        agent = OrchestratorAgent(engine, "test-model")
        result = agent.run("Hello")
        assert result.content == "Hello!"
        assert result.turns == 1
        assert result.tool_results == []

    def test_single_tool_call(self):
        engine = _make_engine_with_tool_call()
        agent = OrchestratorAgent(
            engine,
            "test-model",
            tools=[_CalculatorStub()],
        )
        result = agent.run("What is 2+2?")
        assert result.content == "The answer is 4."
        assert result.turns == 2
        assert len(result.tool_results) == 1
        assert result.tool_results[0].tool_name == "calculator"
        assert result.tool_results[0].content == "4"

    def test_multiple_tool_calls_same_turn(self):
        engine = _make_engine_multi_tool()
        agent = OrchestratorAgent(
            engine,
            "test-model",
            tools=[_CalculatorStub(), _ThinkStub()],
        )
        result = agent.run("Think and calculate.")
        assert result.content == "Done."
        assert result.turns == 2
        assert len(result.tool_results) == 2

    def test_with_context_conversation(self):
        engine = _make_engine_no_tools()
        agent = OrchestratorAgent(engine, "test-model")
        conv = Conversation()
        conv.add(Message(role=Role.SYSTEM, content="Be helpful."))
        ctx = AgentContext(conversation=conv)
        agent.run("Hi", context=ctx)
        call_args = engine.generate.call_args
        messages = call_args[0][0]
        assert len(messages) == 2
        assert messages[0].role == Role.SYSTEM

    def test_tools_passed_to_engine(self):
        engine = _make_engine_no_tools()
        agent = OrchestratorAgent(
            engine,
            "test-model",
            tools=[_CalculatorStub()],
        )
        agent.run("Hello")
        call_kwargs = engine.generate.call_args[1]
        assert "tools" in call_kwargs
        assert len(call_kwargs["tools"]) == 1

    def test_no_tools_no_tools_kwarg(self):
        engine = _make_engine_no_tools()
        agent = OrchestratorAgent(engine, "test-model")
        agent.run("Hello")
        call_kwargs = engine.generate.call_args[1]
        assert "tools" not in call_kwargs

    def test_max_turns_exceeded(self):
        """When the engine keeps returning tool calls, stop after max_turns."""
        engine = MagicMock()
        engine.engine_id = "mock"
        engine.generate.return_value = {
            "content": "",
            "tool_calls": [
                {"id": "c1", "name": "calculator", "arguments": '{"expression":"1+1"}'}
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            "model": "test-model",
            "finish_reason": "tool_calls",
        }
        agent = OrchestratorAgent(
            engine,
            "test-model",
            tools=[_CalculatorStub()],
            max_turns=3,
        )
        result = agent.run("Loop forever")
        assert result.turns == 3
        assert result.metadata.get("max_turns_exceeded") is True

    def test_unknown_tool_in_response(self):
        engine = _make_engine_with_tool_call(
            tool_name="unknown_tool",
            arguments="{}",
            final_content="Handled.",
        )
        agent = OrchestratorAgent(
            engine,
            "test-model",
            tools=[_CalculatorStub()],
        )
        result = agent.run("Use unknown tool")
        assert result.content == "Handled."
        assert len(result.tool_results) == 1
        assert result.tool_results[0].success is False

    def test_temperature_passthrough(self):
        engine = _make_engine_no_tools()
        agent = OrchestratorAgent(engine, "test-model", temperature=0.1)
        agent.run("Hello")
        call_kwargs = engine.generate.call_args[1]
        assert call_kwargs["temperature"] == 0.1

    def test_max_tokens_passthrough(self):
        engine = _make_engine_no_tools()
        agent = OrchestratorAgent(engine, "test-model", max_tokens=256)
        agent.run("Hello")
        call_kwargs = engine.generate.call_args[1]
        assert call_kwargs["max_tokens"] == 256

    def test_event_bus_agent_events(self):
        bus = EventBus(record_history=True)
        engine = _make_engine_no_tools()
        agent = OrchestratorAgent(engine, "test-model", bus=bus)
        agent.run("Hello")
        event_types = [e.event_type for e in bus.history]
        assert EventType.AGENT_TURN_START in event_types
        assert EventType.AGENT_TURN_END in event_types

    def test_event_bus_inference_events(self):
        """INFERENCE_START/END are now published by InstrumentedEngine,
        not by agents directly.  Agent tests verify agent-level events."""
        bus = EventBus(record_history=True)
        engine = _make_engine_no_tools()
        agent = OrchestratorAgent(engine, "test-model", bus=bus)
        agent.run("Hello")
        event_types = [e.event_type for e in bus.history]
        assert EventType.AGENT_TURN_START in event_types
        assert EventType.AGENT_TURN_END in event_types

    def test_event_bus_tool_events(self):
        bus = EventBus(record_history=True)
        engine = _make_engine_with_tool_call()
        agent = OrchestratorAgent(
            engine,
            "test-model",
            tools=[_CalculatorStub()],
            bus=bus,
        )
        agent.run("Calc 2+2")
        event_types = [e.event_type for e in bus.history]
        assert EventType.TOOL_CALL_START in event_types
        assert EventType.TOOL_CALL_END in event_types

    def test_messages_accumulate(self):
        """After tool call, messages include assistant + tool messages."""
        engine = _make_engine_with_tool_call()
        agent = OrchestratorAgent(
            engine,
            "test-model",
            tools=[_CalculatorStub()],
        )
        agent.run("What is 2+2?")
        # Second call should include accumulated messages
        second_call = engine.generate.call_args_list[1]
        messages = second_call[0][0]
        roles = [m.role for m in messages]
        assert Role.ASSISTANT in roles
        assert Role.TOOL in roles

    def test_tool_message_has_tool_call_id(self):
        engine = _make_engine_with_tool_call(tool_call_id="abc123")
        agent = OrchestratorAgent(
            engine,
            "test-model",
            tools=[_CalculatorStub()],
        )
        agent.run("What is 2+2?")
        second_call = engine.generate.call_args_list[1]
        messages = second_call[0][0]
        tool_msgs = [m for m in messages if m.role == Role.TOOL]
        assert len(tool_msgs) == 1
        assert tool_msgs[0].tool_call_id == "abc123"

    def test_no_bus_works(self):
        engine = _make_engine_with_tool_call()
        agent = OrchestratorAgent(
            engine,
            "test-model",
            tools=[_CalculatorStub()],
        )
        result = agent.run("What is 2+2?")
        assert result.content == "The answer is 4."

    def test_empty_tools_list(self):
        engine = _make_engine_no_tools()
        agent = OrchestratorAgent(engine, "test-model", tools=[])
        result = agent.run("Hello")
        assert result.content == "Final answer."

    def test_three_turn_conversation(self):
        """Engine calls a tool twice before answering."""
        engine = MagicMock()
        engine.engine_id = "mock"
        engine.generate.side_effect = [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "c1",
                        "name": "calculator",
                        "arguments": '{"expression":"2+2"}',
                    }
                ],
                "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 3,
                    "total_tokens": 8,
                },
                "model": "test-model",
                "finish_reason": "tool_calls",
            },
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "c2",
                        "name": "calculator",
                        "arguments": '{"expression":"4*3"}',
                    }
                ],
                "usage": {
                    "prompt_tokens": 15,
                    "completion_tokens": 3,
                    "total_tokens": 18,
                },
                "model": "test-model",
                "finish_reason": "tool_calls",
            },
            {
                "content": "2+2=4, 4*3=12",
                "usage": {
                    "prompt_tokens": 25,
                    "completion_tokens": 5,
                    "total_tokens": 30,
                },
                "model": "test-model",
                "finish_reason": "stop",
            },
        ]
        agent = OrchestratorAgent(
            engine,
            "test-model",
            tools=[_CalculatorStub()],
        )
        result = agent.run("Calculate")
        assert result.turns == 3
        assert len(result.tool_results) == 2
        assert result.tool_results[0].content == "4"
        assert result.tool_results[1].content == "12"

    def test_tool_result_latency_tracked(self):
        engine = _make_engine_with_tool_call()
        agent = OrchestratorAgent(
            engine,
            "test-model",
            tools=[_CalculatorStub()],
        )
        result = agent.run("What is 2+2?")
        assert result.tool_results[0].latency_seconds >= 0

    def test_max_turns_1(self):
        """With max_turns=1 and a tool call, should stop after 1 turn."""
        engine = MagicMock()
        engine.engine_id = "mock"
        engine.generate.return_value = {
            "content": "",
            "tool_calls": [
                {"id": "c1", "name": "calculator", "arguments": '{"expression":"1"}'}
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            "model": "test-model",
            "finish_reason": "tool_calls",
        }
        agent = OrchestratorAgent(
            engine,
            "test-model",
            tools=[_CalculatorStub()],
            max_turns=1,
        )
        result = agent.run("Calc")
        assert result.turns == 1
        assert result.metadata.get("max_turns_exceeded") is True

    def test_agent_turn_end_data_no_tools(self):
        bus = EventBus(record_history=True)
        engine = _make_engine_no_tools("reply")
        agent = OrchestratorAgent(engine, "test-model", bus=bus)
        agent.run("Hi")
        end = [e for e in bus.history if e.event_type == EventType.AGENT_TURN_END][0]
        assert end.data["turns"] == 1
        assert end.data["content_length"] == 5

    def test_result_content_on_max_turns(self):
        engine = MagicMock()
        engine.engine_id = "mock"
        engine.generate.return_value = {
            "content": "partial",
            "tool_calls": [
                {"id": "c1", "name": "calculator", "arguments": '{"expression":"1"}'}
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            "model": "test-model",
            "finish_reason": "tool_calls",
        }
        agent = OrchestratorAgent(
            engine,
            "test-model",
            tools=[_CalculatorStub()],
            max_turns=2,
        )
        result = agent.run("Calc")
        # Should use the partial content if available
        assert result.content == "partial"


class TestOrchestratorStructuredMode:
    """Tests for the structured (THOUGHT/TOOL/INPUT/FINAL_ANSWER) mode."""

    def test_structured_mode_final_answer(self):
        """Structured mode should parse FINAL_ANSWER: correctly."""
        engine = MagicMock()
        engine.engine_id = "mock"
        engine.generate.return_value = {
            "content": "THOUGHT: Easy question.\nFINAL_ANSWER: Paris",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "model": "test-model",
            "finish_reason": "stop",
        }
        agent = OrchestratorAgent(
            engine,
            "test-model",
            mode="structured",
        )
        result = agent.run("What is the capital of France?")
        assert result.content == "Paris"
        assert result.turns == 1
        assert result.tool_results == []

    def test_structured_mode_tool_call(self):
        """Parse TOOL:/INPUT:, execute tool, return final answer."""
        engine = MagicMock()
        engine.engine_id = "mock"
        engine.generate.side_effect = [
            {
                "content": (
                    "THOUGHT: Need to calculate.\n"
                    "TOOL: calculator\n"
                    'INPUT: {"expression":"2+2"}'
                ),
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 10,
                    "total_tokens": 20,
                },
                "model": "test-model",
                "finish_reason": "stop",
            },
            {
                "content": ("THOUGHT: Got 4.\nFINAL_ANSWER: The answer is 4."),
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                    "total_tokens": 30,
                },
                "model": "test-model",
                "finish_reason": "stop",
            },
        ]
        agent = OrchestratorAgent(
            engine,
            "test-model",
            tools=[_CalculatorStub()],
            mode="structured",
        )
        result = agent.run("What is 2+2?")
        assert result.content == "The answer is 4."
        assert result.turns == 2
        assert len(result.tool_results) == 1
        assert result.tool_results[0].tool_name == "calculator"
        assert result.tool_results[0].content == "4"

    def test_structured_mode_enriched_descriptions(self):
        """Structured mode system prompt should contain enriched tool descriptions."""
        engine = MagicMock()
        engine.engine_id = "mock"
        engine.generate.return_value = {
            "content": "FINAL_ANSWER: ok",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "model": "test-model",
            "finish_reason": "stop",
        }
        agent = OrchestratorAgent(
            engine,
            "test-model",
            tools=[_CalculatorStub()],
            mode="structured",
        )
        agent.run("Hello")
        call_args = engine.generate.call_args
        messages = call_args[0][0]
        system_msg = messages[0].content
        assert "### calculator" in system_msg
        assert "expression" in system_msg


class TestOrchestratorParallelTools:
    """Tests for parallel tool execution."""

    def test_parallel_tool_execution(self):
        """Multiple tool calls execute in parallel and return in correct order."""
        import time

        class _SlowTool(BaseTool):
            tool_id = "slow"

            @property
            def spec(self) -> ToolSpec:
                return ToolSpec(
                    name="slow",
                    description="Slow tool.",
                    parameters={
                        "type": "object",
                        "properties": {"id": {"type": "string"}},
                    },
                )

            def execute(self, **params) -> ToolResult:
                time.sleep(0.1)  # Simulate slow operation
                return ToolResult(
                    tool_name="slow",
                    content=f"result_{params.get('id', '')}",
                    success=True,
                )

        engine = MagicMock()
        engine.engine_id = "mock"
        engine.generate.side_effect = [
            {
                "content": "",
                "tool_calls": [
                    {"id": "c1", "name": "slow", "arguments": '{"id":"1"}'},
                    {"id": "c2", "name": "slow", "arguments": '{"id":"2"}'},
                    {"id": "c3", "name": "slow", "arguments": '{"id":"3"}'},
                ],
                "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 3,
                    "total_tokens": 8,
                },
                "model": "test-model",
                "finish_reason": "tool_calls",
            },
            {
                "content": "All done.",
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 3,
                    "total_tokens": 23,
                },
                "model": "test-model",
                "finish_reason": "stop",
            },
        ]

        agent = OrchestratorAgent(
            engine,
            "test-model",
            tools=[_SlowTool()],
            parallel_tools=True,
        )
        t0 = time.time()
        result = agent.run("Do things")
        elapsed = time.time() - t0

        assert result.content == "All done."
        assert len(result.tool_results) == 3
        # Results should be in original order
        assert result.tool_results[0].content == "result_1"
        assert result.tool_results[1].content == "result_2"
        assert result.tool_results[2].content == "result_3"
        # Should be parallel — 3 tools at 0.1s each should take < 0.25s, not 0.3s+
        assert elapsed < 0.25

    def test_sequential_tool_execution(self):
        """parallel_tools=False runs tools sequentially."""
        engine = _make_engine_multi_tool()
        agent = OrchestratorAgent(
            engine,
            "test-model",
            tools=[_CalculatorStub(), _ThinkStub()],
            parallel_tools=False,
        )
        result = agent.run("Do things")
        assert result.content == "Done."
        assert len(result.tool_results) == 2

    def test_single_tool_call_no_parallel(self):
        """Single tool call should not use parallel path even if parallel_tools=True."""
        engine = _make_engine_with_tool_call()
        agent = OrchestratorAgent(
            engine,
            "test-model",
            tools=[_CalculatorStub()],
            parallel_tools=True,
        )
        result = agent.run("What is 2+2?")
        assert result.content == "The answer is 4."


class TestOrchestratorStallDetection:
    """qwen2.5:7b sometimes emits a promissory sentence ("Let me calculate
    that for you.") as a complete generation (finish_reason=stop, no
    tool_calls) instead of answering or calling a tool. The orchestrator
    should nudge once and retry rather than returning the stall as final."""

    def test_looks_like_stall_detects_promissory_phrases(self):
        assert _looks_like_stall("Let me calculate that for you.")
        assert _looks_like_stall("Sure, I can calculate that for you. Let me do that now.")
        assert _looks_like_stall("I'll check that for you now.")
        assert _looks_like_stall("One moment.")

    def test_looks_like_stall_ignores_real_answers(self):
        assert not _looks_like_stall("Paris is the capital of France.")
        assert not _looks_like_stall("The sum of 47 and 89 is 136.")
        assert not _looks_like_stall("")

    def test_looks_like_stall_ignores_answers_that_open_with_a_stall_phrase(self):
        """A response that opens like a stall but goes on to contain the
        actual answer should not be flagged -- the check is anchored to the
        END of the content (nothing followed the promise), not "mentions a
        promissory phrase anywhere"."""
        content_with_real_answer = (
            "Let me calculate that for you. The first 10 Fibonacci numbers "
            "are 0, 1, 1, 2, 3, 5, 8, 13, 21, 34, which sum to 88."
        )
        assert not _looks_like_stall(content_with_real_answer)

    def test_stall_then_final_answer_nudges_once(self):
        """First turn stalls, nudge is injected, second turn answers -> 2 turns."""
        engine = MagicMock()
        engine.engine_id = "mock"
        engine.generate.side_effect = [
            _stall_response("Let me calculate that for you."),
            {
                "content": "The sum of the first 10 Fibonacci numbers is 88.",
                "tool_calls": None,
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                    "total_tokens": 30,
                },
                "model": "test-model",
                "finish_reason": "stop",
            },
        ]
        agent = OrchestratorAgent(engine, "test-model")
        result = agent.run("What's the sum of the first 10 Fibonacci numbers?")
        assert result.content == "The sum of the first 10 Fibonacci numbers is 88."
        assert result.turns == 2
        # Second call's messages must include the nudge, proving it actually
        # retried rather than coincidentally matching a second engine call.
        second_call_messages = engine.generate.call_args_list[1][0][0]
        nudge_texts = [
            m.content for m in second_call_messages if m.role == Role.USER
        ]
        assert any("restate intent" in t.lower() for t in nudge_texts)

    def test_stall_then_tool_call_nudges_once(self):
        """Stall on turn 1, delegate on turn 2, final answer on turn 3."""
        engine = MagicMock()
        engine.engine_id = "mock"
        engine.generate.side_effect = [
            _stall_response("Let me look into that for you."),
            {
                "content": "",
                "tool_calls": [
                    {"id": "c1", "name": "calculator", "arguments": '{"expression":"2+2"}'}
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
                "model": "test-model",
                "finish_reason": "tool_calls",
            },
            {
                "content": "The answer is 4.",
                "tool_calls": None,
                "usage": {"prompt_tokens": 15, "completion_tokens": 5, "total_tokens": 20},
                "model": "test-model",
                "finish_reason": "stop",
            },
        ]
        agent = OrchestratorAgent(engine, "test-model", tools=[_CalculatorStub()])
        result = agent.run("What is 2+2?")
        assert result.content == "The answer is 4."
        assert result.turns == 3
        assert len(result.tool_results) == 1

    def test_stall_nudged_only_once_then_returns_stall(self):
        """If the model keeps stalling even after the nudge, give up after
        one retry rather than looping — return whatever it said."""
        engine = MagicMock()
        engine.engine_id = "mock"
        engine.generate.return_value = _stall_response("Let me check that for you.")
        agent = OrchestratorAgent(engine, "test-model", max_turns=10)
        result = agent.run("What is 2+2?")
        assert result.content == "Let me check that for you."
        assert result.turns == 2
        assert engine.generate.call_count == 2

    def test_no_stall_no_nudge_single_turn(self):
        """A normal short direct answer is returned immediately, no nudge."""
        engine = _make_engine_no_tools("Paris is the capital of France.")
        agent = OrchestratorAgent(engine, "test-model")
        result = agent.run("What's the capital of France?")
        assert result.content == "Paris is the capital of France."
        assert result.turns == 1
        assert engine.generate.call_count == 1
