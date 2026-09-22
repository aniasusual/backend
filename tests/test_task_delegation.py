"""
Unit tests for Phase 3 Delegation Layer:
- Parameter validation & repair (single & batch)
- Preflight policy resolution (recursion depth, blockedAgent self-spawn guard, spawns whitelist)
- Git Worktree isolation (creation, diff capture, patch apply, cleanup)
- TaskTool execution (single and batch fan-out with mock Ollama client)
"""

import unittest
import subprocess
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from task.types import TaskItem
from task.tool import repair_task_params, validate_task_params, TaskTool
from task.structured_subagent import resolve_effective_subagent_policy, StructuredSubagentError
from task.worktree import (
    is_git_repo,
    prepare_isolation_worktree,
    capture_worktree_patch,
    apply_patch_to_root,
    cleanup_isolation_worktree,
)


class TestTaskValidationAndRepair(unittest.TestCase):
    """Test parameter validation and repair for single and batch calls."""

    def test_single_task_validation(self):
        # Valid single call
        err = validate_task_params({"agent": "scout", "task": "Search code"}, batch_enabled=False)
        self.assertIsNone(err)

        # Missing task
        err = validate_task_params({"agent": "scout"}, batch_enabled=False)
        self.assertIn("Missing `task`", err)

    def test_batch_task_validation(self):
        # Valid batch
        batch = {
            "context": "Shared objective",
            "tasks": [
                {"name": "t1", "agent": "scout", "task": "Scan"},
                {"name": "t2", "agent": "reviewer", "task": "Review"},
            ],
        }
        err = validate_task_params(batch, batch_enabled=True)
        self.assertIsNone(err)

        # Missing context
        batch_no_ctx = {"tasks": [{"agent": "scout", "task": "Scan"}]}
        err = validate_task_params(batch_no_ctx, batch_enabled=True)
        self.assertIn("Missing `context`", err)

        # Duplicate task names
        batch_dup = {
            "context": "Context",
            "tasks": [
                {"name": "WorkerA", "task": "Do 1"},
                {"name": "workera", "task": "Do 2"},
            ],
        }
        err = validate_task_params(batch_dup, batch_enabled=True)
        self.assertIn("Duplicate task name", err)

    def test_repair_task_params_schemas_and_tools(self):
        """Verify repair_task_params parses stringified output_schema and comma-separated tools."""
        raw = {
            "agent": "  scout  ",
            "task": "Scan",
            "output_schema": '{"type": "object"}',
            "tools": "read_file, grep_search",
        }
        repaired = repair_task_params(raw)
        self.assertEqual(repaired["agent"], "scout")
        self.assertEqual(repaired["output_schema"], {"type": "object"})
        self.assertEqual(repaired["tools"], ["read_file", "grep_search"])

        # Test in batch items
        batch_raw = {
            "context": "Goal",
            "tasks": [
                {"task": "T1", "tools": "read_file, write_file", "outputSchema": '{"type": "string"}'}
            ],
        }
        batch_repaired = repair_task_params(batch_raw)
        self.assertEqual(batch_repaired["tasks"][0]["tools"], ["read_file", "write_file"])
        self.assertEqual(batch_repaired["tasks"][0]["outputSchema"], {"type": "string"})
    def test_repair_task_params(self):
        repaired = repair_task_params("Direct string prompt")
        self.assertEqual(repaired["task"], "Direct string prompt")

        repaired_json = repair_task_params({"tasks": '[{"task": "json_parsed"}]'})
        self.assertIsInstance(repaired_json["tasks"], list)


