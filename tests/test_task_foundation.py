"""
Unit tests for Phase 1 Foundation:
- Data models (Pydantic types)
- Agent Markdown Frontmatter Parser
- Bundled Agent Definitions Loader
- 3-tier Hierarchical Agent Discovery Precedence
"""

import unittest
import tempfile
import shutil
from pathlib import Path

from task.types import AgentDefinition, TaskItem, TaskParams, SingleResult, SubagentProgress
from task.agents import parse_agent_markdown, load_bundled_agents, get_bundled_agent, clear_bundled_agents_cache
from task.discovery import discover_agents, get_agent, list_agents


class TestTaskTypes(unittest.TestCase):
    """Test Pydantic data models for the task subsystem."""

    def test_agent_definition_defaults(self):
        defn = AgentDefinition(name="scout", description="Explorer")
        self.assertEqual(defn.name, "scout")
        self.assertEqual(defn.description, "Explorer")
        self.assertEqual(defn.tools, [])
        self.assertFalse(defn.blocking)
        self.assertTrue(defn.read_summarize)
        self.assertEqual(defn.source, "bundled")

    def test_task_item_and_params(self):
        item = TaskItem(agent="reviewer", task="Audit PR")
        self.assertEqual(item.agent, "reviewer")
        self.assertEqual(item.task, "Audit PR")
        self.assertEqual(item.schema_mode, "permissive")

        # Flat params
        params = TaskParams(agent="scout", task="Find auth routes")
        self.assertEqual(params.agent, "scout")
        self.assertEqual(params.task, "Find auth routes")

        # Batch params
        batch = TaskParams(
            context="Shared refactoring goal",
            tasks=[TaskItem(name="t1", agent="scout", task="Analyze"), TaskItem(name="t2", agent="task", task="Fix")]
        )
        self.assertEqual(batch.context, "Shared refactoring goal")
        self.assertEqual(len(batch.tasks), 2)

    def test_task_item_and_params_aliases(self):
        """Verify camelCase aliases work for TaskItem and TaskParams."""
        item = TaskItem.model_validate({
            "agent": "scout",
            "task": "Explore",
            "outputSchema": {"type": "object"},
            "schemaMode": "strict",
        })
        self.assertEqual(item.output_schema, {"type": "object"})
        self.assertEqual(item.schema_mode, "strict")

        params = TaskParams.model_validate({
            "agent": "scout",
            "task": "Explore",
            "outputSchema": {"type": "object"},
            "schemaMode": "strict",
        })
        self.assertEqual(params.output_schema, {"type": "object"})
        self.assertEqual(params.schema_mode, "strict")

