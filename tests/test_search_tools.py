import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile
import shutil

from tools.search_tools import SearchTools
from tools.registry import ToolRegistry
from tools.schemas import TOOL_SCHEMAS
from config.settings import PROJECTS_ROOT


class TestSearchTools(unittest.TestCase):
    def setUp(self):
        self.search_tools = SearchTools()

    def test_search_web_empty_query(self):
        """Empty or whitespace-only queries must return a descriptive validation error."""
        res = self.search_tools.search_web("")
        self.assertIn("Error: query parameter must not be empty", res)

        res2 = self.search_tools.search_web("   ")
        self.assertIn("Error: query parameter must not be empty", res2)

    @patch("tools.search_tools.DDGS")
    def test_search_web_mock_success(self, mock_ddgs_cls):
        """Verify successful search output is formatted in clean markdown with links and snippets."""
        mock_instance = MagicMock()
        mock_instance.text.return_value = [
            {
                "title": "FastAPI Lifespan Events",
                "href": "https://fastapi.tiangolo.com/advanced/events/",
                "body": "Lifespan events can be used to run logic before the application starts up.",
            },
            {
                "title": "Starlette Lifespan Handlers",
                "href": "https://www.starlette.io/lifespan/",
                "body": "The lifespan state is shared across requests and tasks.",
            },
        ]
        mock_ddgs_cls.return_value.__enter__.return_value = mock_instance

        res = self.search_tools.search_web("FastAPI lifespan", max_results=2)

        self.assertIn('### Web Search Results for: "FastAPI lifespan"', res)
        self.assertIn("1. **[FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/)**", res)
        self.assertIn("Lifespan events can be used to run logic before the application starts up.", res)
        self.assertIn("2. **[Starlette Lifespan Handlers](https://www.starlette.io/lifespan/)**", res)
        self.assertIn("The lifespan state is shared across requests and tasks.", res)

    @patch("tools.search_tools.DDGS")
    def test_search_web_clamping(self, mock_ddgs_cls):
        """Verify max_results is clamped between 1 and 10 to protect LLM context window tokens."""
        mock_instance = MagicMock()
        mock_instance.text.return_value = []
        mock_ddgs_cls.return_value.__enter__.return_value = mock_instance

        # Test upper clamp
        self.search_tools.search_web("test query", max_results=50)
        mock_instance.text.assert_called_with("test query", max_results=10)

        # Test lower clamp
        self.search_tools.search_web("test query", max_results=-3)
        mock_instance.text.assert_called_with("test query", max_results=1)

    @patch("tools.search_tools.DDGS")
    def test_search_web_no_results(self, mock_ddgs_cls):
        """Verify message when search returns no matching items."""
        mock_instance = MagicMock()
        mock_instance.text.return_value = []
        mock_ddgs_cls.return_value.__enter__.return_value = mock_instance

        res = self.search_tools.search_web("xyznonexistentterm12345")
        self.assertIn("No web results found for query: 'xyznonexistentterm12345'", res)

    @patch("tools.search_tools.DDGS")
    def test_search_web_error_handling(self, mock_ddgs_cls):
        """Verify exceptions (network errors, rate limits) are caught gracefully and return error text."""
        mock_instance = MagicMock()
        mock_instance.text.side_effect = ConnectionError("Connection refused by upstream DuckDuckGo")
        mock_ddgs_cls.return_value.__enter__.return_value = mock_instance

        res = self.search_tools.search_web("test error handling")
        self.assertIn("Search error: Unable to retrieve results", res)
        self.assertIn("ConnectionError", res)

    @patch("tools.search_tools.DDGS", None)
    def test_search_web_missing_library(self):
        """Verify helpful error when ddgs is not installed."""
        res = self.search_tools.search_web("test query")
        self.assertIn("duckduckgo search library is not installed", res)

    def test_schemas_presence(self):
        """Verify search_web tool schema is present and well-formed in TOOL_SCHEMAS."""
        search_schema = next(
            (s for s in TOOL_SCHEMAS if s.get("function", {}).get("name") == "search_web"),
            None,
        )
        self.assertIsNotNone(search_schema)
        func = search_schema["function"]
        self.assertEqual(func["name"], "search_web")
        self.assertIn("query", func["parameters"]["properties"])
        self.assertIn("max_results", func["parameters"]["properties"])
        self.assertIn("query", func["parameters"]["required"])

    def test_tool_registry_registration(self):
        """Verify search_web is registered in ToolRegistry dispatch tables and functions."""
        test_dir = PROJECTS_ROOT / "_test_search_reg"
        test_dir.mkdir(parents=True, exist_ok=True)
        try:
            registry = ToolRegistry(sandbox_dir=test_dir)

            # Check get_tools mapping
            tools_map = registry.get_tools()
            self.assertIn("search_web", tools_map)
            self.assertEqual(tools_map["search_web"], registry.search_web)

            # Check get_tool_functions list
            tool_fns = registry.get_tool_functions()
            self.assertIn(registry.search_web, tool_fns)

            # Test invocation delegation through registry
            with patch.object(registry.search_tools, "search_web", return_value="Mocked search output") as mock_sw:
                out = registry.search_web(query="test", max_results=3)
                self.assertEqual(out, "Mocked search output")
                mock_sw.assert_called_once_with(query="test", max_results=3)
        finally:
            if test_dir.exists():
                shutil.rmtree(test_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
