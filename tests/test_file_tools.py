import os
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.file_tools import FileTools, DEFAULT_MAX_READ_LINES
from tools.registry import ToolRegistry
from tools.schemas import TOOL_SCHEMAS
from plugins.argument_normalizer import ToolArgumentNormalizer


class TestFileToolsReadBounds(unittest.TestCase):
    """
    Exhaustive tests for ITEM-5: Safe Range Bounds on File Reading (read_file).
    Validates CP-102.1 compliance: 250-line maximum ceiling, pagination notice formatting,
    _last_read_file tracking, argument normalization, and error handling.
    """

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.file_tools = FileTools(
            sandbox_path=self.temp_dir,
            is_safe_path_fn=lambda p: not str(p).startswith("..") and not os.path.isabs(str(p)),
        )

    def tearDown(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_default_max_read_lines_constant(self):
        """Verify DEFAULT_MAX_READ_LINES is 250 as required by ITEM-5 specification."""
        self.assertEqual(DEFAULT_MAX_READ_LINES, 250)

    def test_read_file_small_file_no_clamp(self):
        """Files with <= 250 lines should return all lines without any continuation notice."""
        file_path = "small.txt"
        lines = [f"line {i}" for i in range(1, 51)]
        (self.temp_dir / file_path).write_text("\n".join(lines), encoding="utf-8")

        result = self.file_tools.read_file(file_path)
        self.assertIn("[small.txt (lines 1-50 of 50)]:", result)
        self.assertIn("   1 | line 1", result)
        self.assertIn("  50 | line 50", result)
        self.assertNotIn("to continue.", result)
        self.assertNotIn("shown. File has", result)

    def test_read_file_1000_lines_unbounded_clamped(self):
        """Reading a 1,000-line file without arguments returns exactly 250 lines + notice."""
        file_path = "large.txt"
        lines = [f"line content {i}" for i in range(1, 1001)]
        (self.temp_dir / file_path).write_text("\n".join(lines), encoding="utf-8")

        result = self.file_tools.read_file(file_path)
        self.assertIn("[large.txt (lines 1-250 of 1000)]:", result)
        self.assertIn("   1 | line content 1", result)
        self.assertIn(" 250 | line content 250", result)
        self.assertNotIn(" 251 | line content 251", result)

        expected_notice = "[Lines 1-250 shown. File has 1000 lines. Use read_file(start_line=251) to continue.]"
        self.assertIn(expected_notice, result)

    def test_read_file_continuation_pagination(self):
        """Calling read_file with start_line=251 yields the next 250-line window."""
        file_path = "large.txt"
        lines = [f"line content {i}" for i in range(1, 1001)]
        (self.temp_dir / file_path).write_text("\n".join(lines), encoding="utf-8")

        result = self.file_tools.read_file(file_path, start_line=251)
        self.assertIn("[large.txt (lines 251-500 of 1000)]:", result)
        self.assertIn(" 251 | line content 251", result)
        self.assertIn(" 500 | line content 500", result)
        self.assertNotIn(" 501 | line content 501", result)

        expected_notice = "[Lines 251-500 shown. File has 1000 lines. Use read_file(start_line=501) to continue.]"
        self.assertIn(expected_notice, result)

    def test_read_file_continuation_without_file_path(self):
        """Omitting file_path on subsequent call resolves via _last_read_file seamlessly."""
        file_path = "notes.txt"
        lines = [f"note {i}" for i in range(1, 601)]
        (self.temp_dir / file_path).write_text("\n".join(lines), encoding="utf-8")

        # Initial call sets _last_read_file
        res1 = self.file_tools.read_file(file_path)
        self.assertIn("[notes.txt (lines 1-250 of 600)]:", res1)

        # Continuation call omits file_path
        res2 = self.file_tools.read_file(start_line=251)
        self.assertIn("[notes.txt (lines 251-500 of 600)]:", res2)
        self.assertIn(" 251 | note 251", res2)
        self.assertIn(" 500 | note 500", res2)
        self.assertIn("[Lines 251-500 shown. File has 600 lines. Use read_file(start_line=501) to continue.]", res2)

    def test_read_file_final_chunk_no_notice(self):
        """Reading the final chunk of a file to EOF should not attach a continuation notice."""
        file_path = "large.txt"
        lines = [f"line content {i}" for i in range(1, 1001)]
        (self.temp_dir / file_path).write_text("\n".join(lines), encoding="utf-8")

        result = self.file_tools.read_file(file_path, start_line=900)
        self.assertIn("[large.txt (lines 900-1000 of 1000)]:", result)
        self.assertIn(" 900 | line content 900", result)
        self.assertIn("1000 | line content 1000", result)
        self.assertNotIn("to continue.", result)

    def test_read_file_explicit_bounded_range(self):
        """Explicit sub-range <= 250 lines returns exact range without continuation notice."""
        file_path = "large.txt"
        lines = [f"line content {i}" for i in range(1, 1001)]
        (self.temp_dir / file_path).write_text("\n".join(lines), encoding="utf-8")

        result = self.file_tools.read_file(file_path, start_line=10, end_line=30)
        self.assertIn("[large.txt (lines 10-30 of 1000)]:", result)
        self.assertIn("  10 | line content 10", result)
        self.assertIn("  30 | line content 30", result)
        self.assertNotIn("  31 | line content 31", result)
        self.assertNotIn("to continue.", result)

    def test_read_file_explicit_range_exceeding_max(self):
        """Explicit sub-range exceeding 250 lines is safely clamped to 250 lines with notice."""
        file_path = "large.txt"
        lines = [f"line content {i}" for i in range(1, 1001)]
        (self.temp_dir / file_path).write_text("\n".join(lines), encoding="utf-8")

        # Requesting 500 lines (lines 10 to 509)
        result = self.file_tools.read_file(file_path, start_line=10, end_line=509)
        self.assertIn("[large.txt (lines 10-259 of 1000)]:", result)
        self.assertIn("  10 | line content 10", result)
        self.assertIn(" 259 | line content 259", result)
        self.assertNotIn(" 260 | line content 260", result)

        expected_notice = "[Lines 10-259 shown. File has 1000 lines. Use read_file(start_line=260) to continue.]"
        self.assertIn(expected_notice, result)

    def test_read_file_empty_file(self):
        """Empty file should return empty notice without error."""
        file_path = "empty.txt"
        (self.temp_dir / file_path).write_text("", encoding="utf-8")

        result = self.file_tools.read_file(file_path)
        self.assertEqual(result, "[empty.txt is empty (0 lines)]")

    def test_read_file_start_line_exceeds_total(self):
        """start_line greater than total lines returns descriptive error."""
        file_path = "short.txt"
        (self.temp_dir / file_path).write_text("a\nb\nc\n", encoding="utf-8")

        result = self.file_tools.read_file(file_path, start_line=10)
        self.assertEqual(result, "Error: start_line 10 exceeds total lines (3) in short.txt")

    def test_read_file_handles_whitespace_and_string_floats(self):
        """read_file strips whitespace from file_path and parses string floats for line bounds."""
        file_path = "padded.txt"
        (self.temp_dir / file_path).write_text("alpha\nbeta\ngamma\ndelta\nepsilon\n", encoding="utf-8")

        # Path with leading/trailing whitespace
        res1 = self.file_tools.read_file("   padded.txt   ")
        self.assertIn("[padded.txt (lines 1-5 of 5)]:", res1)
        self.assertIn("   1 | alpha", res1)

        # String float line numbers (e.g. from LLMs that emit JSON numbers as floats)
        res2 = self.file_tools.read_file("padded.txt", start_line="2.0", end_line="4.0")
        self.assertIn("[padded.txt (lines 2-4 of 5)]:", res2)
        self.assertIn("   2 | beta", res2)
        self.assertIn("   4 | delta", res2)

    def test_read_file_missing_file_path_without_history(self):
        """Calling read_file without file_path when no prior file was read returns error."""
        result = self.file_tools.read_file()
        self.assertEqual(result, "Error: 'file_path' is required.")

    def test_read_file_security_and_nonexistent(self):
        """Test sandbox escape, missing file, and directory errors."""
        self.assertIn("Error: Access denied", self.file_tools.read_file("../outside.txt"))
        self.assertIn("Error: File not found", self.file_tools.read_file("nonexistent.txt"))

        (self.temp_dir / "subdir").mkdir()
        self.assertIn("is a directory. Use list_directory instead.", self.file_tools.read_file("subdir"))

    def test_registry_delegation(self):
        """Test ToolRegistry.read_file correctly delegates with clamping and optional args."""
        from config.settings import PROJECTS_ROOT
        test_project_dir = PROJECTS_ROOT / "_test_item5_read_bounds"
        test_project_dir.mkdir(parents=True, exist_ok=True)
        try:
            registry = ToolRegistry(sandbox_dir=test_project_dir)
            lines = [f"reg line {i}" for i in range(1, 400)]
            (test_project_dir / "reg_test.txt").write_text("\n".join(lines), encoding="utf-8")

            result = registry.read_file("reg_test.txt")
            self.assertIn("[reg_test.txt (lines 1-250 of 399)]:", result)
            self.assertIn("[Lines 1-250 shown. File has 399 lines. Use read_file(start_line=251) to continue.]", result)
        finally:
            if test_project_dir.exists():
                shutil.rmtree(test_project_dir)

    def test_argument_normalizer_read_file(self):
        """Verify ToolArgumentNormalizer coerces string integers and alias paths."""
        normalized = ToolArgumentNormalizer.normalize(
            "read_file",
            {"path": "sample.js", "start_line": "50", "end_line": "150"},
        )
        self.assertEqual(normalized["file_path"], "sample.js")
        self.assertEqual(normalized["start_line"], 50)
        self.assertEqual(normalized["end_line"], 150)

    def test_tool_schema_compliance(self):
        """Verify read_file schema in TOOL_SCHEMAS contains updated 250-line bounds description."""
        read_file_schema = next((s for s in TOOL_SCHEMAS if s["function"]["name"] == "read_file"), None)
        self.assertIsNotNone(read_file_schema)
        desc = read_file_schema["function"]["description"]
        self.assertIn("250 lines", desc)
        self.assertIn("pagination", desc)


class TestTopologyDiscovery(unittest.TestCase):
    """
    Exhaustive tests for ITEM-6: Topology Discovery Tool (locate_files_by_pattern).
    Validates CP-102.1 compliance: depth-limited visual tree exploration, pattern matching,
    noise filtering, argument normalization, and schema integrity.
    """

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.file_tools = FileTools(
            sandbox_path=self.temp_dir,
            is_safe_path_fn=lambda p: not str(p).startswith("..") and not os.path.isabs(str(p)),
        )
        # Create standard project topology
        (self.temp_dir / "server" / "routes").mkdir(parents=True, exist_ok=True)
        (self.temp_dir / "src" / "components").mkdir(parents=True, exist_ok=True)
        (self.temp_dir / "server" / "index.js").write_text("// server", encoding="utf-8")
        (self.temp_dir / "server" / "routes" / "api.js").write_text("// api", encoding="utf-8")
        (self.temp_dir / "src" / "App.jsx").write_text("// app", encoding="utf-8")
        (self.temp_dir / "src" / "index.css").write_text("/* css */", encoding="utf-8")
        (self.temp_dir / "src" / "components" / "Header.jsx").write_text("// header", encoding="utf-8")
        (self.temp_dir / "package.json").write_text("{}", encoding="utf-8")
        (self.temp_dir / "README.md").write_text("# Readme", encoding="utf-8")

    def tearDown(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_locate_files_default_tree(self):
        """Verify full hierarchical visual tree is returned up to max_depth=3."""
        result = self.file_tools.locate_files_by_pattern()
        self.assertIn("[Topology of '.' (max_depth=3, pattern='*')]:", result)
        self.assertIn("server/", result)
        self.assertIn("routes/", result)
        self.assertIn("api.js", result)
        self.assertIn("src/", result)
        self.assertIn("components/", result)
        self.assertIn("Header.jsx", result)
        self.assertIn("App.jsx", result)
        self.assertIn("package.json", result)
        self.assertIn("├── ", result)
        self.assertIn("└── ", result)

    def test_locate_files_depth_truncation(self):
        """Depth limitation at max_depth=1 shows immediate children only, omitting deep files."""
        result = self.file_tools.locate_files_by_pattern(max_depth=1)
        self.assertIn("[Topology of '.' (max_depth=1, pattern='*')]:", result)
        self.assertIn("server/", result)
        self.assertIn("src/", result)
        self.assertIn("package.json", result)
        # Deep files should NOT appear at depth 1
        self.assertNotIn("api.js", result)
        self.assertNotIn("Header.jsx", result)
        self.assertNotIn("App.jsx", result)

    def test_locate_files_pattern_filtering(self):
        """Pattern filtering (e.g. *.jsx) shows only matching files and prunes non-matching subtrees."""
        result = self.file_tools.locate_files_by_pattern(pattern="*.jsx")
        self.assertIn("[Topology of '.' (max_depth=3, pattern='*.jsx')]:", result)
        self.assertIn("src/", result)
        self.assertIn("App.jsx", result)
        self.assertIn("Header.jsx", result)
        # server/ has no .jsx files, so it must be pruned
        self.assertNotIn("server/", result)
        self.assertNotIn("index.js", result)
        self.assertNotIn("package.json", result)

    def test_locate_files_subdirectory_targeting(self):
        """Targeting a sub-folder roots the tree directly at that sub-folder."""
        result = self.file_tools.locate_files_by_pattern(directory="src")
        self.assertIn("[Topology of 'src' (max_depth=3, pattern='*')]:", result)
        self.assertIn("components/", result)
        self.assertIn("Header.jsx", result)
        self.assertIn("App.jsx", result)
        self.assertNotIn("server/", result)

    def test_locate_files_ignores_noise_directories(self):
        """Standard noise directories (node_modules, .git, venv, __pycache__) must be ignored."""
        (self.temp_dir / "node_modules" / "express").mkdir(parents=True, exist_ok=True)
        (self.temp_dir / "node_modules" / "express" / "index.js").write_text("// express", encoding="utf-8")
        (self.temp_dir / ".git" / "hooks").mkdir(parents=True, exist_ok=True)
        (self.temp_dir / ".git" / "config").write_text("config", encoding="utf-8")
        (self.temp_dir / "venv" / "lib").mkdir(parents=True, exist_ok=True)
        (self.temp_dir / "venv" / "pyvenv.cfg").write_text("cfg", encoding="utf-8")
        (self.temp_dir / "__pycache__").mkdir(parents=True, exist_ok=True)
        (self.temp_dir / "__pycache__" / "module.cpython-312.pyc").write_text("pyc", encoding="utf-8")

        result = self.file_tools.locate_files_by_pattern()
        self.assertNotIn("node_modules", result)
        self.assertNotIn(".git", result)
        self.assertNotIn("venv", result)
        self.assertNotIn("__pycache__", result)

    def test_locate_files_security_and_nonexistent(self):
        """Sandbox escape, missing directory, and file target checks."""
        self.assertIn("Error: Access denied", self.file_tools.locate_files_by_pattern(directory="../outside"))
        self.assertIn("Error: Directory not found", self.file_tools.locate_files_by_pattern(directory="nonexistent_folder"))
        self.assertIn("is a file, not a directory", self.file_tools.locate_files_by_pattern(directory="package.json"))

    def test_locate_files_empty_directory(self):
        """Empty directory or pattern with zero matches returns clear message."""
        empty_dir = self.temp_dir / "empty_dir"
        empty_dir.mkdir(parents=True, exist_ok=True)
        result = self.file_tools.locate_files_by_pattern(directory="empty_dir")
        self.assertIn("No matching files found.", result)

    def test_locate_files_registry_delegation(self):
        """ToolRegistry correctly delegates locate_files_by_pattern."""
        from config.settings import PROJECTS_ROOT
        test_project_dir = PROJECTS_ROOT / "_test_item6_topology"
        test_project_dir.mkdir(parents=True, exist_ok=True)
        try:
            (test_project_dir / "src").mkdir(parents=True, exist_ok=True)
            (test_project_dir / "src" / "index.js").write_text("// test", encoding="utf-8")
            registry = ToolRegistry(sandbox_dir=test_project_dir)
            result = registry.locate_files_by_pattern()
            self.assertIn("src/", result)
            self.assertIn("index.js", result)
        finally:
            if test_project_dir.exists():
                shutil.rmtree(test_project_dir)

    def test_locate_files_argument_normalizer(self):
        """ToolArgumentNormalizer maps path, dir, folder, depth, glob to canonical args."""
        norm = ToolArgumentNormalizer.normalize(
            "locate_files_by_pattern",
            {"dir": "src", "depth": "2", "glob": "*.jsx"},
        )
        self.assertEqual(norm["directory"], "src")
        self.assertEqual(norm["max_depth"], 2)
        self.assertEqual(norm["pattern"], "*.jsx")

    def test_locate_files_schema(self):
        """Verify locate_files_by_pattern is present in TOOL_SCHEMAS."""
        schema = next((s for s in TOOL_SCHEMAS if s["function"]["name"] == "locate_files_by_pattern"), None)
        self.assertIsNotNone(schema)
        self.assertIn("directory", schema["function"]["parameters"]["properties"])
        self.assertIn("max_depth", schema["function"]["parameters"]["properties"])
        self.assertIn("pattern", schema["function"]["parameters"]["properties"])


    def test_locate_files_trailing_slash_and_float_depth(self):
        """Verify trailing slash in directory does not create double slash, and float depth is handled."""
        res = self.file_tools.locate_files_by_pattern(directory="src/", max_depth="2.0")
        self.assertIn("[Topology of 'src/' (max_depth=2, pattern='*')]:\nsrc/", res)
        self.assertNotIn("src//", res)
        self.assertIn("components/", res)

    def test_locate_files_case_insensitive_pattern(self):
        """Verify pattern matching is case-insensitive (e.g. *.JSX matches .jsx)."""
        res = self.file_tools.locate_files_by_pattern(pattern="*.JSX")
        self.assertIn("App.jsx", res)
        self.assertIn("Header.jsx", res)

    def test_locate_files_depth_clamp_boundaries(self):
        """Verify max_depth values <= 0 clamp to 1, and values > 10 clamp to 10."""
        res_zero = self.file_tools.locate_files_by_pattern(max_depth=0)
        self.assertIn("max_depth=1", res_zero)

        res_neg = self.file_tools.locate_files_by_pattern(max_depth=-5)
        self.assertIn("max_depth=1", res_neg)

        res_large = self.file_tools.locate_files_by_pattern(max_depth=99)
        self.assertIn("max_depth=10", res_large)

    def test_locate_files_caps_at_max_items(self):
        """Verify topology tree caps at 200 items when directory contains many files."""
        big_dir = self.temp_dir / "big_dir"
        big_dir.mkdir(parents=True, exist_ok=True)
        for i in range(250):
            (big_dir / f"file_{i:03d}.txt").write_text("content", encoding="utf-8")

        res = self.file_tools.locate_files_by_pattern(directory="big_dir")
        self.assertIn("results capped at 200 items", res)

if __name__ == "__main__":
    unittest.main()