class TestAgentFrontmatterParser(unittest.TestCase):
    """Test parsing markdown files with YAML frontmatter."""

    def test_parse_valid_frontmatter(self):
        md_content = """---
name: custom_scout
description: Custom exploration specialist
tools: read_file, glob_files, grep_search
model: "@smol"
thinking-level: medium
spawns: "*"
blocking: true
read-summarize: false
output:
  type: object
  properties:
    summary: { type: string }
---
You are a custom exploration agent. Focus on fast search.
"""
        defn = parse_agent_markdown(file_path=None, content=md_content, source="user")
        self.assertEqual(defn.name, "custom_scout")
        self.assertEqual(defn.description, "Custom exploration specialist")
        self.assertEqual(defn.tools, ["read_file", "glob_files", "grep_search"])
        self.assertEqual(defn.model, "@smol")
        self.assertEqual(defn.thinking_level, "medium")
        self.assertEqual(defn.spawns, "*")
        self.assertTrue(defn.blocking)
        self.assertFalse(defn.read_summarize)
        self.assertIsNotNone(defn.output_schema)
        self.assertEqual(defn.system_prompt, "You are a custom exploration agent. Focus on fast search.")
        self.assertEqual(defn.source, "user")

    def test_parse_without_frontmatter(self):
        content = "You are a raw system prompt without frontmatter."
        defn = parse_agent_markdown(file_path=Path("raw_worker.md"), content=content, source="project")
        self.assertEqual(defn.name, "raw_worker")
        self.assertEqual(defn.system_prompt, content)
        self.assertEqual(defn.tools, [])
        self.assertEqual(defn.source, "project")
    def test_parse_frontmatter_with_crlf_and_bom(self):
        """Verify parsing handles UTF-8 BOM and Windows CRLF newlines."""
        crlf_content = "\ufeff---\r\nname: crlf_worker\r\ndescription: Works with CRLF\r\ntools: read_file\r\n---\r\nPrompt body on CRLF\r\n"
        defn = parse_agent_markdown(file_path=None, content=crlf_content, source="bundled")
        self.assertEqual(defn.name, "crlf_worker")
        self.assertEqual(defn.description, "Works with CRLF")
        self.assertEqual(defn.tools, ["read_file"])
        self.assertEqual(defn.system_prompt, "Prompt body on CRLF")

    def test_parse_frontmatter_nested_delimiters(self):
        """Verify frontmatter containing '---' inside strings is preserved without premature truncation."""
        content = """---
name: delimiter_test
description: "Review divider: --- here"
tools: read_file
---
Actual body instructions.
"""
        defn = parse_agent_markdown(file_path=None, content=content, source="user")
        self.assertEqual(defn.name, "delimiter_test")
        self.assertEqual(defn.description, "Review divider: --- here")
        self.assertEqual(defn.system_prompt, "Actual body instructions.")

    def test_parse_spawns_as_list_and_booleans(self):
        """Verify spawns handles YAML lists, booleans, none, and strings."""
        # YAML list
        list_content = """---
name: list_spawner
spawns:
  - scout
  - reviewer
---
Body
"""
        defn = parse_agent_markdown(file_path=None, content=list_content)
        self.assertEqual(defn.spawns, "scout, reviewer")

        # Spawns false / none
        false_content = """---
name: no_spawn
spawns: false
---
Body
"""
        defn_false = parse_agent_markdown(file_path=None, content=false_content)
        self.assertIsNone(defn_false.spawns)

    def test_parse_boolean_strings_and_aliases(self):
        """Verify safe parsing of string booleans and field aliases."""
        content = """---
name: bool_worker
blocking: "false"
read_summarize: "false"
thinking_level: lo
output_schema:
  type: object
---
Body
"""
        defn = parse_agent_markdown(file_path=None, content=content)
        self.assertFalse(defn.blocking)
        self.assertFalse(defn.read_summarize)
        self.assertEqual(defn.thinking_level, "lo")
        self.assertEqual(defn.output_schema, {"type": "object"})

    def test_parse_non_dict_yaml(self):
        """Verify non-dictionary YAML frontmatter (scalars) fall back gracefully without crashing."""
        content = """---
just a plain string
---
Body content here.
"""
        defn = parse_agent_markdown(file_path=Path("scalar_agent.md"), content=content)
        self.assertEqual(defn.name, "scalar_agent")
        self.assertEqual(defn.system_prompt, "Body content here.")

    def test_whitespace_name_fallback(self):
        """Verify whitespace or empty agent name falls back to filename stem."""
        content = """---
name: "   "
description: Worker
---
Body
"""
        defn = parse_agent_markdown(file_path=Path("fallback_agent.md"), content=content)
        self.assertEqual(defn.name, "fallback_agent")

    def test_tool_deduplication_and_whitespace(self):
        """Verify tools list is stripped and deduplicated while preserving order."""
        content = """---
name: dedup_tools
tools: read_file, grep_search, read_file,  glob_files , grep_search
---
Body
"""
        defn = parse_agent_markdown(file_path=None, content=content)
        self.assertEqual(defn.tools, ["read_file", "grep_search", "glob_files"])


class TestBundledAgents(unittest.TestCase):
    """Verify all 7 bundled agents load correctly with expected attributes."""

    def setUp(self):
        clear_bundled_agents_cache()

    def tearDown(self):
        clear_bundled_agents_cache()

    def test_load_all_bundled_agents(self):
        bundled = load_bundled_agents()
        expected_names = {"task", "scout", "reviewer", "security_reviewer", "troubleshoot", "design", "tester"}
        self.assertTrue(expected_names.issubset(set(bundled.keys())))

        # Verify task agent
        task_agent = bundled["task"]
        self.assertIn("read_file", task_agent.tools)
        self.assertIn("write_file", task_agent.tools)
        self.assertIn("yield", task_agent.tools)
        self.assertEqual(task_agent.spawns, "*")

        # Verify scout agent
        scout_agent = bundled["scout"]
        self.assertEqual(scout_agent.model, "@smol")
        self.assertEqual(scout_agent.thinking_level, "medium")
        self.assertIsNotNone(scout_agent.output_schema)
        self.assertIn("summary", scout_agent.output_schema["properties"])

        # Verify reviewer agent
        rev_agent = bundled["reviewer"]
        self.assertEqual(rev_agent.model, "@slow")
        self.assertEqual(rev_agent.spawns, "scout")
        self.assertIsNotNone(rev_agent.output_schema)
        self.assertIn("overall_correctness", rev_agent.output_schema["properties"])

    def test_get_bundled_agent(self):
        scout = get_bundled_agent("scout")
        self.assertIsNotNone(scout)
        self.assertEqual(scout.name, "scout")

        missing = get_bundled_agent("non_existent_agent")
        self.assertIsNone(missing)
    def test_bundled_agents_cache_mutation_protection(self):
        """Verify mutating returned dict does not corrupt cached bundled agents."""
        first = load_bundled_agents()
        first["corrupted_agent"] = AgentDefinition(name="bad", description="bad")
        second = load_bundled_agents()
        self.assertNotIn("corrupted_agent", second)


