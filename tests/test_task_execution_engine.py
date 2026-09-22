"""
Unit tests for Phase 2 Execution Engine:
- YieldTool and JSON Schema validation (strict and permissive)
- Jinja2 prompt rendering (system prompt, user assignment, yield reminders)
- Tool scoping (whitelisting, yield injection, parent-owned tool stripping)
- run_subprocess execution flow with mocked Ollama chat interactions
"""

import unittest
import asyncio
from unittest.mock import MagicMock

from task.types import AgentDefinition, SingleResult
from task.yield_tool import YieldTool
from task.schema_validator import validate_schema
from task.prompt_renderer import (
    render_subagent_system_prompt,
    render_subagent_user_prompt,
    render_yield_reminder,
)
from task.executor import build_scoped_tools, run_subprocess


class TestYieldToolAndValidator(unittest.TestCase):
    """Test YieldTool deliverables, incremental sections, and schema validation."""

    def test_schema_validator_primitives(self):
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "status": {"enum": ["ok", "fail"]},
            },
            "required": ["name", "status"],
        }

        # Valid payload
        valid, err = validate_schema({"name": "test", "status": "ok", "count": 5, "tags": ["a", "b"]}, schema)
        self.assertTrue(valid)
        self.assertIsNone(err)

        # Missing required field
        valid, err = validate_schema({"name": "test"}, schema)
        self.assertFalse(valid)
        self.assertIn("Missing required property 'status'", err)

        # Invalid type
        valid, err = validate_schema({"name": 123, "status": "ok"}, schema)
        self.assertFalse(valid)
        self.assertIn("expected string", err)

        # Invalid enum value
        valid, err = validate_schema({"name": "test", "status": "invalid_status"}, schema)
        self.assertFalse(valid)
        self.assertIn("not in allowed enum values", err)

    def test_yield_tool_terminal_and_error(self):
        tool = YieldTool()
        # Test error reporting
        res = tool.execute(error="Cannot access database")
        self.assertTrue(tool.called)
        self.assertEqual(tool.error, "Cannot access database")
        self.assertIn("Yield blocker recorded", res)

        # Test terminal data
        tool = YieldTool()
        res = tool.execute(data={"summary": "Task complete", "files": ["app.py"]})
        self.assertTrue(tool.called)
        self.assertTrue(tool.is_terminal)
        self.assertEqual(tool.data["summary"], "Task complete")
        self.assertIn("Yield accepted", res)

    def test_yield_tool_incremental_sections(self):
        tool = YieldTool()
        res1 = tool.execute(data={"note": "step 1"}, type="step1")
        self.assertFalse(tool.is_terminal)
        self.assertIn("Incremental section 'step1' recorded", res1)

        res2 = tool.execute(data={"note": "step 2"}, type="step2")
        self.assertIn("Incremental section 'step2' recorded", res2)

        # Final terminal yield merges incremental sections
        tool.execute(type="result")
        self.assertTrue(tool.is_terminal)
        self.assertIn("step1", tool.data)
        self.assertIn("step2", tool.data)

    def test_yield_tool_schema_enforcement_strict(self):
        schema = {
            "type": "object",
            "properties": {"verdict": {"enum": ["passed", "failed"]}},
            "required": ["verdict"],
        }
        tool = YieldTool(output_schema=schema, schema_mode="strict")

        # Invalid payload rejected in strict mode
        res = tool.execute(data={"verdict": "unknown"})
        self.assertFalse(tool.called)
        self.assertIn("Yield rejected: Schema validation error", res)

        # Valid payload accepted
        res = tool.execute(data={"verdict": "passed"})
        self.assertTrue(tool.called)
        self.assertIn("Yield accepted", res)
    def test_schema_validator_unions_and_nullability(self):
        """Verify union types and nullable fields validate correctly."""
        schema = {
            "type": "object",
            "properties": {
                "nickname": {"type": ["string", "null"]},
                "bio": {"type": "string", "nullable": True},
            },
        }
        # Null values should pass
        valid, err = validate_schema({"nickname": None, "bio": None}, schema)
        self.assertTrue(valid)
        self.assertIsNone(err)

        # String values should pass
        valid, err = validate_schema({"nickname": "Ace", "bio": "Coder"}, schema)
        self.assertTrue(valid)
        self.assertIsNone(err)

        # Wrong type should fail
        valid, err = validate_schema({"nickname": 123}, schema)
        self.assertFalse(valid)

    def test_schema_validator_composition_and_bounds(self):
        """Verify anyOf/oneOf/allOf and numeric/string/array bounds."""
        # Bounds
        num_schema = {"type": "integer", "minimum": 1, "maximum": 10}
        self.assertTrue(validate_schema(5, num_schema)[0])
        self.assertFalse(validate_schema(0, num_schema)[0])
        self.assertFalse(validate_schema(15, num_schema)[0])

        str_schema = {"type": "string", "minLength": 2, "maxLength": 5}
        self.assertTrue(validate_schema("abc", str_schema)[0])
        self.assertFalse(validate_schema("a", str_schema)[0])
        self.assertFalse(validate_schema("abcdef", str_schema)[0])

        arr_schema = {"type": "array", "minItems": 1, "maxItems": 2}
        self.assertTrue(validate_schema([1], arr_schema)[0])
        self.assertFalse(validate_schema([], arr_schema)[0])
        self.assertFalse(validate_schema([1, 2, 3], arr_schema)[0])

        # anyOf
        any_schema = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
        self.assertTrue(validate_schema("hello", any_schema)[0])
        self.assertTrue(validate_schema(42, any_schema)[0])
        self.assertFalse(validate_schema(True, any_schema)[0])

    def test_yield_tool_json_string_data(self):
        """Verify YieldTool accepts stringified JSON payloads from LLMs."""
        schema = {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}
        tool = YieldTool(output_schema=schema, schema_mode="strict")
        res = tool.execute(data='{"summary": "Parsed from JSON string"}')
        self.assertTrue(tool.called)
        self.assertEqual(tool.data["summary"], "Parsed from JSON string")
        self.assertIn("Yield accepted", res)

    def test_yield_tool_merges_incremental_with_terminal_data(self):
        """Verify incremental sections are preserved and merged into terminal data."""
        tool = YieldTool()
        tool.execute(data={"step": 1}, type="step1")
        tool.execute(data={"step": 2}, type="step2")
        # Terminal yield with additional terminal data
        tool.execute(data={"summary": "all done"})
        self.assertTrue(tool.is_terminal)
        self.assertIn("step1", tool.data)
        self.assertIn("step2", tool.data)
        self.assertEqual(tool.data["summary"], "all done")


