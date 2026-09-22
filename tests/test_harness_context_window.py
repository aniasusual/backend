"""
Unit tests verifying Ollama context window allocation (num_ctx) in CodingHarness and Subagent loops.
Verifies compliance with [CP-106] Item-1 in the Context Management Specification.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

from plugins.coding_harness import CodingHarness
from context.config import ContextConfig
from config.models import get_model_context_window
from task import run_subprocess, AgentDefinition


class TestHarnessContextWindow(unittest.IsolatedAsyncioTestCase):
    async def test_coding_harness_passes_num_ctx_default_model(self):
        """Verify CodingHarness passes num_ctx=32768 for qwen2.5-coder:14b."""
        harness = CodingHarness(model_name="qwen2.5-coder:14b")

        mock_registry = MagicMock()
        mock_registry.get_tools.return_value = {}
        mock_registry.get_dev_server_info.return_value = None

        context = {
            "registry": mock_registry,
            "messages": [],
            "model": "qwen2.5-coder:14b",
        }

        # Mock ollama AsyncClient
        mock_chunk = MagicMock()
        mock_chunk.message.thinking = None
        mock_chunk.message.tool_calls = None
        mock_chunk.message.content = "All done!"

        async def mock_stream_gen():
            yield mock_chunk

        with patch("ollama.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat = AsyncMock(return_value=mock_stream_gen())
            mock_client_cls.return_value = mock_client

            events = []
            async for evt in harness.process_prompt("Hello world", context):
                events.append(evt)

            # Assert chat was called
            self.assertTrue(mock_client.chat.called)
            call_kwargs = mock_client.chat.call_args.kwargs
            self.assertIn("options", call_kwargs)
            options = call_kwargs["options"]

            expected_ctx = get_model_context_window("qwen2.5-coder:14b")
            self.assertEqual(expected_ctx, 32768)
            self.assertEqual(options.get("num_ctx"), 32768)
            self.assertEqual(options.get("temperature"), 0.5)

    async def test_coding_harness_passes_num_ctx_large_model(self):
        """Verify CodingHarness passes num_ctx=131072 for deepseek-coder-v2:16b."""
        harness = CodingHarness(model_name="deepseek-coder-v2:16b")

        mock_registry = MagicMock()
        mock_registry.get_tools.return_value = {}
        mock_registry.get_dev_server_info.return_value = None

        context = {
            "registry": mock_registry,
            "messages": [],
            "model": "deepseek-coder-v2:16b",
        }

        mock_chunk = MagicMock()
        mock_chunk.message.thinking = None
        mock_chunk.message.tool_calls = None
        mock_chunk.message.content = "Finished task."

        async def mock_stream_gen():
            yield mock_chunk

        with patch("ollama.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat = AsyncMock(return_value=mock_stream_gen())
            mock_client_cls.return_value = mock_client

            async for _ in harness.process_prompt("Refactor code", context):
                pass

            self.assertTrue(mock_client.chat.called)
            call_kwargs = mock_client.chat.call_args.kwargs
            self.assertIn("options", call_kwargs)
            options = call_kwargs["options"]

            expected_ctx = get_model_context_window("deepseek-coder-v2:16b")
            self.assertEqual(expected_ctx, 131072)
            self.assertEqual(options.get("num_ctx"), 131072)

    async def test_coding_harness_passes_num_ctx_7b_model(self):
        """Verify CodingHarness passes num_ctx=32768 and loads 7B profile for qwen2.5-coder:7b."""
        harness = CodingHarness(model_name="qwen2.5-coder:7b")

        mock_registry = MagicMock()
        mock_registry.get_tools.return_value = {}
        mock_registry.get_dev_server_info.return_value = None

        context = {
            "registry": mock_registry,
            "messages": [],
            "model": "qwen2.5-coder:7b",
        }

        mock_chunk = MagicMock()
        mock_chunk.message.thinking = None
        mock_chunk.message.tool_calls = None
        mock_chunk.message.content = "Fast 7B response."

        async def mock_stream_gen():
            yield mock_chunk

        with patch("ollama.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat = AsyncMock(return_value=mock_stream_gen())
            mock_client_cls.return_value = mock_client

            async for _ in harness.process_prompt("Quick fix", context):
                pass

            self.assertTrue(mock_client.chat.called)
            call_kwargs = mock_client.chat.call_args.kwargs
            self.assertIn("options", call_kwargs)
            options = call_kwargs["options"]

            expected_ctx = get_model_context_window("qwen2.5-coder:7b")
            self.assertEqual(expected_ctx, 32768)
            self.assertEqual(options.get("num_ctx"), 32768)

    async def test_coding_harness_passes_num_ctx_qwen3_256k(self):
        """Verify CodingHarness passes num_ctx=262144 for qwen3-coder:30b-a3b."""
        harness = CodingHarness(model_name="qwen3-coder:30b-a3b")

        mock_registry = MagicMock()
        mock_registry.get_tools.return_value = {}
        mock_registry.get_dev_server_info.return_value = None

        context = {
            "registry": mock_registry,
            "messages": [],
            "model": "qwen3-coder:30b-a3b",
        }

        mock_chunk = MagicMock()
        mock_chunk.message.thinking = None
        mock_chunk.message.tool_calls = None
        mock_chunk.message.content = "256k response."

        async def mock_stream():
            yield mock_chunk

        with patch("ollama.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat = AsyncMock(return_value=mock_stream())
            mock_client_cls.return_value = mock_client

            async for _ in harness.process_prompt("Massive context task", context):
                pass

            self.assertTrue(mock_client.chat.called)
            call_kwargs = mock_client.chat.call_args.kwargs
            self.assertIn("options", call_kwargs)
            options = call_kwargs["options"]

            expected_ctx = get_model_context_window("qwen3-coder:30b-a3b")
            self.assertEqual(expected_ctx, 262144)
            self.assertEqual(options.get("num_ctx"), 262144)

    async def test_coding_harness_passes_num_ctx_muse_glimmer_128k(self):
        """Verify CodingHarness passes num_ctx=131072 for muse-glimmer:30b."""
        harness = CodingHarness(model_name="muse-glimmer:30b")

        mock_registry = MagicMock()
        mock_registry.get_tools.return_value = {}
        mock_registry.get_dev_server_info.return_value = None

        context = {
            "registry": mock_registry,
            "messages": [],
            "model": "muse-glimmer:30b",
        }

        mock_chunk = MagicMock()
        mock_chunk.message.thinking = None
        mock_chunk.message.tool_calls = None
        mock_chunk.message.content = "Multimodal 128k response."

        async def mock_stream():
            yield mock_chunk

        with patch("ollama.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat = AsyncMock(return_value=mock_stream())
            mock_client_cls.return_value = mock_client

            async for _ in harness.process_prompt("Multimodal code task", context):
                pass

            self.assertTrue(mock_client.chat.called)
            options = mock_client.chat.call_args.kwargs.get("options", {})
            self.assertEqual(options.get("num_ctx"), 131072)

    async def test_coding_harness_passes_num_ctx_custom_override(self):
        """Verify CodingHarness respects explicit context_window override passed in context dict."""
        harness = CodingHarness(model_name="qwen2.5-coder:14b")

        mock_registry = MagicMock()
        mock_registry.get_tools.return_value = {}
        mock_registry.get_dev_server_info.return_value = None

        context = {
            "registry": mock_registry,
            "messages": [],
            "model": "qwen2.5-coder:14b",
            "context_window": 65536,
        }

        mock_chunk = MagicMock()
        mock_chunk.message.thinking = None
        mock_chunk.message.tool_calls = None
        mock_chunk.message.content = "Overridden window response."

        async def mock_stream():
            yield mock_chunk

        with patch("ollama.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat = AsyncMock(return_value=mock_stream())
            mock_client_cls.return_value = mock_client

            async for _ in harness.process_prompt("Custom window task", context):
                pass

            self.assertTrue(mock_client.chat.called)
            options = mock_client.chat.call_args.kwargs.get("options", {})
            self.assertEqual(options.get("num_ctx"), 65536)

    async def test_coding_harness_passes_num_ctx_unknown_model_fallback(self):
        """Verify CodingHarness passes default num_ctx=32768 for unknown models."""
        harness = CodingHarness(model_name="unlisted-frontier-model:99b")

        mock_registry = MagicMock()
        mock_registry.get_tools.return_value = {}
        mock_registry.get_dev_server_info.return_value = None
        mock_registry.sandbox_path = None

        context = {
            "registry": mock_registry,
            "messages": [],
            "model": "unlisted-frontier-model:99b",
        }

        mock_chunk = MagicMock()
        mock_chunk.message.thinking = None
        mock_chunk.message.tool_calls = None
        mock_chunk.message.content = "Unknown model response."

        async def mock_stream():
            yield mock_chunk

        with patch("ollama.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat = AsyncMock(return_value=mock_stream())
            mock_client_cls.return_value = mock_client

            async for _ in harness.process_prompt("Test fallback", context):
                pass

            self.assertTrue(mock_client.chat.called)
            options = mock_client.chat.call_args.kwargs.get("options", {})
            self.assertEqual(options.get("num_ctx"), 32768)

    async def test_subagent_runner_passes_num_ctx(self):
        """Verify task executor passes num_ctx in options when invoking client.chat()."""
        mock_response = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "yield", "arguments": {"data": {"done": True}}}}],
            },
            "prompt_eval_count": 50,
            "eval_count": 20,
        }
        mock_client = MagicMock()
        mock_client.chat.return_value = mock_response

        defn = AgentDefinition(name="TestSubagent", description="Helper", tools=["read_file"])
        await run_subprocess(
            id="test_sub_ctx",
            agent_definition=defn,
            assignment="Inspect the codebase.",
            tool_registry=MagicMock(),
            client=mock_client,
        )

        self.assertTrue(mock_client.chat.called)
        call_kwargs = mock_client.chat.call_args.kwargs
        self.assertIn("options", call_kwargs)
        options = call_kwargs["options"]
        self.assertEqual(options.get("num_ctx"), 16384)
    async def test_coding_harness_ingestion_compression_and_no_directions(self):
        """Verify CodingHarness compresses >1.8k char tool outputs and does NOT append synthetic directions."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            harness = CodingHarness(model_name="qwen2.5-coder:7b")

            long_tool_output = "\n".join([f"Build step {i}: Compiling module {i}" for i in range(1, 101)])
            self.assertGreater(len(long_tool_output), 1800)

            mock_registry = MagicMock()
            mock_registry.sandbox_path = project_path
            mock_registry.get_tools.return_value = {
                "execute_command": MagicMock(return_value=long_tool_output)
            }
            mock_registry.get_dev_server_info.return_value = None

            context = {
                "registry": mock_registry,
                "messages": [],
                "model": "qwen2.5-coder:7b",
            }

            # Chunk 1: Model invokes execute_command
            mock_chunk_tool = MagicMock()
            mock_chunk_tool.message.thinking = None
            mock_chunk_tool.message.content = ""
            mock_tool_call = MagicMock()
            mock_tool_call.function.name = "execute_command"
            mock_tool_call.function.arguments = {"command": "npm run build"}
            mock_chunk_tool.message.tool_calls = [mock_tool_call]

            # Chunk 2: Model finishes
            mock_chunk_finish = MagicMock()
            mock_chunk_finish.message.thinking = None
            mock_chunk_finish.message.tool_calls = None
            mock_chunk_finish.message.content = "Build complete."

            async def mock_stream_gen_1():
                yield mock_chunk_tool

            async def mock_stream_gen_2():
                yield mock_chunk_finish

            with patch("ollama.AsyncClient") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.chat = AsyncMock(side_effect=[mock_stream_gen_1(), mock_stream_gen_2()])
                mock_client_cls.return_value = mock_client

                events = []
                async for evt in harness.process_prompt("Run build", context):
                    events.append(evt)

                # Inspect tool message appended to context["messages"]
                tool_msgs = [m for m in context["messages"] if m.get("role") == "tool"]
                self.assertEqual(len(tool_msgs), 1)
                tool_content = tool_msgs[0]["content"]

                # 1. Output must be compressed at ingestion
                self.assertIn("Omitted", tool_content)
                self.assertIn("Full uncompressed output saved to", tool_content)
                self.assertIn("Build step 1:", tool_content)
                self.assertIn("Build step 100:", tool_content)

                # 2. No synthetic conversational directions in message
                self.assertNotIn("Please proceed with the next step", tool_content)
                self.assertNotIn("Do NOT call finish yet", tool_content)

    async def test_coding_harness_scopes_tool_schemas_and_map(self):
        """Verify CodingHarness filters schemas passed to Ollama based on profile and context allowed_tools."""
        harness = CodingHarness(model_name="qwen2.5-coder:7b")

        mock_registry = MagicMock()
        mock_registry.get_tools.return_value = {
            "read_file": lambda **kwargs: "read_ok",
            "write_file": lambda **kwargs: "write_ok",
            "execute_command": lambda **kwargs: "exec_ok",
        }
        mock_registry.get_dev_server_info.return_value = None

        mock_chunk = MagicMock()
        mock_chunk.message.thinking = None
        mock_chunk.message.tool_calls = None
        mock_chunk.message.content = "Done."

        async def mock_stream():
            yield mock_chunk

        # Case 1: Custom allowed_tools passed in context
        context_custom = {
            "registry": mock_registry,
            "messages": [],
            "model": "qwen2.5-coder:7b",
            "allowed_tools": ["read_file"],
        }

        with patch("ollama.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat = AsyncMock(return_value=mock_stream())
            mock_client_cls.return_value = mock_client

            async for _ in harness.process_prompt("Read a file", context_custom):
                pass

            call_kwargs = mock_client.chat.call_args.kwargs
            self.assertIn("tools", call_kwargs)
            passed_tools = call_kwargs["tools"]
            schema_names = [t["function"]["name"] for t in passed_tools]
            self.assertEqual(schema_names, ["read_file"])

    async def test_coding_harness_emits_context_telemetry_and_debug_payload(self):
        """Verify CodingHarness emits real-time context telemetry events and attaches debug payloads."""
        harness = CodingHarness(model_name="qwen2.5-coder:14b")

        mock_registry = MagicMock()
        mock_registry.get_tools.return_value = {
            "read_file": lambda **kwargs: "hello world content",
        }
        mock_registry.get_dev_server_info.return_value = None
        mock_registry.mounted_virtual_ram = {"main.py": "x = 42"}

        # Iteration 0: tool call to read_file
        chunk_iter0 = MagicMock()
        chunk_iter0.message.thinking = None
        chunk_iter0.message.content = ""
        mock_tc = MagicMock()
        mock_tc.function.name = "read_file"
        mock_tc.function.arguments = {"file_path": "test.txt"}
        chunk_iter0.message.tool_calls = [mock_tc]

        # Iteration 1: final conversational completion
        chunk_iter1 = MagicMock()
        chunk_iter1.message.thinking = None
        chunk_iter1.message.tool_calls = None
        chunk_iter1.message.content = "File read successfully."

        async def mock_stream_iter0():
            yield chunk_iter0

        async def mock_stream_iter1():
            yield chunk_iter1

        context = {
            "registry": mock_registry,
            "messages": [],
            "model": "qwen2.5-coder:14b",
        }

        with patch("ollama.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat = AsyncMock(side_effect=[mock_stream_iter0(), mock_stream_iter1()])
            mock_client_cls.return_value = mock_client

            events = []
            async for evt in harness.process_prompt("Read test.txt", context):
                events.append(evt)

            telemetry_events = [e for e in events if e.get("type") == "context_telemetry"]
            # Initial turn telemetry + iteration 0 + iteration 1 + turn completion telemetry
            self.assertGreaterEqual(len(telemetry_events), 3)

            first_telemetry = telemetry_events[0]["telemetry"]
            self.assertEqual(first_telemetry["context_window"], 32768)
            self.assertIn("total_tokens", first_telemetry)
            self.assertIn("static_tokens", first_telemetry)
            self.assertIn("virtual_ram_tokens", first_telemetry)
            self.assertIn("ephemeral_tokens", first_telemetry)
            self.assertIn("schema_tokens", first_telemetry)
            self.assertIn("usage_pct", first_telemetry)
            self.assertIn("status", first_telemetry)
            self.assertEqual(first_telemetry["virtual_ram_files"], 1)

            # Verify llm_debug event contains context_telemetry
            debug_events = [e for e in events if e.get("type") == "llm_debug"]
            self.assertGreaterEqual(len(debug_events), 1)
            self.assertIn("context_telemetry", debug_events[0]["debug"])

            # Verify tool_result event contains debug payload
            tool_res_events = [e for e in events if e.get("type") == "tool_result"]
            self.assertEqual(len(tool_res_events), 1)
            self.assertIn("debug", tool_res_events[0])
            self.assertIn("context_telemetry", tool_res_events[0]["debug"])

            # Verify final telemetry event before Done
            last_telemetry = telemetry_events[-1]["telemetry"]
            self.assertGreater(last_telemetry["total_tokens"], 0)

    async def test_coding_harness_provisions_all_context_roadmap_tools_by_default(self):
        """Verify CodingHarness passes 100% of context management roadmap tools to Ollama by default."""
        from tools.registry import ToolRegistry
        from config.settings import PROJECTS_ROOT
        import shutil

        test_dir = PROJECTS_ROOT / "_test_harness_tools"
        test_dir.mkdir(parents=True, exist_ok=True)
        try:
            registry = ToolRegistry(test_dir)
            harness = CodingHarness(model_name="qwen2.5-coder:14b")

            mock_chunk = MagicMock()
            mock_chunk.message.thinking = None
            mock_chunk.message.tool_calls = None
            mock_chunk.message.content = "Done."

            async def mock_stream():
                yield mock_chunk

            context = {
                "registry": registry,
                "messages": [],
                "model": "qwen2.5-coder:14b",
            }

            with patch("ollama.AsyncClient") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.chat = AsyncMock(return_value=mock_stream())
                mock_client_cls.return_value = mock_client

                async for _ in harness.process_prompt("Discover and analyze workspace", context):
                    pass

                call_kwargs = mock_client.chat.call_args.kwargs
                self.assertIn("tools", call_kwargs)
                passed_tools = call_kwargs["tools"]
                schema_names = set(t["function"]["name"] for t in passed_tools)

                # Verify all roadmap tools are actively passed to the agent
                roadmap_tools = {
                    "read_file",                  # ITEM-5
                    "locate_files_by_pattern",    # ITEM-6
                    "mount_file",                 # ITEM-8
                    "unmount_file",               # ITEM-8
                    "close_file",                 # ITEM-8
                    "list_mounted_files",         # ITEM-8
                    "extract_signatures",         # ITEM-9
                    "map_dependencies",           # ITEM-10
                }
                for tool in roadmap_tools:
                    self.assertIn(tool, schema_names, f"Roadmap tool '{tool}' is missing from agent tools!")
        finally:
            if test_dir.exists():
                shutil.rmtree(test_dir, ignore_errors=True)
if __name__ == "__main__":
    unittest.main()