class TestPolicyResolution(unittest.TestCase):
    """Test preflight checks: recursion depth, blockedAgent, spawns permission."""

    def test_unknown_agent_rejected(self):
        with self.assertRaises(StructuredSubagentError) as ctx:
            resolve_effective_subagent_policy("non_existent_specialist", project_root=None)
        self.assertIn("Unknown agent", str(ctx.exception))

    def test_recursion_depth_ceiling(self):
        with self.assertRaises(StructuredSubagentError) as ctx:
            resolve_effective_subagent_policy("scout", project_root=None, current_depth=2, max_depth=2)
        self.assertIn("maximum depth is 2", str(ctx.exception))

    def test_blocked_agent_self_spawn_guard(self):
        # A scout trying to spawn another scout
        with self.assertRaises(StructuredSubagentError) as ctx:
            resolve_effective_subagent_policy("scout", project_root=None, blocked_agent="scout")
        self.assertIn("Cannot spawn scout agent from within itself", str(ctx.exception))

        # A reviewer spawning a scout is permitted
        defn = resolve_effective_subagent_policy("scout", project_root=None, blocked_agent="reviewer")
        self.assertEqual(defn.name, "scout")

    def test_spawns_whitelist_restriction(self):
        # Parent permits only scout
        with self.assertRaises(StructuredSubagentError) as ctx:
            resolve_effective_subagent_policy("troubleshoot", project_root=None, parent_spawns="scout")
        self.assertIn("does not have permission to spawn 'troubleshoot'", str(ctx.exception))

        # Parent permits *
        defn = resolve_effective_subagent_policy("troubleshoot", project_root=None, parent_spawns="*")
        self.assertEqual(defn.name, "troubleshoot")

    def test_subagent_spawns_denied_when_no_spawns_granted(self):
        """Verify subagent at depth > 0 cannot spawn when parent has no spawns permission."""
        with self.assertRaises(StructuredSubagentError) as ctx:
            resolve_effective_subagent_policy(
                "scout",
                project_root=None,
                current_depth=1,
                parent_spawns=None,  # Parent subagent has no spawns permission
            )
        self.assertIn("No spawns permitted", str(ctx.exception))

    def test_blocked_agent_case_insensitive(self):
        """Verify blockedAgent self-spawn guard is case-insensitive and trims whitespace."""
        with self.assertRaises(StructuredSubagentError) as ctx:
            resolve_effective_subagent_policy(
                "scout",
                project_root=None,
                blocked_agent="  SCOUT  ",
            )
        self.assertIn("Cannot spawn   SCOUT   agent from within itself", str(ctx.exception))

