from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, Callable, List, Optional

from config.settings import PROJECTS_ROOT, DEFAULT_MODEL_ID
from tools.file_tools import FileTools
from tools.linter_tools import LinterTools
from tools.process_tools import ProcessTools
from tools.asset_tools import AssetTools
from tools.interaction_tools import InteractionTools
from subagents.ui_subagent import UITestingSubagent
from subagents.design_subagent import DesignSubagent
from subagents.troubleshoot_subagent import TroubleshootSubagent
from subagents.vision_subagent import VisionExpertSubagent
from subagents.code_reviewer_subagent import CodeReviewerSubagent


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
    ):
        """
        Initialize the tool registry for a specific sandbox directory.

        Args:
            sandbox_dir: The directory where all commands and file operations will be constrained.
            event_callback: Optional callback to emit asynchronous events (e.g., preview_ready).
            model_name: Active model name to synchronize across all subagents.
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
        )
        self.linter_tools = LinterTools(
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
        )
        self.design_subagent = DesignSubagent(
            sandbox_path=self.sandbox_path,
            model_name=self.model_name,
            tool_registry=self,
            event_callback=self.event_callback,
        )
        self.troubleshoot_subagent = TroubleshootSubagent(
            sandbox_path=self.sandbox_path,
            model_name=self.model_name,
            tool_registry=self,
            event_callback=self.event_callback,
        )
        self.vision_subagent = VisionExpertSubagent(
            sandbox_path=self.sandbox_path,
            model_name=self.model_name,
            tool_registry=self,
            event_callback=self.event_callback,
        )
        self.ui_testing_subagent = UITestingSubagent(
            sandbox_path=self.sandbox_path,
            model_name=self.model_name,
            tool_registry=self,
            event_callback=self.event_callback,
        )
        self.code_reviewer_subagent = CodeReviewerSubagent(
            sandbox_path=self.sandbox_path,
            model_name=self.model_name,
            tool_registry=self,
            event_callback=self.event_callback,
        )

    def set_model_name(self, model_name: str) -> None:
        """Dynamically synchronizes the active model name to all child subagents."""
        if not model_name:
            return
        self.model_name = model_name
        for subagent in [
            self.design_subagent,
            self.troubleshoot_subagent,
            self.vision_subagent,
            self.ui_testing_subagent,
            self.code_reviewer_subagent,
        ]:
            if hasattr(subagent, "model_name"):
                subagent.model_name = model_name

    def get_subagent(self, name: str) -> Optional[Any]:
        """Resolves subagent instance by canonical tool name."""
        if name == "invoke_design_agent":
            return self.design_subagent
        if name == "invoke_troubleshoot_agent":
            return self.troubleshoot_subagent
        if name == "invoke_vision_agent":
            return self.vision_subagent
        if name == "invoke_testing_agent":
            return self.ui_testing_subagent
        if name == "invoke_code_reviewer_agent":
            return self.code_reviewer_subagent
        return None

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
            # Linter Tools
            "lint_javascript": self.lint_javascript,
            # Media & Asset Tools
            "get_assets": self.get_assets,
            # Interaction & Lifecycle Tools
            "ask_human": self.ask_human,
            "finish": self.finish,
            # Process & Dev Server Tools
            "execute_command": self.execute_command,
            "run_background_command": self.run_background_command,
            "stop_background_command": self.stop_background_command,
            # Specialized Subagents
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
            self.lint_javascript,
            self.get_assets,
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

    def read_file(self, file_path: str, start_line: int = 1, end_line: int = None) -> str:
        return self.file_tools.read_file(file_path=file_path, start_line=start_line, end_line=end_line)

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

    # ─────────────────────────────────────────────────────────────
    # Delegated Linter Operations
    # ─────────────────────────────────────────────────────────────

    def lint_javascript(self, file_path: str = ".") -> str:
        return self.linter_tools.lint_javascript(file_path=file_path)

    # ─────────────────────────────────────────────────────────────
    # Delegated Media & Asset Operations
    # ─────────────────────────────────────────────────────────────

    def get_assets(self, query: str = "", category: str = "", count: int = 5) -> str:
        return self.asset_tools.get_assets(query=query, category=category, count=count)

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

    # ─────────────────────────────────────────────────────────────
    # Delegated Subagent Operations
    # ─────────────────────────────────────────────────────────────

    def invoke_design_agent(
        self,
        problem_statement: str,
        app_type: str = "saas_app",
        theme_preference: str = "",
        auto_apply_css: bool = True,
    ) -> str:
        """Invoke the specialized Design Subagent to generate cohesive UI/UX tokens, Google Font pairings, and layout blueprints."""
        self.design_subagent.model_name = self.model_name
        return self.design_subagent.generate_layout_blueprint(
            problem_statement=problem_statement,
            app_type=app_type,
            theme_preference=theme_preference,
            auto_apply_css=auto_apply_css,
        )

    def invoke_troubleshoot_agent(
        self,
        error_log: str,
        context_file: str = "",
        recent_actions: str = "",
    ) -> str:
        """Invoke the specialized Troubleshoot Subagent to perform root-cause analysis and generate actionable fixes."""
        self.troubleshoot_subagent.model_name = self.model_name
        return self.troubleshoot_subagent.diagnose_error(
            error_log=error_log,
            context_file=context_file,
            recent_actions=recent_actions,
        )

    def invoke_vision_agent(
        self,
        target_component_or_file: str = "",
        screenshot_base64: str = "",
        design_intent: str = "",
    ) -> str:
        """Invoke the specialized Vision Expert Subagent to audit UI layout balance, color contrast, and micro-interactions."""
        self.vision_subagent.model_name = self.model_name
        return self.vision_subagent.critique_ui(
            target_component_or_file=target_component_or_file,
            screenshot_base64=screenshot_base64,
            design_intent=design_intent,
        )

    def invoke_testing_agent(self, url: str, instructions: str) -> str:
        """Invoke the specialized UI & Browser Testing Subagent to verify webpage functionality, DOM interactions, and user flows."""
        self.ui_testing_subagent.model_name = self.model_name
        return self.ui_testing_subagent.run_ui_test(url, instructions)

    def invoke_code_reviewer_agent(self, target_files: str = "", focus_areas: str = "") -> str:
        """Invoke the specialized Code Reviewer Subagent to audit code correctness, security, Express routes, and React best practices."""
        self.code_reviewer_subagent.model_name = self.model_name
        return self.code_reviewer_subagent.review_code(
            target_files=target_files,
            focus_areas=focus_areas,
        )



