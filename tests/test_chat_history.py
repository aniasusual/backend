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
        turn1_llm = [
            {"role": "user", "content": "Create a todo app\n\n[Instruction: ...]"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"type": "function", "function": {"name": "write_file", "arguments": {"file_path": "src/App.jsx"}}}],
            },
            {"role": "tool", "name": "write_file", "content": "Written"},
            {"role": "assistant", "content": "Created todo app."},
        ]

        turn2_llm = [
            {"role": "user", "content": "Add delete button\n\n[Instruction: ...]"},
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
        in_memory_msgs.extend(turn1_llm[1:])  # assistant and tool calls
        ContextManager.prepare_messages("Add delete button", self.system_prompt, in_memory_msgs)
        in_memory_msgs.extend(turn2_llm[1:])
        in_mem_prepared_turn3 = ContextManager.prepare_messages(
            "Add filter tabs", self.system_prompt, in_memory_msgs
        )

        # Case B: Reopened across each turn
        ChatHistoryManager.save_turn(self.temp_dir, {
            "turn_id": "turn_1",
            "clean_user_prompt": "Create a todo app",
            "llm_messages": turn1_llm,
        })
        reopened_1 = ChatHistoryManager.get_llm_messages(self.temp_dir)
        ContextManager.prepare_messages("Add delete button", self.system_prompt, reopened_1)
        reopened_1.extend(turn2_llm[1:])

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


if __name__ == "__main__":
    unittest.main()
