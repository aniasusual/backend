from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, Callable, List, Optional

from config.settings import PROJECTS_ROOT, DEFAULT_MODEL_ID
from tools.file_tools import FileTools
from tools.linter_tools import LinterTools
from tools.ast_tools import ASTTools
from tools.process_tools import ProcessTools
from tools.asset_tools import AssetTools
from tools.interaction_tools import InteractionTools
from tools.search_tools import SearchTools
from task import TaskTool, HubTool, YieldTool, AsyncJobManager


class ToolRegistry:
    """
    Manages safe execution of tools within a directory-restricted sandbox.
    Acts as the primary coordinator delegating to modular FileTools, LinterTools,
    ProcessTools, AssetTools, InteractionTools, and Specialized Subagents.
    """

    def __init__(
        self,
        sandbox_dir: Path,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        model_name: str = DEFAULT_MODEL_ID,
        subagent_tools: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the tool registry for a specific sandbox directory.

        Args:
            sandbox_dir: The directory where all commands and file operations will be constrained.
            event_callback: Optional callback to emit asynchronous events (e.g., preview_ready).
            model_name: Active model name to synchronize across all subagents.
            subagent_tools: Optional mapping of subagent names to their allowed tools sets.
        """
        self.sandbox_path = Path(sandbox_dir).resolve()
        self.model_name = model_name

        # Ensure the path is safely under the projects root
        if PROJECTS_ROOT not in self.sandbox_path.parents and self.sandbox_path != PROJECTS_ROOT:
            raise ValueError(f"Security Error: Project path {self.sandbox_path} is not under {PROJECTS_ROOT}")

        # Ensure the sandbox directory exists
        self.sandbox_path.mkdir(parents=True, exist_ok=True)
        self.event_callback = event_callback

        # Initialize modular tool handlers
        self.file_tools = FileTools(
            sandbox_path=self.sandbox_path,
            is_safe_path_fn=self._is_safe_path,
            event_callback=self.event_callback,
            model_name=self.model_name,
        )
        self.linter_tools = LinterTools(
            sandbox_path=self.sandbox_path,
            is_safe_path_fn=self._is_safe_path,
        )
        self.ast_tools = ASTTools(
            sandbox_path=self.sandbox_path,
            is_safe_path_fn=self._is_safe_path,
        )
        self.process_tools = ProcessTools(
            sandbox_path=self.sandbox_path,
            event_callback=self.event_callback,
        )
        self.asset_tools = AssetTools(
            sandbox_path=self.sandbox_path,
        )
        self.interaction_tools = InteractionTools(
            event_callback=self.event_callback,
            sandbox_path=self.sandbox_path,
        )
        self.search_tools = SearchTools()
        # Initialize Task delegation and coordination tools
        self.async_job_manager = AsyncJobManager.get_global()
        self.task_tool = TaskTool(
            tool_registry=self,
            max_recursion_depth=2,
            async_job_manager=self.async_job_manager,
        )
        self.hub_tool = HubTool(
            self_agent_id="main_agent",
            async_job_manager=self.async_job_manager,
        )
        self.yield_tool = YieldTool()

    def set_model_name(self, model_name: str) -> None:
        """Dynamically synchronizes the active model name."""
        if not model_name:
            return
        self.model_name = model_name
        if hasattr(self, "file_tools"):
            self.file_tools.model_name = model_name

    def configure_subagent_tools(self, subagent_name: str, allowed_tools: Any) -> None:
        """Compatibility stub for dynamic subagent tool configuration."""
        pass

    SUBAGENT_TOOL_NAMES = {
        "task",
        "invoke_design_agent",
        "invoke_troubleshoot_agent",
        "invoke_vision_agent",
        "invoke_testing_agent",
        "invoke_code_reviewer_agent",
    }

    def get_subagent(self, name: str) -> Optional[Any]:
        """Resolves task tool delegation for subagent tracking."""
        if name in self.SUBAGENT_TOOL_NAMES:
            return self.task_tool
        return None

    @property
    def last_run_events(self) -> List[Dict[str, Any]]:
        return getattr(self.task_tool, "last_run_events", [])

    @property
    def last_run_metrics(self) -> Dict[str, Any]:
        return getattr(self.task_tool, "last_run_metrics", {})

    def _is_safe_path(self, file_path: str) -> bool:
        """Verify the path is within the sandbox directory."""
        try:
            target_path = (self.sandbox_path / file_path).resolve()
            return self.sandbox_path in target_path.parents or target_path == self.sandbox_path
        except Exception:
            return False

    @property
    def background_processes(self) -> Dict[int, Dict[str, Any]]:
        """Direct access to active background processes mapping."""
        return self.process_tools.background_processes

    @property
    def mounted_virtual_ram(self) -> Dict[str, str]:
        """Direct access to active files mounted in Dynamic Virtual RAM."""
        return self.file_tools.mounted_virtual_ram

    # ─────────────────────────────────────────────────────────────
    # Tool Registration & Dispatch Mapping
    # ─────────────────────────────────────────────────────────────

    def get_tools(self) -> Dict[str, Callable]:
        """Returns a mapping of tool name -> callable for dynamic dispatch."""
        return {
            # File Tools
            "read_file": self.read_file,
            "view_bulk": self.view_bulk,
            "glob_files": self.glob_files,
            "grep_search": self.grep_search,
            "write_file": self.write_file,
            "write_files": self.write_files,
            "edit_file": self.edit_file,
            "insert_text": self.insert_text,
            "list_directory": self.list_directory,
            "locate_files_by_pattern": self.locate_files_by_pattern,
            # AST & Code Mapping Tools
            "extract_signatures": self.extract_signatures,
            "map_dependencies": self.map_dependencies,
            # Virtual RAM Lifecycle Tools
            "mount_file": self.mount_file,
            "unmount_file": self.unmount_file,
            "close_file": self.close_file,
            "list_mounted_files": self.list_mounted_files,
            # Linter Tools
            "lint_javascript": self.lint_javascript,
            # Media & Asset Tools
            "get_assets": self.get_assets,
            # Web Search Tools
            "search_web": self.search_web,
            # Interaction & Lifecycle Tools
            "ask_human": self.ask_human,
            "finish": self.finish,
            # Browser Automation & Testing Tools
            "browser_navigate": self.interaction_tools.browser_navigate,
            "browser_click": self.interaction_tools.browser_click,
            "browser_fill": self.interaction_tools.browser_fill,
            "browser_snapshot": self.interaction_tools.browser_snapshot,
            "browser_screenshot": self.interaction_tools.browser_screenshot,
            "browser_scroll": self.interaction_tools.browser_scroll,
            # Process & Dev Server Tools
            "execute_command": self.execute_command,
            "run_background_command": self.run_background_command,
            "stop_background_command": self.stop_background_command,
            # Subagent Delegation & Peer Coordination Tools
            "task": self.task,
            "hub": self.hub,
            "yield": self.yield_fn,
            # Backward compatibility aliases
            "invoke_design_agent": self.invoke_design_agent,
            "invoke_troubleshoot_agent": self.invoke_troubleshoot_agent,
            "invoke_vision_agent": self.invoke_vision_agent,
            "invoke_testing_agent": self.invoke_testing_agent,
            "invoke_code_reviewer_agent": self.invoke_code_reviewer_agent,
        }

    def get_tool_functions(self) -> list:
        """Returns the list of tool functions for Ollama's tools parameter.
        Ollama SDK auto-generates JSON schemas from these functions' signatures and docstrings.
        """
        return [
            self.read_file,
            self.view_bulk,
            self.glob_files,
            self.grep_search,
            self.write_file,
            self.write_files,
            self.edit_file,
            self.insert_text,
            self.list_directory,
            self.locate_files_by_pattern,
            self.extract_signatures,
            self.map_dependencies,
            self.mount_file,
            self.unmount_file,
            self.close_file,
            self.list_mounted_files,
            self.lint_javascript,
            self.get_assets,
            self.search_web,
            self.ask_human,
            self.finish,
            self.invoke_design_agent,
            self.invoke_troubleshoot_agent,
            self.invoke_vision_agent,
            self.execute_command,
            self.run_background_command,
            self.stop_background_command,
            self.invoke_testing_agent,
            self.invoke_code_reviewer_agent,
        ]

    # ─────────────────────────────────────────────────────────────
    # Delegated File Operations
    # ─────────────────────────────────────────────────────────────

    def extract_signatures(self, file_path: str) -> str:
        """Extracts structural code signatures (classes, methods, functions, Express routes,
        interfaces, exports, docstrings) from Python, JavaScript, TypeScript, or JSX files,
        stripping interior execution bodies.
        """
        return self.ast_tools.extract_signatures(file_path=file_path)

    def map_dependencies(self, target_file: Optional[str] = None) -> str:
        """Maps repository import/export relationships across the workspace or analyzes
        the architectural impact of changing a specific target file.
        """
        return self.ast_tools.map_dependencies(target_file=target_file)

    def read_file(self, file_path: Optional[str] = None, start_line: int = 1, end_line: Optional[int] = None) -> str:
        return self.file_tools.read_file(file_path=file_path, start_line=start_line, end_line=end_line)

    def mount_file(self, file_path: str, model_name: Optional[str] = None) -> str:
        return self.file_tools.mount_file(file_path=file_path, model_name=model_name or self.model_name)

    def unmount_file(self, file_path: str, **kwargs) -> str:
        return self.file_tools.unmount_file(file_path=file_path, **kwargs)

    def close_file(self, file_path: str, **kwargs) -> str:
        """Alias for unmount_file."""
        return self.file_tools.unmount_file(file_path=file_path, **kwargs)

    def list_mounted_files(self, model_name: Optional[str] = None) -> str:
        return self.file_tools.list_mounted_files(model_name=model_name or self.model_name)

    def view_bulk(self, files: Any = None, **kwargs) -> str:
        return self.file_tools.view_bulk(files=files, **kwargs)

    def glob_files(self, pattern: str, path: str = ".") -> str:
        return self.file_tools.glob_files(pattern=pattern, path=path)

    def grep_search(self, query: str, path: str = ".", case_sensitive: bool = False) -> str:
        return self.file_tools.grep_search(query=query, path=path, case_sensitive=case_sensitive)

    def write_file(self, file_path: str, content: str) -> str:
        return self.file_tools.write_file(file_path=file_path, content=content)

    def write_files(self, files: Any = None, **kwargs) -> str:
        return self.file_tools.write_files(files=files, **kwargs)

    def insert_text(self, file_path: str, line_number: int, text: str) -> str:
        return self.file_tools.insert_text(file_path=file_path, line_number=line_number, text=text)

    def edit_file(self, file_path: str, old_text: str, new_text: str, replace_all: bool = False) -> str:
        return self.file_tools.edit_file(file_path=file_path, old_text=old_text, new_text=new_text, replace_all=replace_all)

    def list_directory(self, path: str = ".") -> str:
        return self.file_tools.list_directory(path=path)

    def locate_files_by_pattern(self, directory: str = ".", max_depth: int = 3, pattern: str = "*") -> str:
        return self.file_tools.locate_files_by_pattern(directory=directory, max_depth=max_depth, pattern=pattern)

    # ─────────────────────────────────────────────────────────────
    # Delegated Linter Operations
    # ─────────────────────────────────────────────────────────────

    def lint_javascript(
        self,
        file_path: Optional[str] = ".",
        items: Optional[Any] = None,
        files: Optional[Any] = None,
        **kwargs: Any
    ) -> str:
        return self.linter_tools.lint_javascript(
            file_path=file_path,
            items=items,
            files=files,
            **kwargs
        )

    # ─────────────────────────────────────────────────────────────
    # Delegated Media & Asset Operations
    # ─────────────────────────────────────────────────────────────

    def get_assets(self, query: str = "", category: str = "", count: int = 5) -> str:
        return self.asset_tools.get_assets(query=query, category=category, count=count)

    # ─────────────────────────────────────────────────────────────
    # Delegated Web Search Operations
    # ─────────────────────────────────────────────────────────────

    def search_web(self, query: str, max_results: int = 5) -> str:
        """Search the web using DuckDuckGo for live documentation, APIs, error solutions, or technical references without API keys.

        Args:
            query: The search query to look up (e.g. 'FastAPI lifespan handlers', 'Tailwind v4 grid syntax').
            max_results: Maximum number of search results to return (default: 5, range: 1-10).

        Returns:
            A formatted markdown summary of top web search results with titles, links, and snippets.
        """
        return self.search_tools.search_web(query=query, max_results=max_results)

    # ─────────────────────────────────────────────────────────────
    # Delegated Interaction & Lifecycle Operations
    # ─────────────────────────────────────────────────────────────

    def ask_human(self, question: str, options: Optional[List[str]] = None) -> str:
        return self.interaction_tools.ask_human(question=question, options=options)

    def finish(self, summary: str, next_steps: Optional[str] = None) -> str:
        return self.interaction_tools.finish(summary=summary, next_steps=next_steps)

    # ─────────────────────────────────────────────────────────────
    # Delegated Process & Dev Server Operations
    # ─────────────────────────────────────────────────────────────

    def execute_command(self, command: str, reason: str = "") -> str:
        return self.process_tools.execute_command(command=command, reason=reason)

    def start_dev_server(self, command: str = "npm run dev", log_filename: str = "server.log", restart: bool = False) -> Dict[str, Any]:
        return self.process_tools.start_dev_server(command=command, log_filename=log_filename, restart=restart)

    def run_background_command(self, command: str, reason: str = "", log_filename: str = "server.log") -> str:
        return self.process_tools.run_background_command(command=command, reason=reason, log_filename=log_filename)

    def stop_background_command(self, pid: int) -> str:
        return self.process_tools.stop_background_command(pid=pid)

    def get_active_processes(self) -> List[Dict[str, Any]]:
        return self.process_tools.get_active_processes()

    def cleanup(self):
        self.process_tools.cleanup()
        if hasattr(self, "interaction_tools"):
            self.interaction_tools.cleanup()

    # ─────────────────────────────────────────────────────────────
    # Delegated Subagent Operations
    # ─────────────────────────────────────────────────────────────

    async def task(self, **kwargs) -> str:
        """Delegate tasks to specialized background subagents."""
        res = await self.task_tool.execute(
            tool_call_id="call",
            raw_params=kwargs,
            context={"project_root": self.sandbox_path, "task_depth": 0},
            event_callback=self.event_callback,
        )
        return res["content"][0]["text"]

    async def hub(self, **kwargs) -> str:
        """Agent coordination: peer messaging, background-job control, and process supervision."""
        return await self.hub_tool.execute(**kwargs)

    def yield_fn(self, **kwargs) -> str:
        """Mandatory tool for subagents to deliver final findings or blocker errors."""
        return self.yield_tool.execute(**kwargs)

    async def invoke_design_agent(
        self,
        problem_statement: str,
        app_type: str = "saas_app",
        theme_preference: str = "",
        auto_apply_css: bool = True,
    ) -> str:
        """Invoke the specialized Design Subagent via unified task delegation."""
        return await self.task(
            agent="design",
            task=f"Problem statement: {problem_statement}\nApp type: {app_type}\nTheme preference: {theme_preference}\nAuto-apply CSS: {auto_apply_css}",
        )

    async def invoke_troubleshoot_agent(
        self,
        error_log: str,
        context_file: str = "",
        recent_actions: str = "",
    ) -> str:
        """Invoke the specialized Troubleshoot Subagent via unified task delegation."""
        return await self.task(
            agent="troubleshoot",
            task=f"Diagnose error: {error_log}\nContext file: {context_file}\nRecent actions: {recent_actions}",
        )

    async def invoke_vision_agent(
        self,
        target_component_or_file: str = "",
        screenshot_base64: str = "",
        design_intent: str = "",
    ) -> str:
        """Invoke the specialized Vision Expert Subagent via unified task delegation."""
        return await self.task(
            agent="scout",
            task=f"Audit visual component: {target_component_or_file}\nDesign intent: {design_intent}",
        )
    def get_dev_server_info(self) -> Optional[Dict[str, Any]]:
        """Returns metadata about the active development server."""
        return self.process_tools.get_dev_server_info()

    def get_dev_server_url(self) -> str:
        """Gets the URL of the active development server, auto-starting it if necessary."""
        info = self.process_tools.get_dev_server_info()
        if info and info.get("url"):
            return info["url"]
        if (self.sandbox_path / "package.json").exists():
            res = self.start_dev_server()
            if res.get("url"):
                return res["url"]
        return "http://localhost:3000"

    async def invoke_testing_agent(self, url: str = "", instructions: str = "") -> str:
        """Invoke the specialized UI & Browser Testing Subagent via unified task delegation."""
        dev_url = self.get_dev_server_url()
        resolved_url = url or dev_url
        return await self.task(
            agent="tester",
            task=f"Test URL: {resolved_url}\nInstructions: {instructions}",
        )

    async def invoke_code_reviewer_agent(self, target_files: str = "", focus_areas: str = "") -> str:
        """Invoke the specialized Code Reviewer Subagent via unified task delegation."""
        return await self.task(
            agent="reviewer",
            task=f"Target files: {target_files or 'All project files'}\nFocus areas: {focus_areas or 'General code quality and security'}",
        )


