import os
import time
import subprocess
import signal
import socket
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable


class ProcessTools:
    """
    Dedicated handler for executing sandbox commands, managing dual-port dev servers,
    tracking background processes, and cleanly isolating execution lifecycles.
    """

    def __init__(
        self,
        sandbox_path: Path,
        event_callback: Optional[Callable[[dict], None]] = None,
    ):
        self.sandbox_path = sandbox_path
        self.event_callback = event_callback
        # Maps pid -> { "process": Popen, "command": str, "log_filename": str, "port": int | None, "backend_port": int | None, "is_dev_server": bool }
        self.background_processes: Dict[int, Dict[str, Any]] = {}

    def _is_port_in_use(self, port: int) -> bool:
        """Check if a specific port is in use on localhost."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            return s.connect_ex(("127.0.0.1", port)) == 0

    def _find_free_port(self) -> int:
        """Find an available ephemeral port on the host."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    def _find_preferred_or_free_port(self, preferred_port: int, max_attempts: int = 50) -> int:
        """Find a free port starting from preferred_port, checking incrementally."""
        for port in range(preferred_port, preferred_port + max_attempts):
            if not self._is_port_in_use(port):
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.bind(("127.0.0.1", port))
                        return port
                except OSError:
                    continue
        return self._find_free_port()

    def _is_command_safe(self, command: str) -> str | None:
        """Check if a command is blacklisted for sandbox security."""
        cmd_lower = command.lower()
        blacklist = [
            "sudo ",
            "rm -rf /",
            "chmod 777",
            "curl ",
            "wget ",
            "npm -g",
            "npm install -g",
            "../",
        ]
        for bad in blacklist:
            if bad in cmd_lower:
                return f"Error: Command rejected due to security policy (contains '{bad}')."
        return None

    def execute_command(self, command: str, reason: str = "") -> str:
        """Execute a short-lived shell command in the sandbox directory."""
        cmd_clean = command.strip()

        err = self._is_command_safe(cmd_clean)
        if err:
            return err

        cmd_lower = cmd_clean.lower()
        dev_server_keywords = ["npm run dev", "npm start", "npm run start", "yarn dev", "pnpm dev", "bun dev", "vite", "npx vite"]
        if any(kw in cmd_lower for kw in dev_server_keywords):
            is_explicit_restart = "restart" in cmd_lower or "restart" in reason.lower()
            res = self.start_dev_server(command=command, restart=is_explicit_restart)
            if res.get("status") == "already_running":
                return (
                    f"Dev server is already running in background (PID {res['pid']}) with Hot Module Replacement (HMR) "
                    f"at {res['url']} (API: {res.get('backend_port')}). Any code changes are reflected automatically without restarting."
                )
            elif res.get("status") == "started":
                return (
                    f"Dev server started in background (PID {res['pid']}) with frontend on port {res['port']} "
                    f"and API on port {res['backend_port']} (URL: {res['url']}). Live preview updated."
                )
            else:
                return f"Error starting dev server: {res.get('error')}"

        general_server_keywords = ["python -m http.server", "python3 -m http.server", "flask run", "uvicorn ", "gunicorn ", "live-server", "http-server"]
        if any(kw in cmd_lower for kw in general_server_keywords):
            return self.run_background_command(command=command, reason=reason)

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

    def start_dev_server(
        self,
        command: str = "npm run dev",
        log_filename: str = "server.log",
        restart: bool = False,
    ) -> Dict[str, Any]:
        """Starts the fullstack development server in the background with dual-port allocation."""
        for pid, info in list(self.background_processes.items()):
            if info["process"].poll() is None and info.get("is_dev_server"):
                if restart:
                    self.stop_background_command(pid)
                    time.sleep(0.5)
                    break
                else:
                    return {
                        "status": "already_running",
                        "pid": pid,
                        "port": info.get("port"),
                        "backend_port": info.get("backend_port"),
                        "url": f"http://localhost:{info.get('port')}",
                    }

        frontend_port = self._find_preferred_or_free_port(3000)
        backend_preferred = 5001 if frontend_port != 5001 else 5002
        backend_port = self._find_preferred_or_free_port(backend_preferred)
        if backend_port == frontend_port:
            backend_port = self._find_preferred_or_free_port(frontend_port + 1)

        try:
            log_path = self.sandbox_path / log_filename
            log_file = open(log_path, "a")

            env = os.environ.copy()
            env["PORT"] = str(frontend_port)
            env["BACKEND_PORT"] = str(backend_port)

            process = subprocess.Popen(
                command,
                shell=True,
                cwd=self.sandbox_path,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
                preexec_fn=os.setsid,
            )

            preview_info = {
                "type": "preview_ready",
                "port": frontend_port,
                "url": f"http://localhost:{frontend_port}",
                "backend_port": backend_port,
                "backend_url": f"http://localhost:{backend_port}",
            }

            self.background_processes[process.pid] = {
                "process": process,
                "command": command,
                "log_filename": log_filename,
                "port": frontend_port,
                "backend_port": backend_port,
                "is_dev_server": True,
            }

            if self.event_callback:
                self.event_callback(preview_info)

            return {
                "status": "started",
                "pid": process.pid,
                "port": frontend_port,
                "backend_port": backend_port,
                "url": f"http://localhost:{frontend_port}",
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def run_background_command(
        self,
        command: str,
        reason: str = "",
        log_filename: str = "server.log",
    ) -> str:
        """Execute a shell command in the background (useful for servers)."""
        err = self._is_command_safe(command)
        if err:
            return err

        is_restart = "restart" in command.lower() or "restart" in reason.lower()
        dev_server_keywords = ["npm run dev", "npm start", "yarn dev", "pnpm dev", "vite"]
        if any(kw in command.lower() for kw in dev_server_keywords):
            res = self.start_dev_server(command=command, log_filename=log_filename, restart=is_restart)
            if res.get("status") == "already_running":
                return (
                    f"Dev server is already running in background (PID {res['pid']}) with Hot Module Replacement (HMR) "
                    f"at {res['url']} (API: {res.get('backend_port')}). All code edits apply automatically."
                )
            elif res.get("status") == "started":
                return f"Started fullstack dev server (PID {res['pid']}) with frontend on port {res['port']} and API on port {res['backend_port']} (URL: {res['url']})."
            else:
                return f"Error starting dev server: {res.get('error')}"

        for pid, info in list(self.background_processes.items()):
            if info["command"] == command and info["process"].poll() is None:
                existing_log = info["log_filename"]
                return f"Command is already running in the background with PID {pid}. Logs are in '{existing_log}'."

        port = self._find_preferred_or_free_port(3000)

        try:
            log_path = self.sandbox_path / log_filename
            log_file = open(log_path, "a")

            env = os.environ.copy()
            env["PORT"] = str(port)

            process = subprocess.Popen(
                command,
                shell=True,
                cwd=self.sandbox_path,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
                preexec_fn=os.setsid,
            )

            self.background_processes[process.pid] = {
                "process": process,
                "command": command,
                "log_filename": log_filename,
                "port": port,
            }

            if self.event_callback:
                self.event_callback({
                    "type": "preview_ready",
                    "port": port,
                    "url": f"http://localhost:{port}",
                })

            return f"Started background process with PID {process.pid} on port {port}. Logs are being written to '{log_filename}'. Use read_file to check its output."
        except Exception as e:
            return f"Error starting background command: {str(e)}"

    def stop_background_command(self, pid: int) -> str:
        """Stop a running background command by its PID."""
        info = self.background_processes.get(pid)
        if not info:
            return f"Error: No background process found with PID {pid}."

        try:
            os.killpg(os.getpgid(info["process"].pid), signal.SIGTERM)
            del self.background_processes[pid]
            if self.event_callback:
                self.event_callback({"type": "preview_stopped"})
            return f"Successfully stopped background process with PID {pid}."
        except Exception as e:
            return f"Error terminating process {pid}: {str(e)}"

    def get_active_processes(self) -> List[Dict[str, Any]]:
        """Returns a list of currently active background processes."""
        active = []
        for pid, info in list(self.background_processes.items()):
            if info["process"].poll() is None:
                active.append({
                    "pid": pid,
                    "command": info["command"],
                    "log_filename": info["log_filename"],
                    "port": info.get("port"),
                    "backend_port": info.get("backend_port"),
                    "is_dev_server": info.get("is_dev_server", False),
                })
        return active

    def cleanup(self):
        """Kill all tracked background processes and their child process groups."""
        had_active = bool(self.background_processes)
        for pid, info in list(self.background_processes.items()):
            try:
                os.killpg(os.getpgid(info["process"].pid), signal.SIGTERM)
            except Exception:
                try:
                    info["process"].terminate()
                except Exception:
                    pass
        self.background_processes.clear()
        if had_active and self.event_callback:
            try:
                self.event_callback({"type": "preview_stopped"})
            except Exception:
                pass
