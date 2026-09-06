import os
import re
from pathlib import Path
from typing import Dict, Any, Callable, List, Optional


class FileTools:
    """
    Dedicated handler for safe workspace file operations (reading, globbing,
    bulk viewing, precision search, atomic writing, line insertion, and resilient editing).
    """

    def __init__(
        self,
        sandbox_path: Path,
        is_safe_path_fn: Callable[[str], bool],
        event_callback: Optional[Callable[[dict], None]] = None,
    ):
        self.sandbox_path = sandbox_path
        self._is_safe_path = is_safe_path_fn
        self.event_callback = event_callback

    def read_file(self, file_path: str, start_line: int = 1, end_line: int = None) -> str:
        """Read the contents of a file with line numbers, optionally sliced by line range.

        Args:
            file_path: The relative path to the file to read.
            start_line: Optional 1-indexed starting line number (default: 1).
            end_line: Optional 1-indexed ending line number (default: end of file).

        Returns:
            The numbered lines of the file as a formatted string.
        """
        if not self._is_safe_path(file_path):
            return f"Error: Access denied to path outside sandbox: {file_path}"

        target = self.sandbox_path / file_path
        if not target.exists():
            return f"Error: File not found: {file_path}"
        if target.is_dir():
            return f"Error: {file_path} is a directory. Use list_directory instead."

        try:
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)
            if total_lines == 0:
                return f"[{file_path} is empty (0 lines)]"

            start_idx = max(1, int(start_line) if start_line is not None else 1) - 1
            if end_line is None or int(end_line) < 0:
                end_idx = total_lines
            else:
                end_idx = min(total_lines, max(start_idx + 1, int(end_line)))

            if start_idx >= total_lines:
                return f"Error: start_line {start_line} exceeds total lines ({total_lines}) in {file_path}"

            selected_lines = lines[start_idx:end_idx]
            formatted = []
            for i, line in enumerate(selected_lines, start=start_idx + 1):
                formatted.append(f"{i:4d} | {line.rstrip(chr(13) + chr(10))}")

            header = f"[{file_path} (lines {start_idx + 1}-{end_idx} of {total_lines})]:\n"
            return header + "\n".join(formatted)
        except Exception as e:
            return f"Error reading file: {str(e)}"

    def view_bulk(self, files: Any = None, **kwargs) -> str:
        """View the contents of multiple files in a single batched operation.

        Args:
            files: A list of relative file paths to view (e.g. ['src/App.jsx', 'server/index.js']).

        Returns:
            Consolidated formatted view of all requested files with numbered lines.
        """
        if files is None and "paths" in kwargs:
            files = kwargs["paths"]
        elif files is None and "items" in kwargs:
            files = kwargs["items"]
        elif files is None and "file_paths" in kwargs:
            files = kwargs["file_paths"]

        if isinstance(files, str):
            try:
                import json
                parsed = json.loads(files)
                if isinstance(parsed, list):
                    files = parsed
                else:
                    files = [files]
            except Exception:
                files = [files]

        if not files or not isinstance(files, list):
            return "Error: 'files' must be a non-empty list of relative file paths."

        file_list = files[:15]
        output_blocks = []

        for item in file_list:
            if not isinstance(item, str):
                if isinstance(item, dict) and ("file_path" in item or "path" in item):
                    file_path = item.get("file_path") or item.get("path")
                else:
                    continue
            else:
                file_path = item.strip()

            if not file_path:
                continue

            if not self._is_safe_path(file_path):
                output_blocks.append(f"=== [{file_path}] ===\nError: Access denied to path outside sandbox.")
                continue

            target = (self.sandbox_path / file_path).resolve()
            if not target.exists():
                output_blocks.append(f"=== [{file_path}] ===\nError: File not found.")
                continue

            if target.is_dir():
                try:
                    entries = [
                        f"  [DIR]  {e.name}/" if e.is_dir() else f"  [FILE] {e.name} ({e.stat().st_size} bytes)"
                        for e in sorted(target.iterdir())
                    ]
                    listing = "\n".join(entries) if entries else "  (empty directory)"
                    output_blocks.append(f"=== [DIR: {file_path}] ===\n{listing}")
                except Exception as e:
                    output_blocks.append(f"=== [DIR: {file_path}] ===\nError listing directory: {str(e)}")
                continue

            try:
                with open(target, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()

                total_lines = len(lines)
                if total_lines == 0:
                    output_blocks.append(f"=== [{file_path} (0 lines)] ===\n[File is empty]")
                    continue

                max_lines = 500
                display_lines = lines[:max_lines]
                formatted = [
                    f"{i:4d} | {line.rstrip(chr(13) + chr(10))}"
                    for i, line in enumerate(display_lines, start=1)
                ]

                header = f"=== [{file_path} (lines 1-{len(display_lines)} of {total_lines})] ==="
                if total_lines > max_lines:
                    formatted.append(f"... ({total_lines - max_lines} more lines not shown. Use read_file to view specific line ranges.)")

                output_blocks.append(header + "\n" + "\n".join(formatted))
            except Exception as e:
                output_blocks.append(f"=== [{file_path}] ===\nError reading file: {str(e)}")

        if not output_blocks:
            return "No valid file paths provided to view_bulk."

        return "\n\n".join(output_blocks)

    def glob_files(self, pattern: str, path: str = ".") -> str:
        """Find files matching a glob pattern across workspace directories.
        Supports patterns like *.jsx, src/**/*.js, **/*.css while respecting standard ignore rules.

        Args:
            pattern: The glob pattern to match files against (e.g. '*.js', 'src/**/*.jsx').
            path: The relative directory to search within (default: sandbox root).

        Returns:
            A formatted list of matching relative file paths, or a notification if no matches found.
        """
        if not pattern or not pattern.strip():
            return "Error: pattern parameter must not be empty."

        clean_pattern = pattern.strip()
        search_path = path

        if "/" in clean_pattern and not clean_pattern.startswith("**"):
            parts = clean_pattern.rsplit("/", 1)
            sub_dir = parts[0]
            clean_pattern = parts[1]
            if search_path == ".":
                search_path = sub_dir
            else:
                search_path = f"{search_path.rstrip('/')}/{sub_dir}"

        if not self._is_safe_path(search_path):
            return f"Error: Access denied to path outside sandbox: {search_path}"

        search_root = (self.sandbox_path / search_path).resolve()
        if not search_root.exists():
            return f"Error: Search directory not found: {search_path}"
        if not search_root.is_dir():
            return f"Error: Search path '{search_path}' is a file, not a directory."

        ignore_dirs = {".git", "node_modules", "dist", "build", "venv", ".next", "__pycache__", ".cache"}

        try:
            matches = []
            if clean_pattern.startswith("**"):
                raw_pattern = clean_pattern[2:].lstrip("/") if clean_pattern != "**" else "*"
                generator = search_root.rglob(raw_pattern if raw_pattern else "*")
            else:
                generator = search_root.rglob(clean_pattern) if "/" not in clean_pattern else search_root.glob(clean_pattern)

            for item in sorted(generator):
                if any(part in ignore_dirs for part in item.parts):
                    continue
                if item.is_file():
                    rel_path = item.relative_to(self.sandbox_path)
                    matches.append(str(rel_path))
                    if len(matches) >= 100:
                        break

            seen = set()
            unique_matches = []
            for m in matches:
                if m not in seen:
                    seen.add(m)
                    unique_matches.append(m)

            if not unique_matches:
                return f"No files matching pattern '{pattern}' found in '{path}'."

            result = f"Found {len(unique_matches)} file(s) matching '{pattern}' in '{path}':\n" + "\n".join(f"- {m}" for m in unique_matches)
            if len(unique_matches) >= 100:
                result += "\n... (results capped at 100 files)"
            return result
        except Exception as e:
            return f"Error matching glob pattern '{pattern}': {str(e)}"

    def grep_search(self, query: str, path: str = ".", case_sensitive: bool = False) -> str:
        """Search for a keyword or regex pattern across workspace files.

        Args:
            query: The search term or pattern to look for.
            path: Relative path or directory to search within (default: entire workspace).
            case_sensitive: Whether the search should be case sensitive (default: False).

        Returns:
            Formatted matches showing file path, line numbers, and matching code lines.
        """
        if not query or not query.strip():
            return "Error: query parameter must not be empty."

        search_root = (self.sandbox_path / path).resolve()
        if not self._is_safe_path(path):
            return f"Error: Access denied to path outside sandbox: {path}"
        if not search_root.exists():
            return f"Error: Search path does not exist: {path}"

        ignore_dirs = {".git", "node_modules", "dist", "build", "venv", ".next", "__pycache__", ".cache"}
        ignore_exts = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".woff", ".woff2", ".ttf", ".eot", ".zip", ".tar", ".gz", ".lock"}

        matches = []
        pattern_flags = 0 if case_sensitive else re.IGNORECASE
        try:
            compiled_regex = re.compile(query, pattern_flags)
        except re.error:
            compiled_regex = re.compile(re.escape(query), pattern_flags)

        files_to_search = []
        if search_root.is_file():
            files_to_search.append(search_root)
        else:
            for root, dirs, files in os.walk(search_root):
                dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
                for f in files:
                    if not any(f.endswith(ext) for ext in ignore_exts):
                        files_to_search.append(Path(root) / f)

        for filepath in files_to_search:
            try:
                rel_path = filepath.relative_to(self.sandbox_path)
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    for line_num, line in enumerate(f, 1):
                        if compiled_regex.search(line):
                            matches.append(f"{rel_path}:{line_num}: {line.strip()}")
                            if len(matches) >= 50:
                                break
            except Exception:
                continue
            if len(matches) >= 50:
                break

        if not matches:
            return f"No matches found for '{query}' in {path}."

        result = f"Found {len(matches)} match(es) for '{query}':\n" + "\n".join(matches)
        if len(matches) >= 50:
            result += "\n... (results capped at 50 matches)"
        return result

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
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)
            if self.event_callback:
                self.event_callback({"type": "file_changed", "file": file_path})
            return f"Successfully wrote to {file_path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

    def write_files(self, files: Any = None, **kwargs) -> str:
        """Write content to multiple files in a single atomic batch operation.

        Args:
            files: A list of objects with 'file_path' and 'content' keys.

        Returns:
            A summary of all successfully written files or an error message.
        """
        if files is None and "files" in kwargs:
            files = kwargs["files"]
        elif files is None and "items" in kwargs:
            files = kwargs["items"]

        if not files or not isinstance(files, list):
            return "Error: 'files' must be a non-empty list of objects with 'file_path' and 'content'."

        validated = []
        for idx, item in enumerate(files):
            if not isinstance(item, dict):
                return f"Error: Item at index {idx} is not a valid object."
            file_path = item.get("file_path")
            content = item.get("content")
            if not file_path or content is None:
                return f"Error: Item at index {idx} is missing 'file_path' or 'content'."
            if not self._is_safe_path(file_path):
                return f"Error: Access denied to path outside sandbox: {file_path}"
            validated.append((file_path, content))

        written_paths = []
        try:
            for file_path, content in validated:
                target = self.sandbox_path / file_path
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(target, "w", encoding="utf-8") as f:
                    f.write(content)
                written_paths.append(file_path)

            if self.event_callback:
                self.event_callback({"type": "file_changed", "files": written_paths, "file": written_paths[-1] if written_paths else ""})

            return f"Successfully wrote {len(written_paths)} files: {', '.join(written_paths)}"
        except Exception as e:
            return f"Error writing batch files: {str(e)}"

    def insert_text(self, file_path: str, line_number: int, text: str) -> str:
        """Insert text after a specific line number in a file without needing old_text string matching.

        Args:
            file_path: The relative path to the file to modify.
            line_number: 1-indexed line number after which to insert the text (use 0 for top of file).
            text: The text string to insert.

        Returns:
            A success or error message.
        """
        if not self._is_safe_path(file_path):
            return f"Error: Access denied to path outside sandbox: {file_path}"

        target = self.sandbox_path / file_path
        if not target.exists():
            return f"Error: File not found: {file_path}"

        try:
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)
            line_num_int = int(line_number) if line_number is not None else total_lines
            idx = max(0, min(line_num_int, total_lines))

            insert_str = text if text.endswith("\n") else text + "\n"
            lines.insert(idx, insert_str)

            with open(target, "w", encoding="utf-8") as f:
                f.writelines(lines)

            if self.event_callback:
                self.event_callback({"type": "file_changed", "file": file_path})

            return f"Successfully inserted text after line {line_num_int} in {file_path} (new total lines: {len(lines)})"
        except Exception as e:
            return f"Error inserting text: {str(e)}"

    def edit_file(self, file_path: str, old_text: str, new_text: str, replace_all: bool = False) -> str:
        """Edit a file by replacing specific text with new text.
        Supports single replacement or global replace_all, with whitespace & indentation normalization.

        Args:
            file_path: The relative path to the file to edit.
            old_text: The exact text or pattern to find and replace.
            new_text: The replacement text.
            replace_all: When True, replaces all occurrences across the file (ideal for variable/class renames).

        Returns:
            A success or diagnostic error message.
        """
        if not self._is_safe_path(file_path):
            return f"Error: Access denied to path outside sandbox: {file_path}"

        target = self.sandbox_path / file_path
        if not target.exists():
            return f"Error: File not found: {file_path}"

        try:
            content = target.read_text(encoding="utf-8")

            # Stage 1: Exact Substring Matching
            if old_text in content:
                count = content.count(old_text)
                if replace_all:
                    updated = content.replace(old_text, new_text)
                    target.write_text(updated, encoding="utf-8")
                    if self.event_callback:
                        self.event_callback({"type": "file_changed", "file": file_path})
                    return f"Successfully edited {file_path} (replaced all {count} occurrences)"
                else:
                    updated = content.replace(old_text, new_text, 1)
                    target.write_text(updated, encoding="utf-8")
                    if self.event_callback:
                        self.event_callback({"type": "file_changed", "file": file_path})
                    return f"Successfully edited {file_path}"

            # Stage 2: Whitespace & Indentation Normalized Matching
            def normalize_line(line: str) -> str:
                return re.sub(r"\s+", " ", line.strip())

            old_lines_norm = [normalize_line(l) for l in old_text.splitlines() if l.strip()]
            content_lines = content.splitlines()
            content_lines_norm = [normalize_line(l) for l in content_lines]

            if old_lines_norm:
                matched_indices = []
                match_len = len(old_lines_norm)

                for i in range(len(content_lines_norm) - match_len + 1):
                    window = [l for l in content_lines_norm[i : i + match_len] if l]
                    if len(window) != match_len:
                        continue

                    window_quotes = [l.replace("'", '"') for l in window]
                    target_quotes = [l.replace("'", '"') for l in old_lines_norm]

                    if window == old_lines_norm or window_quotes == target_quotes:
                        matched_indices.append(i)
                        if not replace_all:
                            break

                if matched_indices:
                    # Apply replacements (in reverse order if replace_all to keep indices valid)
                    new_replacement_lines = new_text.splitlines()
                    updated_lines = list(content_lines)

                    for matched_start in reversed(matched_indices):
                        first_orig_line = content_lines[matched_start]
                        m = re.match(r"^\s*", first_orig_line)
                        indent = m.group(0) if m is not None else ""

                        formatted_replacement = [
                            indent + l if l.strip() else l for l in new_replacement_lines
                        ]
                        updated_lines = (
                            updated_lines[:matched_start]
                            + formatted_replacement
                            + updated_lines[matched_start + match_len :]
                        )

                    has_trailing_nl = content.endswith("\n")
                    updated = "\n".join(updated_lines) + ("\n" if has_trailing_nl else "")

                    target.write_text(updated, encoding="utf-8")
                    if self.event_callback:
                        self.event_callback({"type": "file_changed", "file": file_path})

                    if len(matched_indices) > 1 and replace_all:
                        return f"Successfully edited {file_path} (matched and replaced {len(matched_indices)} occurrences with whitespace tolerance)"
                    return f"Successfully edited {file_path} (matched with whitespace tolerance at line {matched_indices[0] + 1})"

            first_line_preview = old_text.splitlines()[0][:30] if old_text else ""
            return (
                f"Error: The specified old_text was not found in {file_path}.\n"
                f"Tips: Use grep_search('{first_line_preview}') to find the line number, "
                f"or read_file('{file_path}') to view exact lines, "
                f"or insert_text('{file_path}', line_number, text) to insert without matching."
            )
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