class TestPromptRenderer(unittest.TestCase):
    """Test Jinja2 prompt assembly for system, user, and yield reminders."""

    def test_render_system_prompt_complete(self):
        agent = AgentDefinition(
            name="scout",
            description="Explorer",
            system_prompt="Investigate files.",
        )
        rendered = render_subagent_system_prompt(
            agent_definition=agent,
            context="Refactor authentication endpoints",
            plan_reference="1. Audit tokens\n2. Fix middleware",
            plan_reference_path="local://PLAN.md",
            worktree="/tmp/worktree_123",
            self_id="scout_abc",
            peers=[{"id": "reviewer_xyz", "agent": "reviewer", "status": "running"}],
            output_schema={"type": "object", "properties": {"summary": {"type": "string"}}},
        )

        self.assertIn("§ Role\nInvestigate files.", rendered)
        self.assertIn("§ Context\nRefactor authentication endpoints", rendered)
        self.assertIn("§ Plan", rendered)
        self.assertIn("local://PLAN.md", rendered)
        self.assertIn("isolated Git working tree at `/tmp/worktree_123`", rendered)
        self.assertIn("Your ID is `scout_abc`", rendered)
        self.assertIn("reviewer_xyz", rendered)
        self.assertIn("§ Completion", rendered)
        self.assertIn('"summary"', rendered)

    def test_render_user_prompt(self):
        rendered = render_subagent_user_prompt("Locate all express routers")
        self.assertEqual(rendered, "Complete assignment thoroughly:\n\nLocate all express routers")

    def test_render_yield_reminders(self):
        std_reminder = render_yield_reminder(retry_count=1, max_retries=3, budget_stop=False)
        self.assertIn("Reminder (1/3)", std_reminder)
        self.assertIn("did not call `yield`", std_reminder)

        budget_reminder = render_yield_reminder(budget_stop=True)
        self.assertIn("Soft request budget reached", budget_reminder)


