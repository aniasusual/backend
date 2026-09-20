import unittest
import shutil
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from config.settings import PROJECTS_ROOT
from subagents.runner import SubagentRunner
from subagents.troubleshoot_subagent import TroubleshootSubagent
from tools.registry import ToolRegistry
from config.agent_loader import AgentLoader


class TestSubagentRunner(unittest.TestCase):
    """Unit tests for the autonomous child-loop SubagentRunner."""

    def setUp(self):
        self.sandbox_path = PROJECTS_ROOT / f"_test_runner_{uuid.uuid4().hex[:8]}"
        self.sandbox_path.mkdir(parents=True, exist_ok=True)

        # Create dummy workspace files
        self.app_file = self.sandbox_path / "src" / "App.jsx"
        self.app_file.parent.mkdir(parents=True, exist_ok=True)
        self.app_file.write_text("import React from 'react';\nexport default function App() {\n  return <div>Hello</div>;\n}\n")

        self.registry = ToolRegistry(self.sandbox_path)

    def tearDown(self):
        shutil.rmtree(self.sandbox_path, ignore_errors=True)

    def test_scoped_tool_filtering(self):
        """Verify runner only scopes whitelisted tools in schema and map."""
        allowed = {"read_file", "grep_search"}
        runner = SubagentRunner(
            name="test_subagent",
            system_prompt="Test prompt",
            allowed_tools=allowed,
            tool_registry=self.registry,
        )

        scoped_schemas = runner._get_scoped_schemas()
        schema_names = {s["function"]["name"] for s in scoped_schemas}
        self.assertEqual(schema_names, allowed)

        scoped_tools = runner._get_scoped_tool_map()
        self.assertEqual(set(scoped_tools.keys()), allowed)

    def test_permission_denied_on_forbidden_tool(self):
        """Verify that attempting to call a non-whitelisted tool returns permission denied."""
        allowed = {"read_file"}
        runner = SubagentRunner(
            name="read_only_agent",
            system_prompt="Read only prompt",
            allowed_tools=allowed,
            tool_registry=self.registry,
        )

        # Mock Ollama chat to attempt calling write_file
        with patch("ollama.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client

            # Iteration 1: model attempts to call forbidden tool 'write_file'
            mock_client.chat.side_effect = [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "write_file",
                                    "arguments": {"file_path": "hacked.txt", "content": "bad"},
                                }
                            }
                        ],
                    }
                },
                # Iteration 2: model realizes it's denied and gives up
                {
                    "message": {
                        "content": "I apologize, I do not have permission to write files.",
                        "tool_calls": [],
                    }
                },
            ]

            result = runner.run("Please write a file.")
            self.assertIn("do not have permission to write files", result)
            # Ensure hacked.txt was NOT written
            self.assertFalse((self.sandbox_path / "hacked.txt").exists())

    def test_allowed_tool_execution(self):
        """Verify whitelisted tool is executed and result fed back to child loop."""
        allowed = {"read_file"}
        events = []
        runner = SubagentRunner(
            name="reader_agent",
            system_prompt="Reader prompt",
            allowed_tools=allowed,
            tool_registry=self.registry,
            event_callback=lambda evt: events.append(evt),
        )

        with patch("ollama.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client

            mock_client.chat.side_effect = [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "read_file",
                                    "arguments": {"file_path": "src/App.jsx"},
                                }
                            }
                        ],
                    }
                },
                {
                    "message": {
                        "content": "File contains standard React App component.",
                        "tool_calls": [],
                    }
                },
            ]

            result = runner.run("Inspect App.jsx")
            self.assertIn("File contains standard React App component", result)
            # Verify event telemetry was dispatched
            tool_events = [e for e in events if e.get("event") == "tool_executed"]
            self.assertTrue(len(tool_events) >= 1)
            self.assertEqual(tool_events[0]["tool"], "read_file")

    def test_runner_telemetry_debug_and_token_metrics(self):
        """Verify runner captures token metrics, debug payloads, and caches last_run_events."""
        allowed = {"read_file"}
        events = []
        runner = SubagentRunner(
            name="test_runner",
            system_prompt="Test system prompt",
            allowed_tools=allowed,
            tool_registry=self.registry,
            event_callback=lambda evt: events.append(evt),
        )

        with patch("ollama.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client

            mock_client.chat.return_value = {
                "message": {
                    "role": "assistant",
                    "content": "Done inspecting.",
                    "thinking": "Analyzed code cleanly.",
                    "tool_calls": [],
                },
                "prompt_eval_count": 120,
                "eval_count": 45,
                "total_duration": 150000000,
            }

            result = runner.run("Check files")
            self.assertEqual(result, "Done inspecting.")

            # Verify metrics
            self.assertEqual(runner.last_run_metrics["prompt_tokens"], 120)
            self.assertEqual(runner.last_run_metrics["completion_tokens"], 45)
            self.assertEqual(runner.last_run_metrics["total_tokens"], 165)
            self.assertGreater(len(runner.last_run_events), 0)

            # Verify debug payload in events
            finish_evt = next(e for e in runner.last_run_events if e.get("event") == "finish")
            self.assertIn("debug", finish_evt)
            self.assertEqual(finish_evt["debug"]["metrics"]["prompt_eval_count"], 120)
            self.assertEqual(finish_evt["debug"]["metrics"]["eval_count"], 45)


class TestTroubleshootSubagent(unittest.TestCase):
    """Unit tests for TroubleshootSubagent."""

    def setUp(self):
        self.sandbox_path = PROJECTS_ROOT / f"_test_troubleshoot_{uuid.uuid4().hex[:8]}"
        self.sandbox_path.mkdir(parents=True, exist_ok=True)

        self.app_file = self.sandbox_path / "src" / "App.jsx"
        self.app_file.parent.mkdir(parents=True, exist_ok=True)
        self.app_file.write_text("import React from 'react';\nexport default function App() {\n  return <div>{user.name}</div>;\n}\n")

        self.registry = ToolRegistry(self.sandbox_path)
        self.subagent = TroubleshootSubagent(
            sandbox_path=self.sandbox_path,
            tool_registry=self.registry,
        )

    def tearDown(self):
        shutil.rmtree(self.sandbox_path, ignore_errors=True)

    def test_read_only_tool_restriction(self):
        """Verify TroubleshootSubagent only allows read-only tools including glob_files and list_directory."""
        self.assertEqual(
            self.subagent.allowed_tools,
            {"read_file", "view_bulk", "grep_search", "lint_javascript", "glob_files", "list_directory"},
        )
        self.assertNotIn("write_file", self.subagent.allowed_tools)
        self.assertNotIn("edit_file", self.subagent.allowed_tools)
        self.assertNotIn("execute_command", self.subagent.allowed_tools)

    def test_deterministic_missing_dependency_prefilter(self):
        """Verify fast-path for missing npm dependency."""
        error = "Failed to resolve import 'lucide-react' from 'src/App.jsx'. Does the file exist?"
        result = self.subagent.diagnose_error(error)
        self.assertIn("Root Cause Analysis (RCA): Missing Dependency", result)
        self.assertIn("npm install lucide-react", result)

    def test_relative_import_disambiguation(self):
        """Verify local relative import is never diagnosed as npm package or npm install ."""
        error = "Failed to resolve import './components/Header' from 'src/App.jsx'. Does the file exist?"
        result = self.subagent.diagnose_error(error)
        self.assertIn("Root Cause Analysis (RCA): Missing Local File / Component", result)
        self.assertNotIn("npm install .", result)
        self.assertNotIn("Missing Dependency", result)

    def test_ansi_stripping_and_location_extraction(self):
        """Verify ANSI color codes are stripped and file location extracted correctly."""
        ansi_log = "\x1b[31m[vite] Internal server error\x1b[39m\n  at App (\x1b[36msrc/App.jsx:42:15\x1b[39m)"
        from subagents.troubleshoot import StackTraceParser
        loc = StackTraceParser.extract_file_location(ansi_log)
        self.assertEqual(loc, "src/App.jsx:42")

    def test_python_stack_trace_extraction(self):
        """Verify Python stack trace line extraction."""
        py_log = 'Traceback (most recent call last):\n  File "server/server.py", line 42, in get_users\nZeroDivisionError: division by zero'
        from subagents.troubleshoot import StackTraceParser
        loc = StackTraceParser.extract_file_location(py_log)
        self.assertEqual(loc, "server/server.py:42")

    def test_file_uri_and_arbitrary_folder_extraction(self):
        """Verify generalized path extraction supports file:// URIs and custom folders without hardcoding."""
        from subagents.troubleshoot import StackTraceParser
        esm_log = "Error: boom\n  at file:///Users/animesh/Desktop/work/projects/lowkey/backend/routes/api.js:88:12"
        loc = StackTraceParser.extract_file_location(esm_log)
        self.assertEqual(loc, "backend/routes/api.js:88")

    def test_deterministic_port_conflict_prefilter(self):
        """Verify fast-path for EADDRINUSE port collision."""
        error = "Error: listen EADDRINUSE: address already in use 0.0.0.0:3000"
        result = self.subagent.diagnose_error(error)
        self.assertIn("Root Cause Analysis (RCA): Port Conflict", result)
        self.assertIn("3000", result)

    def test_deterministic_cors_prefilter(self):
        """Verify fast-path for CORS security block."""
        error = "Access to XMLHttpRequest at 'http://localhost:3000/api' has been blocked by CORS policy"
        result = self.subagent.diagnose_error(error)
        self.assertIn("Root Cause Analysis (RCA): CORS Security Block", result)
        self.assertIn("cors", result)

    def test_autonomous_investigation_call(self):
        """Verify autonomous child runner is invoked for complex runtime errors."""
        error = "TypeError: Cannot read properties of undefined (reading 'name') at App (src/App.jsx:3:28)"

        with patch("subagents.troubleshoot_subagent.SubagentRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner_cls.return_value = mock_runner
            mock_runner.run.return_value = "### 🩺 Root Cause Analysis (RCA)\n- **Issue**: user object is undefined\n- **Root Cause**: missing initial state"

            result = self.subagent.diagnose_error(error)
            mock_runner.run.assert_called_once()
            self.assertIn("user object is undefined", result)

    def test_runner_failure_string_triggers_heuristic_fallback(self):
        """Verify runner error string (e.g. Subagent execution failed...) triggers fallback rather than raw error return."""
        error = "TypeError: Cannot read properties of undefined (reading 'name') at App (src/App.jsx:3:28)"

        with patch("subagents.troubleshoot_subagent.SubagentRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner_cls.return_value = mock_runner
            mock_runner.run.return_value = "Subagent execution failed due to model error: Connection refused to Ollama"

            result = self.subagent.diagnose_error(error)
            self.assertIn("Root Cause Analysis (RCA): Undefined Property Access", result)
            self.assertNotIn("Subagent execution failed", result)
            self.assertIn("?.name", result)




class TestToolStandardization(unittest.TestCase):
    """Verifies that tool registries, agent profiles, and parsers use strict canonical names without ghost aliases."""

    def setUp(self):
        self.sandbox_path = PROJECTS_ROOT / f"_test_tools_{uuid.uuid4().hex[:8]}"
        self.sandbox_path.mkdir(parents=True, exist_ok=True)
        self.registry = ToolRegistry(self.sandbox_path)

    def tearDown(self):
        shutil.rmtree(self.sandbox_path, ignore_errors=True)

    def test_no_ghost_aliases_in_registry(self):
        """Ensure deprecated ghost aliases are absent from the tool registry."""
        tools = self.registry.get_tools()
        forbidden_aliases = [
            "get_assets_tool",
            "design_agent",
            "troubleshoot_agent",
            "vision_agent",
            "test_ui",
            "search_replace",
        ]
        for alias in forbidden_aliases:
            self.assertNotIn(alias, tools, f"Ghost alias '{alias}' should not be present in tool registry.")

    def test_canonical_subagents_in_registry(self):
        """Ensure all subagents adhere strictly to the invoke_*_agent naming convention."""
        tools = self.registry.get_tools()
        expected_subagents = [
            "invoke_design_agent",
            "invoke_troubleshoot_agent",
            "invoke_vision_agent",
            "invoke_testing_agent",
            "invoke_code_reviewer_agent",
        ]
        for subagent in expected_subagents:
            self.assertIn(subagent, tools, f"Canonical subagent '{subagent}' missing from registry.")
            self.assertTrue(callable(tools[subagent]))

    def test_agent_profile_no_synthetic_aliases(self):
        """Verify AgentProfile.all_callable_tools does not generate redundant short-name aliases."""
        from config.agent_loader import AgentProfile
        profile = AgentProfile(
            id="test_profile",
            name="Test",
            tier=1,
            whitelisted_tools=["read_file", "get_assets"],
            enabled_subagents=["invoke_design_agent", "invoke_testing_agent", "invoke_code_reviewer_agent"],
        )
        tools = profile.all_callable_tools
        self.assertIn("invoke_design_agent", tools)
        self.assertIn("invoke_testing_agent", tools)
        self.assertIn("invoke_code_reviewer_agent", tools)
        self.assertNotIn("design_agent", tools)
        self.assertNotIn("testing_agent", tools)
        self.assertNotIn("code_reviewer_agent", tools)
        self.assertNotIn("test_ui", tools)

    def test_parser_known_tools_canonical(self):
        """Verify ToolCallParser.KNOWN_TOOLS has only canonical tool names."""
        from tools.parser import KNOWN_TOOLS
        self.assertIn("get_assets", KNOWN_TOOLS)
        self.assertNotIn("get_assets_tool", KNOWN_TOOLS)
        self.assertIn("invoke_testing_agent", KNOWN_TOOLS)
        self.assertIn("invoke_code_reviewer_agent", KNOWN_TOOLS)
        self.assertNotIn("test_ui", KNOWN_TOOLS)
        self.assertNotIn("design_agent", KNOWN_TOOLS)
    def test_subagent_model_synchronization(self):
        """Verify that all subagents inherit and synchronize with the active main agent model."""
        test_model = "deepseek-r1:14b"
        self.registry.set_model_name(test_model)

        self.assertEqual(self.registry.design_subagent.model_name, test_model)
        self.assertEqual(self.registry.troubleshoot_subagent.model_name, test_model)
        self.assertEqual(self.registry.vision_subagent.model_name, test_model)
        self.assertEqual(self.registry.ui_testing_subagent.model_name, test_model)
        self.assertEqual(self.registry.code_reviewer_subagent.model_name, test_model)

        # Also verify invoker methods maintain synchronization
        another_model = "claude-3-7-sonnet"
        self.registry.set_model_name(another_model)
        self.assertEqual(self.registry.design_subagent.model_name, another_model)
        self.assertEqual(self.registry.troubleshoot_subagent.model_name, another_model)
        self.assertEqual(self.registry.vision_subagent.model_name, another_model)
        self.assertEqual(self.registry.ui_testing_subagent.model_name, another_model)
        self.assertEqual(self.registry.code_reviewer_subagent.model_name, another_model)



class TestDesignSubagent(unittest.TestCase):
    """Unit tests for upgraded autonomous DesignSubagent."""

    def setUp(self):
        self.sandbox_path = PROJECTS_ROOT / f"_test_design_{uuid.uuid4().hex[:8]}"
        self.sandbox_path.mkdir(parents=True, exist_ok=True)
        self.registry = ToolRegistry(self.sandbox_path)
        from subagents.design_subagent import DesignSubagent
        self.subagent = DesignSubagent(
            sandbox_path=self.sandbox_path,
            tool_registry=self.registry,
        )

    def tearDown(self):
        shutil.rmtree(self.sandbox_path, ignore_errors=True)

    def test_allowed_tools(self):
        """Verify design subagent is scoped to write_file, get_assets, read_file, and view_bulk."""
        self.assertEqual(
            self.subagent.allowed_tools,
            {"write_file", "get_assets", "read_file", "view_bulk"},
        )
        self.assertNotIn("execute_command", self.subagent.allowed_tools)
        self.assertNotIn("edit_file", self.subagent.allowed_tools)

    def test_autonomous_design_runner_invocation(self):
        """Verify autonomous child runner is invoked and generates design blueprint."""
        with patch("subagents.design_subagent.SubagentRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner_cls.return_value = mock_runner
            mock_runner.run.return_value = "# 🎨 UI/UX Design System Blueprint\n**Aesthetic Direction**: Neon Cyberpunk\n"

            result = self.subagent.generate_layout_blueprint(
                problem_statement="Build a futuristic DJ audio mixer",
                app_type="audio_app",
            )
            mock_runner.run.assert_called_once()
            self.assertIn("Neon Cyberpunk", result)

            # Ensure baseline index.css was created on disk
            css_file = self.sandbox_path / "src" / "index.css"
            self.assertTrue(css_file.exists())
            self.assertIn("--primary", css_file.read_text())

    def test_heuristic_fallback_on_runner_error(self):
        """Verify graceful fallback synthesizing bespoke taste and topology when runner throws an error."""
        with patch("subagents.design_subagent.SubagentRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner_cls.return_value = mock_runner
            mock_runner.run.side_effect = RuntimeError("Ollama connection refused")

            result = self.subagent.generate_layout_blueprint(
                problem_statement="Crypto trading wealth tracker",
                app_type="fintech",
                theme_preference="warm terracotta",
            )
            self.assertIn("Warm Terracotta", result)
            css_file = self.sandbox_path / "src" / "index.css"
            self.assertTrue(css_file.exists())
            self.assertIn("--primary", css_file.read_text())

    def test_tailwind_directive_preservation(self):
        """Verify that Tailwind directives are never wiped out when generating design systems."""
        css_file = self.sandbox_path / "src" / "index.css"
        css_file.parent.mkdir(parents=True, exist_ok=True)
        css_file.write_text("@tailwind base;\n@tailwind components;\n@tailwind utilities;\n")

        with patch("subagents.design_subagent.SubagentRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner_cls.return_value = mock_runner
            mock_runner.run.side_effect = RuntimeError("Ollama connection refused")

            result = self.subagent.generate_layout_blueprint(
                problem_statement="E-commerce boutique shop",
                app_type="ecommerce",
            )

            # Check that file still has Tailwind directives
            content = css_file.read_text()
            self.assertIn("@tailwind base;", content)
            self.assertIn("@tailwind components;", content)
            self.assertIn("@tailwind utilities;", content)
            self.assertIn("@layer components", content)
            self.assertIn("--primary", content)

    def test_archetype_component_topology(self):
        """Verify dynamic archetype detection derives tailored components instead of generic StatsGrid."""
        from subagents.design.topology import detect_archetype

        chat_arch = detect_archetype("Team collaboration and direct messaging app", "messaging_chat")
        self.assertEqual(chat_arch["name"], "Messaging & Real-time Collaboration")
        comp_names = [c["name"] for c in chat_arch["components"]]
        self.assertIn("ChatStream.jsx", comp_names)
        self.assertIn("MessageInput.jsx", comp_names)
        self.assertNotIn("StatsGrid.jsx", comp_names)

        canvas_arch = detect_archetype("Vector graphics illustrator and drawing canvas", "canvas_tool")
        self.assertEqual(canvas_arch["name"], "Creative Studio & Interactive Canvas")
        comp_names = [c["name"] for c in canvas_arch["components"]]
        self.assertIn("ToolFloatingDock.jsx", comp_names)
        self.assertIn("InteractiveWorkspace.jsx", comp_names)
        self.assertNotIn("StatsGrid.jsx", comp_names)
class TestCodeReviewerSubagent(unittest.TestCase):
    """Unit tests for CodeReviewerSubagent."""

    def setUp(self):
        self.sandbox_path = PROJECTS_ROOT / f"_test_reviewer_{uuid.uuid4().hex[:8]}"
        self.sandbox_path.mkdir(parents=True, exist_ok=True)
        self.registry = ToolRegistry(self.sandbox_path)

        # Create a sample file with security and performance smells
        self.vuln_file = self.sandbox_path / "src" / "api.js"
        self.vuln_file.parent.mkdir(parents=True, exist_ok=True)
        self.vuln_file.write_text("""
const apiKey = "sk-1234567890abcdef12345678";
app.get("/search", (req, res) => {
    const q = "SELECT * FROM users WHERE name = '" + req.query.name + "'";
    eval(req.query.cmd);
    res.send(q);
});
""")
        from subagents.code_reviewer_subagent import CodeReviewerSubagent
        self.subagent = CodeReviewerSubagent(
            sandbox_path=self.sandbox_path,
            tool_registry=self.registry,
        )

    def tearDown(self):
        shutil.rmtree(self.sandbox_path, ignore_errors=True)

    def test_allowed_tools(self):
        """Verify code reviewer subagent is strictly scoped to read-only tools including glob_files."""
        self.assertEqual(
            self.subagent.allowed_tools,
            {"read_file", "view_bulk", "grep_search", "lint_javascript", "glob_files"},
        )
        self.assertNotIn("write_file", self.subagent.allowed_tools)
        self.assertNotIn("edit_file", self.subagent.allowed_tools)
        self.assertNotIn("execute_command", self.subagent.allowed_tools)

    def test_multi_file_discovery(self):
        """Verify multi-file discovery finds components in src/components and routes in server/routes."""
        from subagents.reviewer import StaticSecurityScanner
        comp_dir = self.sandbox_path / "src" / "components"
        comp_dir.mkdir(parents=True, exist_ok=True)
        (comp_dir / "Button.jsx").write_text("export function Button() { return <button>Click</button>; }")

        routes_dir = self.sandbox_path / "server" / "routes"
        routes_dir.mkdir(parents=True, exist_ok=True)
        (routes_dir / "users.js").write_text("router.get('/', (req, res) => res.json([]));")

        discovered = StaticSecurityScanner.discover_code_files(self.sandbox_path)
        self.assertIn("src/components/Button.jsx", discovered)
        self.assertIn("server/routes/users.js", discovered)
        self.assertIn("src/api.js", discovered)

    def test_autonomous_review_runner_invocation(self):
        """Verify autonomous child runner is invoked with target files and focus areas."""
        with patch("subagents.code_reviewer_subagent.SubagentRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner_cls.return_value = mock_runner
            mock_runner.run.return_value = "### 🧐 Code Review & Security Audit\n**Overall Code Quality Score**: 85/100\n- **Security**: SQL Injection detected\n"

            result = self.subagent.review_code(
                target_files=["src/api.js"],
                focus_areas=["security", "correctness"],
            )
            mock_runner.run.assert_called_once()
            self.assertIn("SQL Injection detected", result)

    def test_runner_failure_string_triggers_heuristic_fallback(self):
        """Verify runner error string (e.g. Subagent execution failed...) triggers fallback rather than raw error return."""
        with patch("subagents.code_reviewer_subagent.SubagentRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner_cls.return_value = mock_runner
            mock_runner.run.return_value = "Subagent execution failed due to model error: Connection refused to Ollama"

            result = self.subagent.review_code(
                target_files=["src/api.js"],
                focus_areas=["security"],
            )
            self.assertIn("Code Review & Security Audit", result)
            self.assertNotIn("Subagent execution failed", result)
            self.assertIn("eval()", result)

    def test_template_literal_sql_injection_detection(self):
        """Verify StaticSecurityScanner catches ES6 template literal SQL injection."""
        sql_file = self.sandbox_path / "server" / "db.js"
        sql_file.parent.mkdir(parents=True, exist_ok=True)
        sql_file.write_text("""
app.get("/user/:id", async (req, res) => {
    try {
        const query = `SELECT * FROM accounts WHERE id = ${req.params.id}`;
        res.send(query);
    } catch (e) {
        res.status(500).send(e);
    }
});
""")
        from subagents.reviewer import StaticSecurityScanner
        findings, score = StaticSecurityScanner.scan(self.sandbox_path, ["server/db.js"])
        self.assertTrue(any("template literal interpolation" in f for f in findings))
        self.assertLess(score, 75)

    def test_heuristic_fallback_on_runner_error(self):
        """Verify deterministic heuristic fallback when runner throws an error."""
        with patch("subagents.code_reviewer_subagent.SubagentRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner_cls.return_value = mock_runner
            mock_runner.run.side_effect = RuntimeError("Model timeout")

            result = self.subagent.review_code(
                target_files=["src/api.js"],
                focus_areas=["security"],
            )
            self.assertIn("Code Review & Security Audit", result)
            self.assertIn("eval()", result)
            self.assertIn("SQL injection", result)
            self.assertIn("hardcoded API secret", result)

    def test_models_pydantic_serialization_and_markdown(self):
        """Verify typed Pydantic models for code reviewer findings and reports."""
        from subagents.reviewer.models import (
            FindingSeverity,
            FindingCategory,
            ReviewFinding,
            ReviewAuditReport,
        )

        finding = ReviewFinding(
            file_path="server/db.js",
            line_number=42,
            severity=FindingSeverity.CRITICAL,
            category=FindingCategory.SECURITY,
            title="SQL Injection",
            description="Unescaped template literal query parameter",
            code_snippet="SELECT * FROM users WHERE id = ${req.params.id}",
            suggested_replacement="db.query('SELECT * FROM users WHERE id = $1', [req.params.id])",
        )
        self.assertEqual(finding.line_number, 42)
        self.assertEqual(finding.severity, FindingSeverity.CRITICAL)

        report = ReviewAuditReport(
            findings=[finding],
            inspected_files=["server/db.js"],
        )
        report.recalculate()
        self.assertEqual(report.score, 75)
        self.assertEqual(report.status, "NEEDS_REVISION")
        self.assertFalse(report.approved)

        markdown = report.to_markdown()
        self.assertIn("server/db.js:42", markdown)
        self.assertIn("SQL Injection", markdown)
        self.assertIn("Recommended Fix", markdown)

        parsed_report = ReviewAuditReport.from_markdown(markdown, files=["server/db.js"])
        self.assertEqual(parsed_report.score, 75)
        self.assertFalse(parsed_report.approved)

    def test_scan_structured_exact_line_numbers(self):
        """Verify StaticSecurityScanner.scan_structured detects exact line numbers and code snippets."""
        from subagents.reviewer import StaticSecurityScanner
        target = self.sandbox_path / "server" / "api.js"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("""// Line 1
// Line 2
const secret_key = "abc123456789xyz";
// Line 4
eval("console.log(1)");
""")
        findings, score = StaticSecurityScanner.scan_structured(self.sandbox_path, ["server/api.js"])
        self.assertEqual(len(findings), 2)
        secret_finding = next((f for f in findings if "Secret" in f.title), None)
        eval_finding = next((f for f in findings if "eval" in f.title), None)

        self.assertIsNotNone(secret_finding)
        self.assertEqual(secret_finding.line_number, 3)
        self.assertIn("secret_key", secret_finding.code_snippet)

        self.assertIsNotNone(eval_finding)
        self.assertEqual(eval_finding.line_number, 5)
        self.assertIn("eval(", eval_finding.code_snippet)

    def test_preflight_leads_passed_to_runner(self):
        """Verify StaticSecurityScanner pre-flight leads are injected into SubagentRunner task prompt."""
        target = self.sandbox_path / "server" / "vulnerable.js"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('eval("danger()");\n')

        with patch("subagents.code_reviewer_subagent.SubagentRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner_cls.return_value = mock_runner
            mock_runner.run.return_value = "# 🧐 Code Review & Security Audit\n**Overall Code Quality Score**: **95/100**\n**Status**: **APPROVED**\n"

            self.subagent.review_code(target_files=["server/vulnerable.js"])
            mock_runner.run.assert_called_once()
            called_prompt = mock_runner.run.call_args[0][0]
            self.assertIn("PRE-FLIGHT STATIC SCANNER LEADS", called_prompt)
            self.assertIn("server/vulnerable.js:1", called_prompt)
            self.assertIn("Dangerous `eval()`", called_prompt)
            self.assertIsNotNone(self.subagent.last_report)
            self.assertEqual(self.subagent.last_report.score, 95)
            self.assertTrue(self.subagent.last_report.approved)

    def test_subagent_runner_fallback_message_formatting(self):
        """Verify text-fallback tool calls append tool responses as role 'user' without chat template crashes."""
        from subagents.runner import SubagentRunner
        runner = SubagentRunner(
            name="test_runner",
            system_prompt="Test system",
            allowed_tools={"read_file"},
            tool_registry=self.registry,
        )

        with patch("ollama.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            # Turn 1: model returns markdown fallback JSON for read_file
            # Turn 2: model returns final conclusion
            mock_client.chat.side_effect = [
                {
                    "message": {
                        "content": '```json\n{"name": "read_file", "arguments": {"file_path": "src/api.js"}}\n```',
                        "tool_calls": [],
                    },
                    "prompt_eval_count": 10,
                    "eval_count": 20,
                    "total_duration": 1e8,
                },
                {
                    "message": {
                        "content": "Audit complete. No additional issues found.",
                        "tool_calls": [],
                    },
                    "prompt_eval_count": 15,
                    "eval_count": 25,
                    "total_duration": 1e8,
                },
            ]

            report = runner.run("Inspect src/api.js")
            self.assertIn("Audit complete", report)

            # Verify that the tool response in messages history was formatted with role: "user"
            # because native tool_calls was empty (fallback parsing)
            second_chat_call_messages = mock_client.chat.call_args_list[1][1]["messages"]
            tool_result_msg = next((m for m in second_chat_call_messages if "[Tool Result for 'read_file']" in m.get("content", "")), None)
            self.assertIsNotNone(tool_result_msg)
            self.assertEqual(tool_result_msg["role"], "user")
            self.assertNotIn("tool", [m["role"] for m in second_chat_call_messages])


class TestBrowserTestingPrimitives(unittest.TestCase):
    """Unit tests for browser testing primitives (console noise filtering, DOM observer formatting)."""

    def test_console_log_noise_filtering(self):
        """Verify Emergent-style console log noise filter."""
        from subagents.testing.session import PlaywrightBrowserSession
        session = PlaywrightBrowserSession(headless=True)

        # Noisy logs should be skipped
        self.assertTrue(session._should_skip_log("Using fallback translation for language en"))
        self.assertTrue(session._should_skip_log("https://us-assets.i.posthog.com/static/array.js 403"))
        self.assertTrue(session._should_skip_log("Failed to load resource: fonts.googleapis.com"))

        # Real errors should NOT be skipped
        self.assertFalse(session._should_skip_log("Uncaught TypeError: Cannot read property 'map' of undefined"))
        self.assertFalse(session._should_skip_log("HTTP 500 Internal Server Error at /api/users"))

    def test_dom_observer_formatting(self):
        """Verify DOMObserver formats elements and errors cleanly."""
        from subagents.testing.observer import DOMObserver

        obs = {
            "url": "http://localhost:3000",
            "title": "Test App",
            "elements": [
                {"id": "el_0", "tag": "button", "type": "button", "text": "Submit", "testid": "btn-submit"},
                {"id": "el_1", "tag": "input", "type": "text", "text": "", "name": "username"},
            ],
            "dom_errors": ["Invalid credentials"],
        }

        formatted = DOMObserver.format_observation_for_llm(
            observation=obs,
            step=1,
            max_steps=5,
            console_errors=["[ERROR] 401 Unauthorized"],
            previous_action_result="Clicked el_0",
        )

        self.assertIn("[Step 1/5]", formatted)
        self.assertIn("Test App", formatted)
        self.assertIn("Invalid credentials", formatted)
        self.assertIn("Submit", formatted)
        self.assertIn("401 Unauthorized", formatted)



class TestVisionExpertSubagent(unittest.TestCase):
    """Unit tests for upgraded Goal-Driven Autonomous VisionExpertSubagent."""

    def setUp(self):
        self.sandbox_path = PROJECTS_ROOT / f"_test_vision_{uuid.uuid4().hex[:8]}"
        self.sandbox_path.mkdir(parents=True, exist_ok=True)
        self.registry = ToolRegistry(self.sandbox_path)
        from subagents.vision_subagent import VisionExpertSubagent
        self.subagent = VisionExpertSubagent(
            sandbox_path=self.sandbox_path,
            tool_registry=self.registry,
            max_iterations=4,
        )

    def tearDown(self):
        shutil.rmtree(self.sandbox_path, ignore_errors=True)

    def test_allowed_tools(self):
        """Verify vision subagent is scoped to read_file, grep_search, view_bulk, and get_assets."""
        expected = {"read_file", "grep_search", "view_bulk", "get_assets"}
        self.assertEqual(self.subagent.allowed_tools, expected)
        self.assertNotIn("write_file", self.subagent.allowed_tools)
        self.assertNotIn("edit_file", self.subagent.allowed_tools)
        self.assertNotIn("execute_command", self.subagent.allowed_tools)

    def test_autonomous_vision_runner_invocation(self):
        """Verify autonomous child runner is invoked with task description and returns structured report."""
        with patch("subagents.vision_subagent.SubagentRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner_cls.return_value = mock_runner
            mock_runner.run.return_value = """# 👁️ Vision & Aesthetic Review Report
**Design Intent**: Futuristic Audio Station
**Target Component**: `src/App.jsx`
**Overall Visual Quality Score**: **92/100**
**Status**: [APPROVED]
"""
            report = self.subagent.critique_ui(
                target_component_or_file="src/App.jsx",
                design_intent="Futuristic Audio Station",
            )
            mock_runner.run.assert_called_once()
            self.assertIn("Vision & Aesthetic Review Report", report)
            self.assertIn("92/100", report)

    def test_static_vision_analyzer_detection(self):
        """Verify StaticVisionAnalyzer detects font absence, raw hex, unstyled buttons, and placeholder images."""
        from subagents.vision.analyzer import StaticVisionAnalyzer

        # Create files with aesthetic issues
        src_dir = self.sandbox_path / "src"
        src_dir.mkdir(parents=True, exist_ok=True)

        (self.sandbox_path / "index.html").write_text("<!DOCTYPE html><html><body><div id='root'></div></body></html>")
        (src_dir / "index.css").write_text("body { margin: 0; }")
        (src_dir / "App.jsx").write_text("""
export default function App() {
  return (
    <div className="grid grid-cols-3">
      <button>Click Me</button>
      <input type="text" />
      <span style={{ color: '#ff0000' }}>Error</span>
      <img src="https://via.placeholder.com/150" alt="avatar" />
    </div>
  );
}
""")

        analysis = StaticVisionAnalyzer.analyze(self.sandbox_path, target_component_or_file="src/App.jsx")
        findings_text = " ".join(analysis["findings"])

        self.assertIn("Missing Google Font Pairings", findings_text)
        self.assertIn("Missing Semantic Theme Tokens", findings_text)
        self.assertIn("Static Grid Columns Detected", findings_text)
        self.assertIn("Unstyled Raw Button Elements", findings_text)
        self.assertIn("Unstyled Input Fields", findings_text)
        self.assertIn("Generic Placeholder Images Detected", findings_text)

        report = StaticVisionAnalyzer.generate_report(analysis, design_intent="Modern SaaS")
        self.assertIn("Vision & Aesthetic Review Report", report)
        self.assertIn("Recommended Polish Actions", report)

    def test_heuristic_fallback_on_runner_error(self):
        """Verify fallback to deterministic static analyzer when LLM runner encounters an error."""
        with patch("subagents.vision_subagent.SubagentRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner_cls.return_value = mock_runner
            mock_runner.run.side_effect = RuntimeError("Ollama connection timeout")

            # Create baseline files
            src_dir = self.sandbox_path / "src"
            src_dir.mkdir(parents=True, exist_ok=True)
            (src_dir / "index.css").write_text(":root { --primary: #6366f1; --bg-main: #0f172a; }")
            (src_dir / "App.jsx").write_text("export default function App() { return <div>App</div>; }")

            report = self.subagent.critique_ui(
                target_component_or_file="src/App.jsx",
                design_intent="Clean Dashboard",
            )
            self.assertIn("Vision & Aesthetic Review Report", report)
            self.assertIn("Score Breakdown", report)
            self.assertIn("src/App.jsx", report)


class TestUITestingSubagent(unittest.TestCase):
    """Unit tests for the overhauled UITestingSubagent."""

    def setUp(self):
        from subagents.ui_subagent import UITestingSubagent
        self.subagent = UITestingSubagent(max_steps=5)

    @patch("subagents.ui_subagent.PlaywrightBrowserSession")
    def test_ui_subagent_unreachable_server(self, mock_session_cls):
        """Verify that an unreachable server returns an honest failure without fake smoke data."""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.start.return_value = (False, "Connection refused at 127.0.0.1:5173")

        report = self.subagent.run_ui_test("http://localhost:5173", "Verify landing page")
        self.assertIn("❌ UI Test Failed: Application Unreachable", report)
        self.assertIn("Connection refused at 127.0.0.1:5173", report)
        self.assertIn("Do not attempt to run `npm run dev`", report)

    @patch("subagents.ui_subagent.DOMObserver")
    @patch("subagents.ui_subagent.ollama.Client")
    @patch("subagents.ui_subagent.PlaywrightBrowserSession")
    def test_ui_subagent_native_tool_call_flow(self, mock_session_cls, mock_ollama_cls, mock_observer_cls):
        """Verify multi-turn tool-calling loop executes actions and compiles a real-time report."""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.start.return_value = (True, "")
        mock_session.console_errors = []
        mock_session.network_failures = []
        mock_session.actions_executed = ["Clicked 'el_0' (Click submit button)"]

        mock_observer_cls.observe.return_value = {
            "url": "http://localhost:5173",
            "title": "Task Manager",
            "elements": [{"id": "el_0", "tag": "button", "text": "Submit Task"}],
            "dom_errors": [],
            "can_scroll_down": False,
        }
        mock_observer_cls.format_observation_for_llm.return_value = "Mock Observation"

        mock_client = MagicMock()
        mock_ollama_cls.return_value = mock_client

        # Turn 1: browser_click, Turn 2: browser_finish
        mock_client.chat.side_effect = [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "browser_click",
                                "arguments": {"id": "el_0", "reason": "Click submit button"},
                            }
                        }
                    ],
                }
            },
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "browser_finish",
                                "arguments": {
                                    "status": "PASSED",
                                    "report": "Form submit verified successfully.",
                                    "fix_instructions": "None",
                                },
                            }
                        }
                    ],
                }
            },
        ]

        report = self.subagent.run_ui_test("http://localhost:5173", "Verify submit task")
        mock_session.execute_action.assert_called_once_with({"name": "click", "arguments": {"id": "el_0", "reason": "Click submit button"}})
        self.assertIn("✅ PASSED", report)
        self.assertIn("Form submit verified successfully.", report)
        self.assertIn("Task Manager", report)
        self.assertIn("Visual Snapshot", report)
        mock_session.take_screenshot.assert_called_once()
        mock_session.close.assert_called_once()

    @patch("subagents.ui_subagent.DOMObserver")
    @patch("subagents.ui_subagent.ollama.Client")
    @patch("subagents.ui_subagent.PlaywrightBrowserSession")
    def test_ui_subagent_turn_one_retry_not_aborted(self, mock_session_cls, mock_ollama_cls, mock_observer_cls):
        """Verify that conversational text on turn 1 does NOT abort, but prompts a retry."""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.start.return_value = (True, "")
        mock_session.console_errors = []
        mock_session.network_failures = []
        mock_session.actions_executed = []

        mock_observer_cls.observe.return_value = {
            "url": "http://localhost:5173",
            "title": "App",
            "elements": [{"id": "el_0", "tag": "button", "text": "Save"}],
            "dom_errors": [],
            "can_scroll_down": False,
        }
        mock_observer_cls.format_observation_for_llm.return_value = "Mock Observation"

        mock_client = MagicMock()
        mock_ollama_cls.return_value = mock_client

        # Turn 1: Conversational text (no tool call)
        # Turn 2: Valid tool call
        # Turn 3: browser_finish
        mock_client.chat.side_effect = [
            {
                "message": {
                    "content": "I am thinking about clicking the Save button.",
                    "tool_calls": [],
                }
            },
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "browser_click",
                                "arguments": {"id": "el_0", "reason": "Click save"},
                            }
                        }
                    ],
                }
            },
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "browser_finish",
                                "arguments": {
                                    "status": "PASSED",
                                    "report": "Save flow tested after retry.",
                                },
                            }
                        }
                    ],
                }
            },
        ]

        report = self.subagent.run_ui_test("http://localhost:5173", "Test save")
        self.assertIn("✅ PASSED", report)
        self.assertIn("Save flow tested after retry.", report)
        self.assertEqual(mock_session.execute_action.call_count, 1)

    @patch("subagents.ui_subagent.DOMObserver")
    @patch("subagents.ui_subagent.ollama.Client")
    @patch("subagents.ui_subagent.PlaywrightBrowserSession")
    def test_ui_subagent_reports_real_errors(self, mock_session_cls, mock_ollama_cls, mock_observer_cls):
        """Verify that live console crashes and network errors are reported with ❌ FAILED."""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.start.return_value = (True, "")
        mock_session.console_errors = ["[CRASH] TypeError: Cannot read properties of undefined (reading 'map')"]
        mock_session.network_failures = ["[NET_FAIL] POST http://localhost:8000/api/items - 500 Internal Server Error"]
        mock_session.actions_executed = ["Clicked 'el_0'"]

        mock_observer_cls.observe.return_value = {
            "url": "http://localhost:5173",
            "title": "Error App",
            "elements": [],
            "dom_errors": ["Error loading items"],
            "can_scroll_down": False,
        }
        mock_observer_cls.format_observation_for_llm.return_value = "Mock Observation"

        mock_client = MagicMock()
        mock_ollama_cls.return_value = mock_client

        mock_client.chat.return_value = {
            "message": {
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "browser_finish",
                            "arguments": {
                                "status": "FAILED",
                                "report": "API 500 error triggered on load.",
                                "fix_instructions": "Fix null check in ItemList.jsx",
                            },
                        }
                    }
                ],
            }
        }

        report = self.subagent.run_ui_test("http://localhost:5173", "Test item load")
        self.assertIn("❌ FAILED", report)
        self.assertIn("TypeError: Cannot read properties of undefined", report)
        self.assertIn("500 Internal Server Error", report)
        self.assertIn("Fix null check in ItemList.jsx", report)

    @patch("subagents.ui_subagent.DOMObserver")
    @patch("subagents.ui_subagent.ollama.Client")
    @patch("subagents.ui_subagent.PlaywrightBrowserSession")
    def test_ui_subagent_advanced_tools_dispatch(self, mock_session_cls, mock_ollama_cls, mock_observer_cls):
        """Verify that advanced tools (hover, drag_and_drop, press_key, upload_file) dispatch to Playwright."""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.start.return_value = (True, "")
        mock_session.console_errors = []
        mock_session.network_failures = []
        mock_session.actions_executed = []

        mock_observer_cls.observe.return_value = {
            "url": "http://localhost:5173",
            "title": "Kanban App",
            "elements": [{"id": "el_1", "tag": "div", "text": "Card"}, {"id": "el_2", "tag": "div", "text": "Column"}],
            "dom_errors": [],
            "can_scroll_down": False,
        }
        mock_observer_cls.format_observation_for_llm.return_value = "Mock Observation"

        mock_client = MagicMock()
        mock_ollama_cls.return_value = mock_client

        # Sequence: hover -> drag_and_drop -> press_key -> finish
        mock_client.chat.side_effect = [
            {
                "message": {
                    "content": "",
                    "tool_calls": [{"function": {"name": "browser_hover", "arguments": {"id": "el_1", "reason": "preview tooltip"}}}],
                }
            },
            {
                "message": {
                    "content": "",
                    "tool_calls": [{"function": {"name": "browser_drag_and_drop", "arguments": {"source_id": "el_1", "target_id": "el_2", "reason": "move card"}}}],
                }
            },
            {
                "message": {
                    "content": "",
                    "tool_calls": [{"function": {"name": "browser_press_key", "arguments": {"key": "Escape", "reason": "close modal"}}}],
                }
            },
            {
                "message": {
                    "content": "",
                    "tool_calls": [{"function": {"name": "browser_finish", "arguments": {"status": "PASSED", "report": "All advanced interactions verified"}}}],
                }
            },
        ]

        report = self.subagent.run_ui_test("http://localhost:5173", "Test Kanban interactions")
        self.assertIn("✅ PASSED", report)
        self.assertIn("All advanced interactions verified", report)