class TestHierarchicalDiscovery(unittest.TestCase):
    """Verify discovery precedence: Bundled -> User -> Project."""

    def setUp(self):
        clear_bundled_agents_cache()
        self.temp_dir = tempfile.mkdtemp(prefix="lowkey_test_discovery_")
        self.test_root = Path(self.temp_dir)
        self.user_dir = self.test_root / "user_home"
        self.proj_dir = self.test_root / "project_workspace"
        self.user_dir.mkdir(parents=True)
        self.proj_dir.mkdir(parents=True)

    def tearDown(self):
        clear_bundled_agents_cache()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_discovery_precedence(self):
        # 1. Base check: bundled scout exists
        agents_base = discover_agents(project_root=self.proj_dir, home_dir=self.user_dir)
        self.assertEqual(agents_base["scout"].source, "bundled")
        self.assertEqual(agents_base["scout"].description, "MUST be used for exploratory codebase research, rapid code analysis, and broad pattern searches. Fast read-only scout returning compressed context for handoff.")

        # 2. User overrides scout (~/.lowkey/agents/scout.md)
        user_agents_path = self.user_dir / ".lowkey" / "agents"
        user_agents_path.mkdir(parents=True)
        (user_agents_path / "scout.md").write_text("""---
name: scout
description: User customized scout agent
tools: read_file
---
User scout instructions.
""", encoding="utf-8")

        agents_user = discover_agents(project_root=self.proj_dir, home_dir=self.user_dir)
        self.assertEqual(agents_user["scout"].source, "user")
        self.assertEqual(agents_user["scout"].description, "User customized scout agent")
        self.assertEqual(agents_user["scout"].system_prompt, "User scout instructions.")

        # 3. Project overrides scout (<project_root>/.lowkey/agents/scout.md)
        proj_agents_path = self.proj_dir / ".lowkey" / "agents"
        proj_agents_path.mkdir(parents=True)
        (proj_agents_path / "scout.md").write_text("""---
name: scout
description: Project specific scout agent
tools: read_file, grep_search
---
Project scout instructions.
""", encoding="utf-8")

        # Also add a brand new project-level agent
        (proj_agents_path / "react_specialist.md").write_text("""---
name: react_specialist
description: Project React component auditor
tools: read_file, lint_javascript
---
Audit React components.
""", encoding="utf-8")

        agents_proj = discover_agents(project_root=self.proj_dir, home_dir=self.user_dir)
        self.assertEqual(agents_proj["scout"].source, "project")
        self.assertEqual(agents_proj["scout"].description, "Project specific scout agent")
        self.assertIn("react_specialist", agents_proj)
        self.assertEqual(agents_proj["react_specialist"].source, "project")

    def test_get_agent_and_list_agents(self):
        agent = get_agent("task", project_root=self.proj_dir, home_dir=self.user_dir)
        self.assertIsNotNone(agent)
        self.assertEqual(agent.name, "task")

        all_list = list_agents(project_root=self.proj_dir, home_dir=self.user_dir)
        self.assertTrue(len(all_list) >= 7)
        names = [a.name for a in all_list]
        self.assertEqual(names, sorted(names))
    def test_discovery_empty_project_root(self):
        """Verify empty string project_root skips project-level discovery gracefully."""
        agents = discover_agents(project_root="", home_dir=self.user_dir)
        self.assertIn("task", agents)
        self.assertNotIn("react_specialist", agents)

    def test_load_agents_from_inaccessible_dir(self):
        """Verify load_agents_from_dir returns empty dict on non-existent path without error."""
        from task.discovery import load_agents_from_dir
        agents = load_agents_from_dir(Path("/non_existent_path_12345"), source="project")
        self.assertEqual(agents, {})


if __name__ == "__main__":
    unittest.main()
