import unittest
from pathlib import Path
import tempfile
import shutil

from config.settings import PROJECTS_ROOT
from tools.linter_tools import LinterTools
from tools.registry import ToolRegistry
from plugins.argument_normalizer import ToolArgumentNormalizer
from plugins.coding_harness import CodingHarness


class TestLinterToolsRobustness(unittest.TestCase):
    def setUp(self):
        self.sandbox = PROJECTS_ROOT / "_test_linter_tools"
        self.sandbox.mkdir(parents=True, exist_ok=True)
        self.linter = LinterTools(
            sandbox_path=self.sandbox,
            is_safe_path_fn=lambda p: True
        )
        self.registry = ToolRegistry(sandbox_dir=self.sandbox)

    def tearDown(self):
        if self.sandbox.exists():
            shutil.rmtree(self.sandbox, ignore_errors=True)

    def test_lint_javascript_with_empty_items_kwarg(self):
        # The exact error the user encountered: unexpected keyword argument 'items'
        res = self.linter.lint_javascript(items=[])
        self.assertIn("No JavaScript/TypeScript files found", res)

    def test_lint_javascript_with_empty_files_kwarg(self):
        res = self.linter.lint_javascript(files=[])
        self.assertIn("No JavaScript/TypeScript files found", res)

    def test_lint_javascript_with_unexpected_kwargs(self):
        # Should gracefully absorb unexpected kwargs without raising TypeError
        res = self.linter.lint_javascript(items=[], unexpected_arg="foo", random_flag=True)
        self.assertIn("No JavaScript/TypeScript files found", res)

    def test_lint_javascript_with_items_list(self):
        js_file = self.sandbox / "sample.js"
        js_file.write_text("console.log('hello world');\n")

        res = self.linter.lint_javascript(items=["sample.js"])
        self.assertIn("No syntax errors found across 1 file", res)

    def test_lint_javascript_with_dict_items(self):
        js_file = self.sandbox / "sample.js"
        js_file.write_text("console.log('hello world');\n")

        res = self.linter.lint_javascript(items=[{"file_path": "sample.js"}])
        self.assertIn("No syntax errors found across 1 file", res)

    def test_registry_lint_javascript_with_items(self):
        res = self.registry.lint_javascript(items=[])
        self.assertIn("No JavaScript/TypeScript files found", res)

    def test_normalizer_lint_javascript_empty_items(self):
        # {"items": []} should normalize to {} so default file_path="." is used
        norm = ToolArgumentNormalizer.normalize("lint_javascript", {"items": []})
        self.assertNotIn("items", norm)
        self.assertEqual(norm, {})

    def test_normalizer_lint_javascript_list_items(self):
        # {"items": ["src/App.jsx"]} should normalize to {"file_path": "src/App.jsx"}
        norm = ToolArgumentNormalizer.normalize("lint_javascript", {"items": ["src/App.jsx"]})
        self.assertEqual(norm.get("file_path"), "src/App.jsx")
        self.assertNotIn("items", norm)

    def test_normalizer_lint_javascript_raw_empty_list(self):
        # When model passes raw [] to lint_javascript
        norm = ToolArgumentNormalizer.normalize("lint_javascript", [])
        self.assertNotIn("items", norm)
        self.assertEqual(norm, {})

    def test_coding_harness_run_tool_safely_filters_unknown_kwargs(self):
        # Tool with rigid signature (no **kwargs) should have unknown parameters stripped safely
        def rigid_tool(file_path: str = "."):
            return f"linted {file_path}"

        tool_map = {"lint_javascript": rigid_tool}
        result = CodingHarness._run_tool("lint_javascript", {"items": [], "file_path": "main.js"}, tool_map)
        self.assertEqual(result, "linted main.js")

        # When only {"items": []} is passed, rigid tool called with default file_path
        result_default = CodingHarness._run_tool("lint_javascript", {"items": []}, tool_map)
        self.assertEqual(result_default, "linted .")


if __name__ == "__main__":
    unittest.main()
