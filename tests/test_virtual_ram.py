import json
import pytest
from pathlib import Path
from tools.file_tools import FileTools
from tools.registry import ToolRegistry
from tools.schemas import TOOL_SCHEMAS
from plugins.argument_normalizer import ToolArgumentNormalizer
from context.manager import ContextManager
from context.estimator import TokenEstimator
from context.config import ContextConfig


class TestVirtualRAMSuite:
    @pytest.fixture
    def setup_sandbox(self):
        import shutil
        from config.settings import PROJECTS_ROOT
        test_dir = PROJECTS_ROOT / "_test_virtual_ram"
        test_dir.mkdir(parents=True, exist_ok=True)
        registry = ToolRegistry(sandbox_dir=test_dir, model_name="qwen2.5-coder:14b")
        file_tools = registry.file_tools
        try:
            yield test_dir, file_tools, registry
        finally:
            if test_dir.exists():
                shutil.rmtree(test_dir, ignore_errors=True)

    def test_mount_and_list_files(self, setup_sandbox):
        tmp_path, file_tools, _ = setup_sandbox
        test_file = tmp_path / "app.py"
        test_file.write_text("import sys\nprint('Hello world!')\n")

        # Mount the file
        res = file_tools.mount_file("app.py")
        assert "into Virtual RAM" in res
        assert "app.py" in file_tools.mounted_virtual_ram
        assert "print('Hello world!')" in file_tools.mounted_virtual_ram["app.py"]

        # List mounted files
        list_res = file_tools.list_mounted_files()
        assert "app.py" in list_res
        assert "ACTIVE VIRTUAL RAM REGISTER" in list_res

    def test_unmount_and_close_file_alias(self, setup_sandbox):
        tmp_path, _, registry = setup_sandbox
        f1 = tmp_path / "service.ts"
        f1.write_text("export const api = () => {};\n")

        # Mount via registry
        mount_res = registry.mount_file("service.ts")
        assert "into Virtual RAM" in mount_res
        assert "service.ts" in registry.mounted_virtual_ram

        # Unmount via close_file alias
        close_res = registry.close_file("service.ts")
        assert "from Virtual RAM" in close_res
        assert "service.ts" not in registry.mounted_virtual_ram

        # Remount and unmount via unmount_file from tool functions map
        tools = registry.get_tools()
        tools["mount_file"]("service.ts")
        unmount_res = tools["unmount_file"]("service.ts")
        assert "from Virtual RAM" in unmount_res
        assert len(registry.mounted_virtual_ram) == 0

    def test_unmount_basename_fallback(self, setup_sandbox):
        tmp_path, file_tools, _ = setup_sandbox
        sub = tmp_path / "src"
        sub.mkdir()
        f = sub / "index.js"
        f.write_text("console.log('index');\n")

        file_tools.mount_file("src/index.js")
        assert "src/index.js" in file_tools.mounted_virtual_ram

        # Unmount using just basename
        res = file_tools.unmount_file("index.js")
        assert "from Virtual RAM" in res
        assert len(file_tools.mounted_virtual_ram) == 0


    def test_close_file_alias(self, setup_sandbox):
        tmp_path, file_tools, _ = setup_sandbox
        f = tmp_path / "helper.py"
        f.write_text("def helper(): pass\n")
        file_tools.mount_file("helper.py")
        assert "helper.py" in file_tools.mounted_virtual_ram

        res = file_tools.close_file("helper.py")
        assert "from Virtual RAM" in res
        assert "helper.py" not in file_tools.mounted_virtual_ram
    def test_ram_60_percent_budget_cap_enforcement(self, setup_sandbox):
        tmp_path, file_tools, _ = setup_sandbox
        file_tools.model_name = "qwen2.5-coder:7b"
        # 32768 * 0.60 = 19660 tokens limit.
        # Create a file exceeding the budget cap
        huge_file = tmp_path / "huge.txt"
        huge_content = "def function_large_sample_data_block():\n    pass\n" * 4000  # ~24,000+ tokens
        huge_file.write_text(huge_content)

        res = file_tools.mount_file("huge.txt")
        assert "Virtual RAM budget exceeded" in res
        assert "exceeding the 60% budget cap" in res
        assert "huge.txt" not in file_tools.mounted_virtual_ram

    def test_auto_sync_on_write_file(self, setup_sandbox):
        tmp_path, file_tools, _ = setup_sandbox
        target = tmp_path / "config.json"
        target.write_text('{"debug": false}')

        file_tools.mount_file("config.json")
        assert '"debug": false' in file_tools.mounted_virtual_ram["config.json"]

        # Write new content
        file_tools.write_file("config.json", '{"debug": true, "version": 2}')
        # Virtual RAM should immediately reflect the update without re-mounting
        assert '"debug": true' in file_tools.mounted_virtual_ram["config.json"]
        assert '"version": 2' in file_tools.mounted_virtual_ram["config.json"]

    def test_auto_sync_on_edit_file(self, setup_sandbox):
        tmp_path, file_tools, _ = setup_sandbox
        target = tmp_path / "server.py"
        target.write_text("PORT = 8000\nDEBUG = True\n")

        file_tools.mount_file("server.py")
        assert "PORT = 8000" in file_tools.mounted_virtual_ram["server.py"]

        # Edit the file
        file_tools.edit_file("server.py", "PORT = 8000", "PORT = 5001")
        # Virtual RAM should immediately reflect edit
        assert "PORT = 5001" in file_tools.mounted_virtual_ram["server.py"]
        assert "PORT = 8000" not in file_tools.mounted_virtual_ram["server.py"]

    def test_auto_sync_on_insert_text(self, setup_sandbox):
        tmp_path, file_tools, _ = setup_sandbox
        target = tmp_path / "todo.txt"
        target.write_text("Line 1\nLine 2\n")

        file_tools.mount_file("todo.txt")
        file_tools.insert_text("todo.txt", 2, "Inserted Line\n")

        assert "Inserted Line" in file_tools.mounted_virtual_ram["todo.txt"]

    def test_context_manager_format_virtual_ram_block(self):
        mounted_ram = {
            "src/App.tsx": "function App() { return <div>App</div>; }",
            "src/index.css": "body { margin: 0; }",
        }
        block = ContextManager.format_virtual_ram_block(mounted_ram)
        assert ContextManager.RAM_HEADER in block
        assert ContextManager.RAM_FOOTER in block
        assert "--- FILE: src/App.tsx (1 lines) ---" in block
        assert "--- FILE: src/index.css (1 lines) ---" in block
        assert "function App() { return <div>App</div>; }" in block

    def test_context_manager_prepare_messages_injects_ram(self):
        mounted_ram = {
            "main.py": "print('live RAM state')",
        }
        messages = ContextManager.prepare_messages(
            user_prompt="Add feature",
            system_prompt="You are Lowkey.",
            existing_messages=[],
            mounted_virtual_ram=mounted_ram,
        )
        assert len(messages) >= 2
        sys_msg = messages[0]["content"]
        assert ContextManager.RAM_HEADER in sys_msg
        assert "main.py" in sys_msg
        assert "print('live RAM state')" in sys_msg

    def test_context_manager_sync_virtual_ram_block_dynamic_update_and_removal(self):
        messages = [{"role": "system", "content": "You are Lowkey assistant."}]

        # 1. Mount file dynamically
        ContextManager.sync_virtual_ram_block(messages, {"test.py": "x = 10"})
        assert ContextManager.RAM_HEADER in messages[0]["content"]
        assert "test.py" in messages[0]["content"]
        assert "x = 10" in messages[0]["content"]

        # 2. Update mounted file
        ContextManager.sync_virtual_ram_block(messages, {"test.py": "x = 20", "other.py": "y = 30"})
        assert "x = 20" in messages[0]["content"]
        assert "other.py" in messages[0]["content"]
        assert "x = 10" not in messages[0]["content"]

        # 3. Unmount all files
        ContextManager.sync_virtual_ram_block(messages, {})
        assert ContextManager.RAM_HEADER not in messages[0]["content"]
        assert messages[0]["content"] == "You are Lowkey assistant."

    def test_token_estimator_virtual_ram_accounting(self):
        mounted_ram = {
            "file1.py": "x = 1\n" * 100,
            "file2.py": "y = 2\n" * 200,
        }
        ram_tokens = TokenEstimator.estimate_virtual_ram(mounted_ram)
        assert ram_tokens > 100

        messages = [
            {"role": "system", "content": "You are Lowkey."},
            {"role": "user", "content": "Hello"},
        ]
        # estimate_total when ram is not in messages
        total_with_ram = TokenEstimator.estimate_total(messages, virtual_ram=mounted_ram)
        total_without_ram = TokenEstimator.estimate_total(messages)
        assert total_with_ram == total_without_ram + ram_tokens

        # estimate_total when ram is already inside messages[0] should not double count
        messages[0]["content"] += f"\n\n{ContextManager.RAM_HEADER}\n..."
        total_already_rendered = TokenEstimator.estimate_total(messages, virtual_ram=mounted_ram)
        # Should not add extra ram_tokens
        assert total_already_rendered < total_with_ram + ram_tokens

    def test_argument_normalizer_for_virtual_ram_tools(self):
        res1 = ToolArgumentNormalizer.normalize("mount_file", {"path": "src/App.tsx"})
        assert res1 == {"file_path": "src/App.tsx"}

        res2 = ToolArgumentNormalizer.normalize("unmount_file", {"file": "src/App.tsx"})
        assert res2 == {"file_path": "src/App.tsx"}

        res3 = ToolArgumentNormalizer.normalize("close_file", {"target_file": "src/App.tsx"})
        assert res3 == {"file_path": "src/App.tsx"}

    def test_tool_schemas_registered(self):
        all_schemas = list(TOOL_SCHEMAS.values() if isinstance(TOOL_SCHEMAS, dict) else TOOL_SCHEMAS)
        schema_names = [s["function"]["name"] for s in all_schemas]
        assert "mount_file" in schema_names
        assert "unmount_file" in schema_names
        assert "list_mounted_files" in schema_names

    def test_ram_budget_cap_scales_with_model_context_window(self, setup_sandbox):
        tmp_path, file_tools, _ = setup_sandbox
        target = tmp_path / "medium.txt"
        # ~21,000 tokens: exceeds 7B cap (19,660 tokens), but well within DeepSeek cap (78,643 tokens)
        target.write_text("line of sample data in file\n" * 3500)

        # 1. Rejected on 7B (32k context window)
        file_tools.model_name = "qwen2.5-coder:7b"
        res_7b = file_tools.mount_file("medium.txt")
        assert "Virtual RAM budget exceeded" in res_7b
        assert "medium.txt" not in file_tools.mounted_virtual_ram

        # 2. Accepted on DeepSeek 16B (128k context window)
        file_tools.model_name = "deepseek-coder-v2:16b"
        res_deepseek = file_tools.mount_file("medium.txt")
        assert "Successfully mounted 'medium.txt' into Virtual RAM" in res_deepseek
        assert "medium.txt" in file_tools.mounted_virtual_ram

    def test_ram_remount_updates_tokens_without_double_counting(self, setup_sandbox):
        tmp_path, file_tools, _ = setup_sandbox
        target = tmp_path / "evolving.py"
        target.write_text("x = 1\n" * 100)
        file_tools.model_name = "qwen2.5-coder:14b"

        # Initial mount
        file_tools.mount_file("evolving.py")
        initial_tokens = sum(
            TokenEstimator.estimate_text(f"--- FILE: {p} ---\n{c}\n")
            for p, c in file_tools.mounted_virtual_ram.items()
        )

        # Update on disk and remount
        target.write_text("x = 1\n" * 200)
        file_tools.mount_file("evolving.py")
        updated_tokens = sum(
            TokenEstimator.estimate_text(f"--- FILE: {p} ---\n{c}\n")
            for p, c in file_tools.mounted_virtual_ram.items()
        )
        # Must be roughly 2x initial, NOT 3x (which would happen if old wasn't subtracted)
        assert updated_tokens > initial_tokens
        assert updated_tokens < initial_tokens * 2.5

    def test_sync_virtual_ram_block_preserves_surrounding_system_prompt_and_handles_inner_dividers(self):
        initial_sys = (
            "Base System Prompt.\n\n"
            "## Repository Directives & Guidelines (.agentrules)\n"
            "Rule 1: Strict coding rules.\n\n"
            "=============================================================================\n"
            "[ACTIVE APPLICATION RUNTIME & PREVIEW ENVIRONMENT]\n"
            "=============================================================================\n"
            "Frontend URL: http://localhost:5173"
        )
        messages = [{"role": "system", "content": initial_sys}]

        # File contains inner divider line matching =============================================================================
        file_with_divider = (
            "// File with divider\n"
            "=============================================================================\n"
            "// More code after divider\n"
        )

        # 1. Mount file
        ContextManager.sync_virtual_ram_block(messages, {"divider_file.js": file_with_divider})
        sys_content = messages[0]["content"]
        assert ContextManager.RAM_HEADER in sys_content
        assert ContextManager.RAM_FOOTER in sys_content
        assert "Rule 1: Strict coding rules." in sys_content
        assert "Frontend URL: http://localhost:5173" in sys_content
        assert "divider_file.js" in sys_content

        # 2. Update mounted file
        ContextManager.sync_virtual_ram_block(messages, {"divider_file.js": "console.log('updated');"})
        sys_content = messages[0]["content"]
        assert "console.log('updated');" in sys_content
        assert "Rule 1: Strict coding rules." in sys_content
        assert "Frontend URL: http://localhost:5173" in sys_content

        # 3. Unmount all files: must leave base directives and runtime preview environment intact
        ContextManager.sync_virtual_ram_block(messages, {})
        sys_content = messages[0]["content"]
        assert ContextManager.RAM_HEADER not in sys_content
        assert ContextManager.RAM_FOOTER not in sys_content
        assert "Base System Prompt." in sys_content
        assert "Rule 1: Strict coding rules." in sys_content
        assert "Frontend URL: http://localhost:5173" in sys_content

    def test_mount_unmount_handles_whitespace(self, setup_sandbox):
        tmp_path, file_tools, _ = setup_sandbox
        target = tmp_path / "whitespace.txt"
        target.write_text("content of whitespace file")

        # Mount with whitespace padding
        mount_res = file_tools.mount_file("   whitespace.txt   ")
        assert "Successfully mounted 'whitespace.txt'" in mount_res
        assert "whitespace.txt" in file_tools.mounted_virtual_ram

        # Unmount with whitespace padding
        unmount_res = file_tools.unmount_file("   whitespace.txt   ")
        assert "Successfully unmounted 'whitespace.txt'" in unmount_res
        assert "whitespace.txt" not in file_tools.mounted_virtual_ram

    def test_sync_unmounts_deleted_file(self, setup_sandbox):
        tmp_path, file_tools, _ = setup_sandbox
        target = tmp_path / "ephemeral.txt"
        target.write_text("will be deleted")

        file_tools.mount_file("ephemeral.txt")
        assert "ephemeral.txt" in file_tools.mounted_virtual_ram

        # Delete file on disk
        target.unlink()

        # Sync without content triggers disk re-read; file is missing -> cleanly auto-unmounts
        file_tools._sync_virtual_ram_on_change("ephemeral.txt")
        assert "ephemeral.txt" not in file_tools.mounted_virtual_ram

    def test_mount_file_validation_errors(self, setup_sandbox):
        tmp_path, file_tools, _ = setup_sandbox
        (tmp_path / "a_directory").mkdir()

        assert "Error: 'file_path' is required" in file_tools.mount_file("")
        assert "Error: Access denied" in file_tools.mount_file("../outside.txt")
        assert "Error: File not found" in file_tools.mount_file("nonexistent.txt")
        assert "is a directory. Only files can be mounted" in file_tools.mount_file("a_directory")

    def test_unmount_unmounted_file_error(self, setup_sandbox):
        tmp_path, file_tools, _ = setup_sandbox
        res = file_tools.unmount_file("not_mounted.py")
        assert "Error: File 'not_mounted.py' is not currently mounted in Virtual RAM" in res
        assert "Currently mounted files:" in res
