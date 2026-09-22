"""
Test Suite for Lowkey Chat History Persistence & Context Invariant.

Verifies:
1. ChatHistoryManager persistence, atomic saves, and UI/LLM format extraction.
2. Dangling tool call pruning (crash recovery).
3. The Core Invariant: Closing and reopening the project produces an
   identical, drift-free LLM context sequence for subsequent turns.
4. Subagent action extraction across multi-turn compaction.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from project_manager.chat_history import ChatHistoryManager
from context.manager import ContextManager
from context.compactor import ContextCompactor


class TestChatHistoryManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_load_turn(self):
        turn_data = {
            "turn_id": "turn_1",
            "timestamp": "2026-09-03T22:00:00Z",
            "clean_user_prompt": "Create a counter app",
            "model": "qwen2.5-coder:7b",
            "status": "completed",
            "ui_events": [
                {"type": "user", "content": "Create a counter app"},
                {"type": "thinking", "content": "Planning counter component..."},
                {
                    "type": "tool_call",
                    "name": "invoke_design_agent",
                    "arguments": {"problem_statement": "counter app"},
                },
                {"type": "tool_result", "name": "invoke_design_agent", "result": "Design applied"},
                {
                    "type": "tool_call",
                    "name": "write_file",
                    "arguments": {"file_path": "src/App.jsx", "content": "..."},
                },
                {"type": "tool_result", "name": "write_file", "result": "File written"},
                {"type": "token", "content": "Created the counter application."},
                {"type": "status", "content": "Done"},
            ],
            "llm_messages": [
                {
                    "role": "user",
                    "content": "Create a counter app\n\n[Instruction: Directly execute tools...]",
                },
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "invoke_design_agent",
                                "arguments": {"problem_statement": "counter app"},
                            },
                        }
                    ],
                },
                {"role": "tool", "name": "invoke_design_agent", "content": "Design applied"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "write_file",
                                "arguments": {"file_path": "src/App.jsx", "content": "..."},
                            },
                        }
                    ],
                },
                {"role": "tool", "name": "write_file", "content": "File written"},
                {"role": "assistant", "content": "Created the counter application."},
            ],
        }

        # Save turn
        ChatHistoryManager.save_turn(self.temp_dir, turn_data)

        # Verify chat file exists
        chat_file = ChatHistoryManager.get_chat_file(self.temp_dir)
        self.assertTrue(chat_file.exists())

        # Load history
        history = ChatHistoryManager.load_history(self.temp_dir)
        self.assertEqual(len(history["turns"]), 1)
        self.assertEqual(history["turns"][0]["turn_id"], "turn_1")

        # Verify UI events (past tools & thoughts collapsed)
        ui_events = ChatHistoryManager.get_ui_events(self.temp_dir)
        self.assertEqual(len(ui_events), 8)
        tool_call_evt = next(e for e in ui_events if e["type"] == "tool_call")
        self.assertTrue(tool_call_evt.get("collapsed"))
        thinking_evt = next(e for e in ui_events if e["type"] == "thinking")
        self.assertTrue(thinking_evt.get("collapsed"))

        # Verify LLM messages
        llm_messages = ChatHistoryManager.get_llm_messages(self.temp_dir)
        self.assertEqual(len(llm_messages), 6)

    def test_prune_dangling_tool_calls(self):
        # Assistant had a tool call, but the process crashed before tool result arrived
        unclosed_messages = [
            {"role": "user", "content": "Do something"},
            {
                "role": "assistant",
                "content": "Working on it...",
                "tool_calls": [
                    {"type": "function", "function": {"name": "write_file", "arguments": {}}}
                ],
            },
            # Missing tool message!
        ]

        cleaned = ChatHistoryManager.prune_dangling_tool_calls(unclosed_messages)
        self.assertEqual(len(cleaned), 2)
        # Assistant message should have tool_calls pruned so Ollama won't reject with 400 Bad Request
        self.assertNotIn("tool_calls", cleaned[1])
        self.assertEqual(cleaned[1]["content"], "Working on it...")

    def test_prune_orphaned_tool_messages(self):
        """Tool messages without a preceding assistant tool call are pruned."""
        messages = [
            {"role": "system", "content": "System"},
            {"role": "tool", "content": "Orphaned result", "name": "locate_files_by_pattern"},
            {"role": "user", "content": "Active prompt"},
        ]
        cleaned = ChatHistoryManager.prune_dangling_tool_calls(messages)
        self.assertEqual(len(cleaned), 2)
        self.assertEqual(cleaned[0]["role"], "system")
        self.assertEqual(cleaned[1]["role"], "user")


class TestContextInvariant(unittest.TestCase):
    """
    Validates that reopening the app produces an exact, mathematically equivalent context.
    """

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.system_prompt = "You are Lowkey, a local full-stack coding assistant."

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_context_equivalence_on_app_restart(self):
        # Scenario: Turn 1 executes in memory
        turn1_llm_messages = [
            {
                "role": "user",
                "content": "Build a Kanban app\n\n[Instruction: Directly execute tools...]",
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "invoke_design_agent",
                            "arguments": {"problem_statement": "Kanban app"},
                        },
                    }
                ],
            },
            {"role": "tool", "name": "invoke_design_agent", "content": "Design system applied."},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "write_files",
                            "arguments": {
                                "files": [
                                    {"file_path": "server/index.js", "content": "..."},
                                    {"file_path": "src/App.jsx", "content": "..."},
                                ]
                            },
                        },
                    }
                ],
            },
            {"role": "tool", "name": "write_files", "content": "Wrote 2 files."},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "finish",
                            "arguments": {"summary": "Kanban app completed."},
                        },
                    }
                ],
            },
            {"role": "tool", "name": "finish", "content": "Done."},
            {"role": "assistant", "content": "I have created the Kanban app with full-stack support."},
        ]

        # Case A: Live in-memory session. Server was never closed.
        in_memory_session = list(turn1_llm_messages)
        prepared_in_memory = ContextManager.prepare_messages(
            user_prompt="Add dark mode toggle",
            system_prompt=self.system_prompt,
            existing_messages=in_memory_session,
            model_name="qwen2.5-coder:7b",
        )

        # Case B: Server was closed, then reopened.
        # Save Turn 1 to disk
        turn1_record = {
            "turn_id": "turn_1",
            "timestamp": "2026-09-03T22:00:00Z",
            "clean_user_prompt": "Build a Kanban app",
            "model": "qwen2.5-coder:7b",
            "status": "completed",
            "ui_events": [],
            "llm_messages": turn1_llm_messages,
        }
        ChatHistoryManager.save_turn(self.temp_dir, turn1_record)

        # Reopen: Load from disk
        reloaded_messages = ChatHistoryManager.get_llm_messages(self.temp_dir)

        # Prepare messages for Turn 2 using reloaded messages
        prepared_from_disk = ContextManager.prepare_messages(
            user_prompt="Add dark mode toggle",
            system_prompt=self.system_prompt,
            existing_messages=reloaded_messages,
            model_name="qwen2.5-coder:7b",
        )

        # THE INVARIANT: Both prepared context lists must be 100% IDENTICAL
        self.assertEqual(len(prepared_in_memory), len(prepared_from_disk))

        for idx, (msg_a, msg_b) in enumerate(zip(prepared_in_memory, prepared_from_disk)):
            self.assertEqual(
                msg_a.get("role"),
                msg_b.get("role"),
                f"Role mismatch at index {idx}",
            )
            self.assertEqual(
                msg_a.get("content"),
                msg_b.get("content"),
                f"Content mismatch at index {idx}",
            )

        # Verify that compaction correctly captured the modified files and subagent actions
        compacted_assistant = prepared_from_disk[2]
        self.assertIn("Applied design system tokens to src/index.css", compacted_assistant["content"])
        self.assertIn("server/index.js", compacted_assistant["content"])
        self.assertIn("src/App.jsx", compacted_assistant["content"])

    def test_multi_turn_restart_simulation(self):
        """
        Simulates:
        1. Turn 1 executes -> saved to disk
        2. App closes -> reopens from disk -> Turn 2 executes -> saved to disk
        3. App closes -> reopens from disk -> Turn 3 prepares context
        Verifies against continuous in-memory execution of the same 3 turns.
        """
        turn1_assistant_and_tool = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"type": "function", "function": {"name": "write_file", "arguments": {"file_path": "src/App.jsx"}}}],
            },
            {"role": "tool", "name": "write_file", "content": "Written"},
            {"role": "assistant", "content": "Created todo app."},
        ]

        turn2_assistant_and_tool = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"type": "function", "function": {"name": "edit_file", "arguments": {"file_path": "src/App.jsx"}}}],
            },
            {"role": "tool", "name": "edit_file", "content": "Edited"},
            {"role": "assistant", "content": "Added delete button."},
        ]

        # Case A: In-memory continuous
        in_memory_msgs = []
        ContextManager.prepare_messages("Create a todo app", self.system_prompt, in_memory_msgs)
        # Capture the actual Turn 1 user message produced by prepare_messages
        turn1_user_msg = in_memory_msgs[-1]  # the user message just added
        in_memory_msgs.extend(turn1_assistant_and_tool)
        ContextManager.prepare_messages("Add delete button", self.system_prompt, in_memory_msgs)
        turn2_user_msg = in_memory_msgs[-1]
        in_memory_msgs.extend(turn2_assistant_and_tool)
        in_mem_prepared_turn3 = ContextManager.prepare_messages(
            "Add filter tabs", self.system_prompt, in_memory_msgs
        )

        # Build the actual turn1/turn2 llm_messages as they would be saved to disk
        turn1_llm = [turn1_user_msg] + turn1_assistant_and_tool
        turn2_llm = [turn2_user_msg] + turn2_assistant_and_tool

        # Case B: Reopened across each turn
        ChatHistoryManager.save_turn(self.temp_dir, {
            "turn_id": "turn_1",
            "clean_user_prompt": "Create a todo app",
            "llm_messages": turn1_llm,
        })
        reopened_1 = ChatHistoryManager.get_llm_messages(self.temp_dir)
        ContextManager.prepare_messages("Add delete button", self.system_prompt, reopened_1)
        reopened_1.extend(turn2_assistant_and_tool)

        ChatHistoryManager.save_turn(self.temp_dir, {
            "turn_id": "turn_2",
            "clean_user_prompt": "Add delete button",
            "llm_messages": reopened_1[len(reopened_1) - len(turn2_llm):],
        })

        # Final reopen for Turn 3
        reopened_final = ChatHistoryManager.get_llm_messages(self.temp_dir)
        disk_prepared_turn3 = ContextManager.prepare_messages(
            "Add filter tabs", self.system_prompt, reopened_final
        )

        self.assertEqual(len(in_mem_prepared_turn3), len(disk_prepared_turn3))
        for m1, m2 in zip(in_mem_prepared_turn3, disk_prepared_turn3):
            self.assertEqual(m1["role"], m2["role"])
            self.assertEqual(m1["content"], m2["content"])

    def test_clear_history(self):
        ChatHistoryManager.save_turn(self.temp_dir, {
            "turn_id": "turn_1",
            "clean_user_prompt": "Hello",
            "llm_messages": [{"role": "user", "content": "Hello"}],
        })
        self.assertTrue(ChatHistoryManager.get_chat_file(self.temp_dir).exists())
        ChatHistoryManager.clear_history(self.temp_dir)
        self.assertFalse(ChatHistoryManager.get_chat_file(self.temp_dir).exists())
        self.assertEqual(len(ChatHistoryManager.get_llm_messages(self.temp_dir)), 0)
        self.assertEqual(len(ChatHistoryManager.get_ui_events(self.temp_dir)), 0)


    def test_incremental_and_interrupted_turn_persistence(self):
        """
        Verifies that saving turns incrementally with the same turn_id updates
        the turn in place rather than creating duplicate turns, and preserves
        in-flight progress when interrupted.
        """
        turn_id = "turn_stream_123"

        # 1. Early persistence: initial prompt registered
        ChatHistoryManager.save_turn(self.temp_dir, {
            "turn_id": turn_id,
            "status": "in_progress",
            "clean_user_prompt": "Build me a notes app",
            "ui_events": [{"type": "user", "content": "Build me a notes app"}],
            "llm_messages": [{"role": "user", "content": "Build me a notes app"}],
        })

        history1 = ChatHistoryManager.load_history(self.temp_dir)
        self.assertEqual(len(history1["turns"]), 1)
        self.assertEqual(history1["turns"][0]["status"], "in_progress")

        # 2. Incremental update after tool execution
        ChatHistoryManager.save_turn(self.temp_dir, {
            "turn_id": turn_id,
            "status": "in_progress",
            "clean_user_prompt": "Build me a notes app",
            "ui_events": [
                {"type": "user", "content": "Build me a notes app"},
                {"type": "tool_call", "name": "view_bulk", "arguments": {"files": ["src/App.jsx"]}},
                {"type": "tool_result", "name": "view_bulk", "result": "content"},
            ],
            "llm_messages": [
                {"role": "user", "content": "Build me a notes app"},
                {"role": "assistant", "content": "", "tool_calls": [{"type": "function", "function": {"name": "view_bulk"}}]},
                {"role": "tool", "name": "view_bulk", "content": "content"},
            ],
        })

        # Must NOT create a second turn; must update turn_0 in-place
        history2 = ChatHistoryManager.load_history(self.temp_dir)
        self.assertEqual(len(history2["turns"]), 1)
        self.assertEqual(len(history2["turns"][0]["ui_events"]), 3)

        # 3. Interrupted turn (e.g. user closes app)
        ChatHistoryManager.save_turn(self.temp_dir, {
            "turn_id": turn_id,
            "status": "interrupted",
            "clean_user_prompt": "Build me a notes app",
            "ui_events": [
                {"type": "user", "content": "Build me a notes app"},
                {"type": "tool_call", "name": "view_bulk", "arguments": {"files": ["src/App.jsx"]}},
                {"type": "tool_result", "name": "view_bulk", "result": "content"},
                {"type": "status", "content": "Stopped."},
            ],
            "llm_messages": [
                {"role": "user", "content": "Build me a notes app"},
                {"role": "assistant", "content": "", "tool_calls": [{"type": "function", "function": {"name": "view_bulk"}}]},
                {"role": "tool", "name": "view_bulk", "content": "content"},
            ],
        })

        history3 = ChatHistoryManager.load_history(self.temp_dir)
        self.assertEqual(len(history3["turns"]), 1)
        self.assertEqual(history3["turns"][0]["status"], "interrupted")

        # When rehydrated, ui_events and llm_messages are fully available
        ui_events = ChatHistoryManager.get_ui_events(self.temp_dir)
        self.assertEqual(len(ui_events), 4)
        llm_messages = ChatHistoryManager.get_llm_messages(self.temp_dir)
        self.assertEqual(len(llm_messages), 3)


class TestTokenPersistenceInChatHistory(unittest.IsolatedAsyncioTestCase):
    """
    Verifies that conversational token events from the agent are properly saved
    in chat history alongside tools, tool results, and terminal tools.
    """

    async def test_conversational_tokens_saved_alongside_tool_calls(self):
        from unittest.mock import MagicMock, AsyncMock, patch
        from plugins.coding_harness import CodingHarness

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            harness = CodingHarness(model_name="qwen2.5-coder:7b")

            mock_registry = MagicMock()
            mock_registry.sandbox_path = project_path
            mock_registry.get_tools.return_value = {
                "write_file": MagicMock(return_value="File written successfully")
            }
            mock_registry.get_dev_server_info.return_value = None

            mock_project = MagicMock()
            mock_project.path = project_path

            context = {
                "registry": mock_registry,
                "project": mock_project,
                "messages": [],
                "model": "qwen2.5-coder:7b",
            }

            # Iteration 1: Model speaks text AND calls a tool
            mock_chunk_1 = MagicMock()
            mock_chunk_1.message.thinking = None
            mock_chunk_1.message.content = "I will write the component now."
            mock_tool_call = MagicMock()
            mock_tool_call.function.name = "write_file"
            mock_tool_call.function.arguments = {"file_path": "src/App.jsx", "content": "export default () => <div>App</div>;"}
            mock_chunk_1.message.tool_calls = [mock_tool_call]

            # Iteration 2: Model finishes with text and no tools
            mock_chunk_2 = MagicMock()
            mock_chunk_2.message.thinking = None
            mock_chunk_2.message.tool_calls = None
            mock_chunk_2.message.content = "Component created successfully!"

            async def mock_stream_1():
                yield mock_chunk_1

            async def mock_stream_2():
                yield mock_chunk_2

            with patch("ollama.AsyncClient") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.chat = AsyncMock(side_effect=[mock_stream_1(), mock_stream_2()])
                mock_client_cls.return_value = mock_client

                events = []
                async for evt in harness.process_prompt("Create App.jsx", context):
                    events.append(evt)

                # Load history from disk
                history = ChatHistoryManager.load_history(project_path)
                self.assertEqual(len(history["turns"]), 1)
                turn = history["turns"][0]
                ui_events = turn["ui_events"]

                # Extract token events
                token_events = [e for e in ui_events if e.get("type") == "token"]
                self.assertEqual(len(token_events), 2)
                self.assertEqual(token_events[0]["content"], "I will write the component now.")
                self.assertEqual(token_events[1]["content"], "Component created successfully!")

                # Verify chronological ordering: token before tool_call in iteration 1
                token_idx = next(i for i, e in enumerate(ui_events) if e.get("type") == "token")
                tool_call_idx = next(i for i, e in enumerate(ui_events) if e.get("type") == "tool_call")
                self.assertLess(token_idx, tool_call_idx)

                # Verify get_ui_events returns tokens intact
                rehydrated = ChatHistoryManager.get_ui_events(project_path)
                rehydrated_tokens = [e for e in rehydrated if e.get("type") == "token"]
                self.assertEqual(len(rehydrated_tokens), 2)

    async def test_finish_tool_summary_saved_as_token_when_content_empty(self):
        from unittest.mock import MagicMock, AsyncMock, patch
        from plugins.coding_harness import CodingHarness

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            harness = CodingHarness(model_name="qwen2.5-coder:7b")

            mock_registry = MagicMock()
            mock_registry.sandbox_path = project_path
            mock_registry.get_tools.return_value = {
                "finish": MagicMock(return_value="Task completed successfully.")
            }
            mock_registry.get_dev_server_info.return_value = None

            mock_project = MagicMock()
            mock_project.path = project_path

            context = {
                "registry": mock_registry,
                "project": mock_project,
                "messages": [],
                "model": "qwen2.5-coder:7b",
            }

            # Model calls finish with empty content (common for native tool models)
            mock_chunk = MagicMock()
            mock_chunk.message.thinking = None
            mock_chunk.message.content = ""
            mock_finish_call = MagicMock()
            mock_finish_call.function.name = "finish"
            mock_finish_call.function.arguments = {"summary": "Built counter app with decrement and reset buttons."}
            mock_chunk.message.tool_calls = [mock_finish_call]

            async def mock_stream():
                yield mock_chunk

            with patch("ollama.AsyncClient") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.chat = AsyncMock(return_value=mock_stream())
                mock_client_cls.return_value = mock_client

                events = []
                async for evt in harness.process_prompt("Build counter", context):
                    events.append(evt)

                # Check that a token event was yielded and persisted
                token_events_yielded = [e for e in events if e.get("type") == "token"]
                self.assertEqual(len(token_events_yielded), 1)
                self.assertIn("Built counter app", token_events_yielded[0]["content"])

                # Check chat history on disk
                history = ChatHistoryManager.load_history(project_path)
                ui_events = history["turns"][0]["ui_events"]
                saved_tokens = [e for e in ui_events if e.get("type") == "token"]
                self.assertEqual(len(saved_tokens), 1)
                self.assertEqual(saved_tokens[0]["content"], "Built counter app with decrement and reset buttons.")


if __name__ == "__main__":
    unittest.main()