class TestToolScoping(unittest.TestCase):
    """Test scoping tools to agent whitelist, stripping parent tools, injecting yield and hub."""

    def test_tool_scoping(self):
        agent = AgentDefinition(
            name="reader",
            description="Reader agent",
            tools=["read_file", "glob_files", "todo", "task"],  # todo and task should be stripped
        )

        dummy_registry = MagicMock()
        dummy_registry.get_tools.return_value = {
            "read_file": lambda **kwargs: "file content",
            "write_file": lambda **kwargs: "written",
            "glob_files": lambda **kwargs: ["a.py"],
            "todo": lambda **kwargs: "todo_list",
            "task": lambda **kwargs: "spawned",
        }

        yield_tool = YieldTool()
        hub_mock = MagicMock()

        scoped_map, scoped_schemas = build_scoped_tools(
            agent_definition=agent,
            tool_registry=dummy_registry,
            yield_tool=yield_tool,
            hub_tool=hub_mock,
        )

        # Verify allowed tools are included
        self.assertIn("read_file", scoped_map)
        self.assertIn("glob_files", scoped_map)
        self.assertIn("yield", scoped_map)
        self.assertIn("hub", scoped_map)

        # Verify non-whitelisted tool excluded
        self.assertNotIn("write_file", scoped_map)

        # Verify parent-owned tools are stripped
        self.assertNotIn("todo", scoped_map)
        self.assertNotIn("task", scoped_map)

    def test_bundled_agents_have_context_roadmap_tools(self):
        from task.agents import load_bundled_agents
        agents = load_bundled_agents()

        scout = agents["scout"]
        self.assertIn("locate_files_by_pattern", scout.tools)
        self.assertIn("extract_signatures", scout.tools)
        self.assertIn("map_dependencies", scout.tools)

        task = agents["task"]
        self.assertIn("locate_files_by_pattern", task.tools)
        self.assertIn("extract_signatures", task.tools)
        self.assertIn("map_dependencies", task.tools)
        self.assertIn("mount_file", task.tools)
        self.assertIn("unmount_file", task.tools)
        self.assertIn("close_file", task.tools)
        self.assertIn("list_mounted_files", task.tools)
        reviewer = agents["reviewer"]
        self.assertIn("extract_signatures", reviewer.tools)
        self.assertIn("map_dependencies", reviewer.tools)

        troubleshoot = agents["troubleshoot"]
        self.assertIn("extract_signatures", troubleshoot.tools)
        self.assertIn("map_dependencies", troubleshoot.tools)
        self.assertIn("locate_files_by_pattern", troubleshoot.tools)