class TestDynamicSubagentToolProvisioning(unittest.TestCase):
    """Unit tests for Approach B: dynamic subagent tool configuration and provisioning."""

    def setUp(self):
        self.sandbox_path = PROJECTS_ROOT / f"_test_dyn_tools_{uuid.uuid4().hex[:8]}"
        self.sandbox_path.mkdir(parents=True, exist_ok=True)
        self.registry = ToolRegistry(sandbox_dir=self.sandbox_path)

    def tearDown(self):
        shutil.rmtree(self.sandbox_path, ignore_errors=True)

    def test_base_subagent_tool_normalization(self):
        """Verify BaseSubagent correctly normalizes list, set, and comma-separated string."""
        from subagents.base import BaseSubagent

        class DummySubagent(BaseSubagent):
            @property
            def default_allowed_tools(self) -> set[str]:
                return {"default_tool_1", "default_tool_2"}

        # 1. Default fallback
        dummy = DummySubagent(sandbox_path=self.sandbox_path)
        self.assertEqual(dummy.allowed_tools, {"default_tool_1", "default_tool_2"})

        # 2. List input
        dummy_list = DummySubagent(sandbox_path=self.sandbox_path, allowed_tools=["read_file", "grep_search"])
        self.assertEqual(dummy_list.allowed_tools, {"read_file", "grep_search"})

        # 3. Comma-separated string
        dummy_str = DummySubagent(sandbox_path=self.sandbox_path, allowed_tools="read_file, locate_files_by_pattern")
        self.assertEqual(dummy_str.allowed_tools, {"read_file", "locate_files_by_pattern"})

        # 4. Property setter mutation
        dummy.allowed_tools = ["write_file", "view_bulk"]
        self.assertEqual(dummy.allowed_tools, {"write_file", "view_bulk"})

        # 5. Property setter reset to default
        dummy.allowed_tools = None
        self.assertEqual(dummy.allowed_tools, {"default_tool_1", "default_tool_2"})

    def test_subclasses_constructor_override(self):
        """Verify domain subagents accept custom allowed_tools in their constructors."""
        from subagents.code_reviewer_subagent import CodeReviewerSubagent
        from subagents.design_subagent import DesignSubagent

        custom_tools = {"read_file", "locate_files_by_pattern"}

        troubleshoot = TroubleshootSubagent(
            sandbox_path=self.sandbox_path,
            tool_registry=self.registry,
            allowed_tools=custom_tools,
        )
        self.assertEqual(troubleshoot.allowed_tools, custom_tools)

        reviewer = CodeReviewerSubagent(
            sandbox_path=self.sandbox_path,
            tool_registry=self.registry,
            allowed_tools=["read_file", "locate_files_by_pattern"],
        )
        self.assertEqual(reviewer.allowed_tools, custom_tools)

        design = DesignSubagent(
            sandbox_path=self.sandbox_path,
            tool_registry=self.registry,
            allowed_tools="read_file, write_file",
        )
        self.assertEqual(design.allowed_tools, {"read_file", "write_file"})

    def test_tool_registry_subagent_tools_injection(self):
        """Verify ToolRegistry initializes subagents with custom tools if provided in subagent_tools."""
        reg = ToolRegistry(
            sandbox_dir=self.sandbox_path,
            subagent_tools={
                "troubleshoot": ["read_file", "locate_files_by_pattern"],
                "invoke_design_agent": {"write_file"},
            },
        )
        self.assertEqual(reg.troubleshoot_subagent.allowed_tools, {"read_file", "locate_files_by_pattern"})
        self.assertEqual(reg.design_subagent.allowed_tools, {"write_file"})
        # Other subagents retain default tools
        self.assertIn("lint_javascript", reg.code_reviewer_subagent.allowed_tools)

    def test_tool_registry_configure_subagent_tools(self):
        """Verify ToolRegistry.configure_subagent_tools dynamically modifies subagent allowed tools."""
        self.assertNotIn("locate_files_by_pattern", self.registry.troubleshoot_subagent.allowed_tools)

        self.registry.configure_subagent_tools("troubleshoot", {"read_file", "locate_files_by_pattern"})
        self.assertEqual(self.registry.troubleshoot_subagent.allowed_tools, {"read_file", "locate_files_by_pattern"})

        # Check by canonical name and comma-separated string
        self.registry.configure_subagent_tools("invoke_design_agent", "read_file, locate_files_by_pattern")
        self.assertEqual(self.registry.design_subagent.allowed_tools, {"read_file", "locate_files_by_pattern"})

    def test_runner_scoped_schemas_with_custom_tools(self):
        """Verify SubagentRunner filters schemas strictly against custom provided allowed tools."""
        custom_tools = {"read_file", "locate_files_by_pattern"}
        troubleshoot = TroubleshootSubagent(
            sandbox_path=self.sandbox_path,
            tool_registry=self.registry,
            allowed_tools=custom_tools,
        )

        runner = SubagentRunner(
            name="troubleshoot_custom",
            system_prompt=troubleshoot.system_prompt,
            allowed_tools=troubleshoot.allowed_tools,
            tool_registry=self.registry,
        )

        scoped_schemas = runner._get_scoped_schemas()
        schema_names = {s["function"]["name"] for s in scoped_schemas}
        self.assertEqual(schema_names, custom_tools)

        scoped_tools = runner._get_scoped_tool_map()
        self.assertEqual(set(scoped_tools.keys()), custom_tools)


if __name__ == "__main__":
    unittest.main()

