import os
import subprocess
from pathlib import Path
from typing import Dict, Callable
from subagents.ui_subagent import UITestingSubagent


class ToolRegistry:
    """
    Manages safe execution of tools within a directory-restricted sandbox.
    All file operations are confined to the sandbox directory.
    """

    def __init__(self, sandbox_dir: str):
        self.sandbox_path = Path(sandbox_dir).resolve()
        # Ensure the sandbox directory exists
        self.sandbox_path.mkdir(parents=True, exist_ok=True)
        self.background_processes = {}

    def _is_safe_path(self, file_path: str) -> bool:
        """Verify the path is within the sandbox directory."""
        try:
            target_path = (self.sandbox_path / file_path).resolve()
            return self.sandbox_path in target_path.parents or target_path == self.sandbox_path
        except Exception:
            return False

    def get_tools(self) -> Dict[str, Callable]:
        """Returns a mapping of tool name -> callable for dynamic dispatch."""
        return {
            "read_file": self.read_file,
            "write_file": self.write_file,
            "edit_file": self.edit_file,
            "list_directory": self.list_directory,
            "execute_command": self.execute_command,
            "run_background_command": self.run_background_command,
            "stop_background_command": self.stop_background_command,
            "test_ui": self.test_ui,
        }

    def get_tool_functions(self) -> list:
        """Returns the list of tool functions for Ollama's tools parameter.
        Ollama SDK auto-generates JSON schemas from these functions' signatures and docstrings.
        """
        return [
            self.read_file,
            self.write_file,
            self.edit_file,
            self.list_directory,
            self.execute_command,
            self.run_background_command,
            self.stop_background_command,
            self.test_ui,
        ]

    def read_file(self, file_path: str) -> str:
        """Read the contents of a file.

        Args:
            file_path: The relative path to the file to read.

        Returns:
            The contents of the file as a string.
        """
        if not self._is_safe_path(file_path):
            return f"Error: Access denied to path outside sandbox: {file_path}"

        target = self.sandbox_path / file_path
        if not target.exists():
            return f"Error: File not found: {file_path}"

        try:
            with open(target, "r") as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {str(e)}"

    def write_file(self, file_path: str, content: str) -> str:
        """Write content to a file, creating it and any parent directories if they don't exist.

        Args:
            file_path: The relative path to the file to write.
            content: The full content to write to the file.

        Returns:
            A success or error message.
        """
        if not self._is_safe_path(file_path):
            return f"Error: Access denied to path outside sandbox: {file_path}"

        target = self.sandbox_path / file_path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w") as f:
                f.write(content)
            return f"Successfully wrote to {file_path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

    def edit_file(self, file_path: str, old_text: str, new_text: str) -> str:
        """Edit a file by replacing a specific text occurrence with new text.

        Args:
            file_path: The relative path to the file to edit.
            old_text: The exact text to find and replace.
            new_text: The text to replace it with.

        Returns:
            A success or error message.
        """
        if not self._is_safe_path(file_path):
            return f"Error: Access denied to path outside sandbox: {file_path}"

        target = self.sandbox_path / file_path
        if not target.exists():
            return f"Error: File not found: {file_path}"

        try:
            content = target.read_text()
            if old_text not in content:
                return (
                    f"Error: The specified old_text was not found in {file_path}. "
                    f"Please use read_file('{file_path}') to see the exact current contents, "
                    f"or use write_file('{file_path}', content) to rewrite the file."
                )

            updated = content.replace(old_text, new_text, 1)
            target.write_text(updated)
            return f"Successfully edited {file_path}"
        except Exception as e:
            return f"Error editing file: {str(e)}"

    def list_directory(self, path: str = ".") -> str:
        """List the contents of a directory, showing files and subdirectories.

        Args:
            path: The relative path to the directory to list. Defaults to the sandbox root.

        Returns:
            A formatted listing of directory contents.
        """
        if not self._is_safe_path(path):
            return f"Error: Access denied to path outside sandbox: {path}"

        target = (self.sandbox_path / path).resolve()
        if not target.exists():
            return f"Error: Directory not found: {path}"
        if not target.is_dir():
            return f"Error: {path} is not a directory"

        try:
            entries = []
            for item in sorted(target.iterdir()):
                rel = item.relative_to(self.sandbox_path)
                if item.is_dir():
                    entries.append(f"  [DIR]  {rel}/")
                else:
                    size = item.stat().st_size
                    entries.append(f"  [FILE] {rel} ({size} bytes)")

            if not entries:
                return f"Directory '{path}' is empty."

            return f"Contents of '{path}':\n" + "\n".join(entries)
        except Exception as e:
            return f"Error listing directory: {str(e)}"

    def execute_command(self, command: str) -> str:
        """Execute a shell command in the sandbox directory.

        Args:
            command: The shell command to execute.

        Returns:
            The command output (stdout on success, stderr on failure).
        """
        cmd_clean = command.strip()
        if cmd_clean.startswith("cd ") or cmd_clean == "cd":
            return (
                "Note: Standalone 'cd' command executed, but shell directory state does NOT persist "
                "across separate tool calls. All tool calls execute relative to the project root. "
                "To write files in subdirectories, specify relative paths in write_file (e.g. 'folder/file.py') "
                "or combine commands with '&&' (e.g. 'cd folder && python script.py')."
            )

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(self.sandbox_path),
                capture_output=True,
                text=True,
                timeout=300,
            )
            output = result.stdout if result.returncode == 0 else result.stderr
            if not output.strip():
                return f"Command completed with exit code {result.returncode} (no output)"
            
            if result.returncode != 0:
                return f"[Command failed with exit code {result.returncode}]\n{output}"
            return output
        except subprocess.TimeoutExpired:
            return "Error: Command timed out after 300 seconds"
        except Exception as e:
            return f"Error executing command: {str(e)}"

    def run_background_command(self, command: str, log_filename: str = "server.log") -> str:
        """Execute a shell command in the background (useful for starting web servers).
        
        Args:
            command: The shell command to execute in the background.
            log_filename: The name of the log file to append output to (default: server.log).
            
        Returns:
            A message indicating the process started with its PID.
        """
        # Check if the exact command is already running
        for pid, process in list(self.background_processes.items()):
            if getattr(process, "command_str", None) == command and process.poll() is None:
                existing_log = getattr(process, "log_filename", "unknown.log")
                return f"Command is already running in the background with PID {pid}. Logs are in '{existing_log}'."

        try:
            log_path = self.sandbox_path / log_filename
            log_file = open(log_path, "a")  # Append instead of overwrite
            
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=str(self.sandbox_path),
                stdout=log_file,
                stderr=subprocess.STDOUT
            )
            process.command_str = command
            process.log_filename = log_filename
            self.background_processes[process.pid] = process
            return f"Background process started with PID {process.pid}. Logs are being appended to '{log_filename}'. Use read_file to check its output."
        except Exception as e:
            return f"Error starting background command: {str(e)}"
            
    def stop_background_command(self, pid: int) -> str:
        """Stop a running background command by its PID.
        
        Args:
            pid: The process ID to stop.
            
        Returns:
            A success or error message.
        """
        process = self.background_processes.get(pid)
        if not process:
            return f"Error: No background process found with PID {pid}."
            
        try:
            process.terminate()
            del self.background_processes[pid]
            return f"Successfully terminated process {pid}."
        except Exception as e:
            return f"Error terminating process {pid}: {str(e)}"
            
    def cleanup(self):
        """Kill all tracked background processes."""
        for pid, process in list(self.background_processes.items()):
            try:
                process.terminate()
            except Exception:
                pass
        self.background_processes.clear()

    def test_ui(self, url: str, instructions: str) -> str:
        """Run an automated UI testing subagent to verify the functionality of a webpage.
        
        Args:
            url: The URL to test (e.g., 'http://localhost:5000').
            instructions: What the subagent should test (e.g., 'Add a todo item and check if it appears').
            
        Returns:
            A detailed report from the subagent on what it tested and the results.
        """
        subagent = UITestingSubagent()
        return subagent.run_ui_test(url, instructions)