class TestRunSubprocessFlow(unittest.IsolatedAsyncioTestCase):
    """Test run_subprocess end-to-end with simulated Ollama client."""

    async def test_subprocess_happy_path_with_yield(self):
        agent = AgentDefinition(
            name="scout",
            description="Explorer",
            tools=["read_file"],
            output_schema={"type": "object", "properties": {"files": {"type": "array"}}},
        )

        mock_registry = MagicMock()
        mock_registry.get_tools.return_value = {
            "read_file": lambda file_path: f"Content of {file_path}",
        }

        mock_client = MagicMock()
        # Iteration 1: calls read_file
        # Iteration 2: calls yield with output
        mock_client.chat.side_effect = [
            {
                "message": {
                    "content": "Reading the file first",
                    "tool_calls": [
                        {"function": {"name": "read_file", "arguments": {"file_path": "server.py"}}}
                    ],
                },
                "prompt_eval_count": 50,
                "eval_count": 20,
            },
            {
                "message": {
                    "content": "Delivering results",
                    "tool_calls": [
                        {"function": {"name": "yield", "arguments": {"data": {"files": ["server.py"]}}}}
                    ],
                },
                "prompt_eval_count": 80,
                "eval_count": 30,
            },
        ]

        events = []
        result: SingleResult = await run_subprocess(
            id="test_sub_1",
            agent_definition=agent,
            assignment="Check server.py",
            tool_registry=mock_registry,
            client=mock_client,
            event_callback=lambda evt: events.append(evt),
        )

        self.assertEqual(result.id, "test_sub_1")
        self.assertEqual(result.exit_code, 0)
        self.assertIsNone(result.error)
        self.assertEqual(result.structured_output, {"files": ["server.py"]})
        self.assertEqual(result.requests, 2)
        self.assertEqual(result.total_tokens, 180)

        # Check telemetry events
        event_names = [e["event"] for e in events]
        self.assertIn("start", event_names)
        self.assertIn("tool_call", event_names)
        self.assertIn("tool_executed", event_names)
        self.assertIn("finish", event_names)

    async def test_subprocess_reminder_ladder_when_yield_missing(self):
        agent = AgentDefinition(
            name="worker",
            description="Worker",
            tools=["read_file"],
        )

        mock_registry = MagicMock()
        mock_registry.get_tools.return_value = {"read_file": lambda file_path: "data"}

        mock_client = MagicMock()
        # Turn 1: Model reads file
        # Turn 2: Model talks without calling yield -> triggers reminder
        # Turn 3: Model calls yield
        mock_client.chat.side_effect = [
            {
                "message": {
                    "content": "",
                    "tool_calls": [{"function": {"name": "read_file", "arguments": {"file_path": "a.txt"}}}],
                },
            },
            {
                "message": {
                    "content": "I finished looking at the file.",
                    "tool_calls": [],
                },
            },
            {
                "message": {
                    "content": "",
                    "tool_calls": [{"function": {"name": "yield", "arguments": {"data": {"done": True}}}}],
                },
            },
        ]

        result = await run_subprocess(
            id="test_sub_2",
            agent_definition=agent,
            assignment="Inspect a.txt",
            tool_registry=mock_registry,
            client=mock_client,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.structured_output, {"done": True})
        self.assertEqual(result.requests, 3)
    async def test_hard_request_ceiling_stops_infinite_tool_loop(self):
        """Verify runaway tool calling is halted at the hard request ceiling."""
        agent = AgentDefinition(name="runner", description="Runaway", tools=["read_file"])
        mock_registry = MagicMock()
        mock_registry.get_tools.return_value = {"read_file": lambda **kwargs: "data"}

        # Model keeps making tool calls and never calls yield
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "message": {
                "content": "Reading again...",
                "tool_calls": [{"function": {"name": "read_file", "arguments": {}}}],
            }
        }

        # Set soft budget 2 -> ceiling should be 2 + 3 + 2 = 7
        result = await run_subprocess(
            id="test_runaway",
            agent_definition=agent,
            assignment="Loop test",
            tool_registry=mock_registry,
            soft_request_budget=2,
            max_yield_retries=2,
            client=mock_client,
        )

        self.assertTrue(result.requests <= 7)
        self.assertTrue(result.exit_code == 0)
        self.assertIn("Subagent halted", result.structured_output.get("summary", ""))

    async def test_subprocess_model_role_resolution(self):
        """Verify model role @smol resolves to configured smol model."""
        agent = AgentDefinition(name="scout", description="Explorer", tools=["read_file"], model="@smol")
        mock_registry = MagicMock()
        mock_registry.get_tools.return_value = {"read_file": lambda **kwargs: "data"}

        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "message": {
                "content": "",
                "tool_calls": [{"function": {"name": "yield", "arguments": {"data": {"ok": True}}}}],
            }
        }

        result = await run_subprocess(
            id="test_role",
            agent_definition=agent,
            assignment="Role check",
            tool_registry=mock_registry,
            client=mock_client,
        )

        self.assertEqual(result.model_role, "@smol")
        self.assertEqual(result.model_override, "qwen2.5-coder:7b")

    async def test_subprocess_async_tool_callable(self):
        """Verify async tools are awaited and do not leak coroutine objects."""
        async def async_read_tool(file_path: str = "") -> str:
            await asyncio.sleep(0.01)
            return f"Async read: {file_path}"

        agent = AgentDefinition(name="async_worker", description="Worker", tools=["read_file"])
        mock_registry = MagicMock()
        mock_registry.get_tools.return_value = {"read_file": async_read_tool}

        mock_client = MagicMock()
        mock_client.chat.side_effect = [
            {
                "message": {
                    "content": "",
                    "tool_calls": [{"function": {"name": "read_file", "arguments": {"file_path": "test.txt"}}}],
                }
            },
            {
                "message": {
                    "content": "",
                    "tool_calls": [{"function": {"name": "yield", "arguments": {"data": {"done": True}}}}],
                }
            },
        ]

        events = []
        result = await run_subprocess(
            id="test_async",
            agent_definition=agent,
            assignment="Async tool test",
            tool_registry=mock_registry,
            client=mock_client,
            event_callback=lambda e: events.append(e),
        )

        read_exec_events = [e for e in events if e.get("event") == "tool_executed" and e.get("tool") == "read_file"]
        self.assertEqual(len(read_exec_events), 1)
        self.assertIn("Async read: test.txt", read_exec_events[0]["result"])
        self.assertNotIn("<coroutine object", read_exec_events[0]["result"])

    async def test_subprocess_unclosed_think_tag(self):
        """Verify unclosed <think> tag is parsed into thought event without leaking."""
        agent = AgentDefinition(name="thinker", description="Worker", tools=["read_file"])
        mock_registry = MagicMock()
        mock_registry.get_tools.return_value = {}

        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "message": {
                "content": "Answer here <think>Unclosed internal reasoning...",
                "tool_calls": [{"function": {"name": "yield", "arguments": {"data": {"result": 1}}}}],
            }
        }

        events = []
        await run_subprocess(
            id="test_think",
            agent_definition=agent,
            assignment="Think test",
            tool_registry=mock_registry,
            client=mock_client,
            event_callback=lambda e: events.append(e),
        )

        thought_events = [e for e in events if e.get("event") == "thought"]
        self.assertTrue(any("Unclosed internal reasoning" in t.get("content", "") for t in thought_events))


if __name__ == "__main__":
    unittest.main()