class TestGitWorktreeIsolation(unittest.TestCase):
    """Test full Git worktree isolation lifecycle in a temporary repository."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="lowkey_test_git_")
        self.repo_dir = Path(self.temp_dir)

        # Initialize real git repository
        subprocess.run(["git", "init"], cwd=str(self.repo_dir), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "TestUser"], cwd=str(self.repo_dir), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(self.repo_dir), check=True, capture_output=True)

        # Initial commit
        (self.repo_dir / "README.md").write_text("# Test Repo\nInitial line\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=str(self.repo_dir), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(self.repo_dir), check=True, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_worktree_isolation_and_patch_merge(self):
        self.assertTrue(is_git_repo(self.repo_dir))

        agent_id = "agent_iso_1"
        wt_path, branch, err = prepare_isolation_worktree(self.repo_dir, agent_id)
        self.assertIsNone(err)
        self.assertIsNotNone(wt_path)
        self.assertTrue(wt_path.exists())

        # Subagent modifies file in the worktree
        wt_readme = wt_path / "README.md"
        wt_readme.write_text("# Test Repo\nInitial line\nAdded by subagent!\n", encoding="utf-8")

        # Capture patch
        patch, patch_err = capture_worktree_patch(wt_path)
        self.assertIsNone(patch_err)
        self.assertIn("+Added by subagent!", patch)

        # Verify main repo has NOT changed yet
        self.assertNotIn("Added by subagent!", (self.repo_dir / "README.md").read_text(encoding="utf-8"))

        # Apply patch to main repo
        applied, apply_err = apply_patch_to_root(self.repo_dir, patch)
        self.assertTrue(applied)
        self.assertIsNone(apply_err)

        # Verify main repo has now received the change
        self.assertIn("Added by subagent!", (self.repo_dir / "README.md").read_text(encoding="utf-8"))

        # Cleanup worktree
        cleanup_err = cleanup_isolation_worktree(self.repo_dir, wt_path, branch)
        self.assertIsNone(cleanup_err)
        self.assertFalse(wt_path.exists())

    def test_worktree_untracked_new_file_capture_and_merge(self):
        """Verify newly created (untracked) files in worktree are captured and merged to root."""
        agent_id = "new_file_worker"
        wt_path, branch, err = prepare_isolation_worktree(self.repo_dir, agent_id)
        self.assertIsNone(err)
        self.assertIsNotNone(wt_path)

        # Subagent creates a brand new file
        new_file = wt_path / "new_module.py"
        new_file.write_text("def run():\n    return 'success'\n", encoding="utf-8")

        # Capture patch
        patch, patch_err = capture_worktree_patch(wt_path)
        self.assertIsNone(patch_err)
        self.assertIn("new file mode", patch)
        self.assertIn("def run():", patch)

        # Apply patch to main repo
        applied, apply_err = apply_patch_to_root(self.repo_dir, patch)
        self.assertTrue(applied)
        self.assertIsNone(apply_err)

        # Verify root repo now has the new file with exact content
        root_new_file = self.repo_dir / "new_module.py"
        self.assertTrue(root_new_file.exists())
        self.assertIn("def run():", root_new_file.read_text(encoding="utf-8"))

        # Cleanup
        cleanup_err = cleanup_isolation_worktree(self.repo_dir, wt_path, branch)
        self.assertIsNone(cleanup_err)
        self.assertFalse(wt_path.exists())

    def test_prepare_isolation_worktree_sanitizes_branch_name(self):
        """Verify agent IDs with spaces and slashes are sanitized for branch names."""
        agent_id = "Task 1 / audit & fix"
        wt_path, branch, err = prepare_isolation_worktree(self.repo_dir, agent_id)
        self.assertIsNone(err)
        self.assertIsNotNone(wt_path)
        self.assertNotIn(" ", branch)
        self.assertNotIn("/", branch)
        self.assertNotIn("&", branch)
        cleanup_isolation_worktree(self.repo_dir, wt_path, branch)

    def test_worktree_tool_registry_proxy_operations(self):
        """Verify WorktreeToolRegistryProxy writes and reads relative to the worktree."""
        from task.worktree import WorktreeToolRegistryProxy

        base_registry = MagicMock()
        base_registry.get_tools.return_value = {}

        wt_dir = Path(tempfile.mkdtemp(prefix="proxy_test_"))
        try:
            proxy = WorktreeToolRegistryProxy(base_registry, wt_dir)
            tools = proxy.get_tools()

            # Write file through proxy
            write_res = tools["write_file"]("hello.txt", "world")
            self.assertIn("Successfully wrote", write_res)
            self.assertTrue((wt_dir / "hello.txt").exists())
            self.assertEqual((wt_dir / "hello.txt").read_text(encoding="utf-8"), "world")

            # Read file through proxy
            read_res = tools["read_file"]("hello.txt")
            self.assertIn("1: world", read_res)
        finally:
            shutil.rmtree(wt_dir, ignore_errors=True)


class TestTaskToolExecution(unittest.IsolatedAsyncioTestCase):
    """Test TaskTool dispatching single and batch items."""

    async def test_task_tool_single_execution(self):
        dummy_registry = MagicMock()
        dummy_registry.sandbox_path = Path("/tmp")
        dummy_registry.get_tools.return_value = {}

        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "message": {
                "content": "",
                "tool_calls": [
                    {"function": {"name": "yield", "arguments": {"data": {"summary": "Scouted successfully"}}}}
                ],
            },
        }

        task_tool = TaskTool(tool_registry=dummy_registry)
        response = await task_tool.execute(
            tool_call_id="call_1",
            raw_params={"agent": "scout", "task": "Explore API"},
            context={"project_root": Path("/tmp")},
            client=mock_client,
        )

        self.assertIn("Scouted successfully", response["content"][0]["text"])
        self.assertEqual(len(response["details"]["results"]), 1)
        self.assertEqual(response["details"]["results"][0]["agent"], "scout")
    async def test_task_tool_batch_execution(self):
        dummy_registry = MagicMock()
        dummy_registry.sandbox_path = Path("/tmp")
        dummy_registry.get_tools.return_value = {}

        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "message": {
                "content": "",
                "tool_calls": [
                    {"function": {"name": "yield", "arguments": {"data": {"done": True}}}}
                ],
            },
        }

        task_tool = TaskTool(tool_registry=dummy_registry)
        batch_params = {
            "context": "Shared migration goal",
            "tasks": [
                {"name": "scout_task", "agent": "scout", "task": "Audit paths"},
                {"name": "review_task", "agent": "reviewer", "task": "Review security"},
            ],
        }

        response = await task_tool.execute(
            tool_call_id="call_batch_1",
            raw_params=batch_params,
            context={"project_root": Path("/tmp")},
            client=mock_client,
        )

        self.assertEqual(len(response["details"]["results"]), 2)
        res_agents = [r["agent"] for r in response["details"]["results"]]
        self.assertIn("scout", res_agents)
        self.assertIn("reviewer", res_agents)


if __name__ == "__main__":
    unittest.main()
