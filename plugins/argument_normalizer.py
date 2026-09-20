import json
from typing import Dict, Any, List


class ToolArgumentNormalizer:
    """
    Normalizes polymorphic LLM tool-calling argument dictionaries across different model families
    (Qwen, Llama, DeepSeek, Gemma, Mistral) to ensure schema-compliant argument formats.
    """

    @classmethod
    def normalize(cls, name: str, args: Any) -> Dict[str, Any]:
        """Ensures tool arguments are always a valid dictionary matching tool requirements across all models."""
        normalized: Dict[str, Any] = {}

        if isinstance(args, str):
            try:
                parsed = json.loads(args)
                if isinstance(parsed, dict):
                    normalized = dict(parsed)
                elif isinstance(parsed, list):
                    if name == "write_files":
                        normalized = {"files": parsed}
                    else:
                        normalized = {"items": parsed}
            except Exception:
                normalized = {}
        elif isinstance(args, list):
            if name == "write_files":
                normalized = {"files": list(args)}
            else:
                normalized = {"items": list(args)}
        elif isinstance(args, dict):
            normalized = dict(args)
        else:
            normalized = {}

        # 1. Normalize write_files & view_bulk arguments
        if name == "write_files":
            if "files" in normalized:
                f = normalized["files"]
                # If "files": {"test.txt": "content", ...}
                if isinstance(f, dict):
                    normalized["files"] = [{"file_path": k, "content": str(v)} for k, v in f.items()]
                elif isinstance(f, list):
                    # Ensure each element has 'file_path' and 'content'
                    norm_list = []
                    for item in f:
                        if isinstance(item, dict):
                            fp = item.get("file_path") or item.get("path") or item.get("file")
                            c = item.get("content") or item.get("text") or item.get("code") or ""
                            if fp:
                                norm_list.append({"file_path": fp, "content": str(c)})
                    normalized["files"] = norm_list
            else:
                # If normalized itself is a dict mapping filename -> content: {"test.txt": "content"}
                norm_list = []
                for k, v in list(normalized.items()):
                    if isinstance(v, str):
                        norm_list.append({"file_path": k, "content": v})
                    elif isinstance(v, list) and v and isinstance(v[0], dict) and ("file_path" in v[0] or "path" in v[0]):
                        norm_list = [{"file_path": item.get("file_path") or item.get("path"), "content": item.get("content", "")} for item in v]
                        break
                if norm_list:
                    normalized = {"files": norm_list}

        if name == "view_bulk":
            if "files" not in normalized:
                if "paths" in normalized:
                    normalized["files"] = normalized.pop("paths")
                elif "file_paths" in normalized:
                    normalized["files"] = normalized.pop("file_paths")
                elif "items" in normalized:
                    normalized["files"] = normalized.pop("items")
            if "files" in normalized and isinstance(normalized["files"], str):
                try:
                    parsed = json.loads(normalized["files"])
                    normalized["files"] = parsed if isinstance(parsed, list) else [normalized["files"]]
                except Exception:
                    normalized["files"] = [normalized["files"]]

        if name == "glob_files":
            if "pattern" not in normalized:
                if "glob" in normalized:
                    normalized["pattern"] = normalized.pop("glob")
                elif "query" in normalized:
                    normalized["pattern"] = normalized.pop("query")

        # 2. Normalize write_file / edit_file / read_file / insert_text / extract_signatures / mount_file / unmount_file / lint_javascript key aliases
        if name in ["write_file", "edit_file", "read_file", "insert_text", "extract_signatures", "mount_file", "unmount_file", "close_file", "lint_javascript"]:
            if "file_path" not in normalized:
                if "path" in normalized:
                    normalized["file_path"] = normalized.pop("path")
                elif "file" in normalized:
                    normalized["file_path"] = normalized.pop("file")
                elif "target_file" in normalized:
                    normalized["file_path"] = normalized.pop("target_file")
                elif "filepath" in normalized:
                    normalized["file_path"] = normalized.pop("filepath")
                elif "filename" in normalized:
                    normalized["file_path"] = normalized.pop("filename")
                elif "path_pattern" in normalized:
                    normalized["file_path"] = normalized.pop("path_pattern")
                elif "items" in normalized:
                    items_val = normalized.pop("items")
                    if isinstance(items_val, list) and items_val:
                        if isinstance(items_val[0], str):
                            normalized["file_path"] = items_val[0]
                        elif isinstance(items_val[0], dict):
                            normalized["file_path"] = items_val[0].get("file_path") or items_val[0].get("path") or items_val[0].get("file") or "."
                    elif isinstance(items_val, str) and items_val.strip():
                        normalized["file_path"] = items_val.strip()
                elif "files" in normalized:
                    files_val = normalized.pop("files")
                    if isinstance(files_val, list) and files_val:
                        if isinstance(files_val[0], str):
                            normalized["file_path"] = files_val[0]
                        elif isinstance(files_val[0], dict):
                            normalized["file_path"] = files_val[0].get("file_path") or files_val[0].get("path") or files_val[0].get("file") or "."
                    elif isinstance(files_val, str) and files_val.strip():
                        normalized["file_path"] = files_val.strip()

            # Clean up residual empty or redundant batch keys
            if "items" in normalized and not normalized["items"]:
                normalized.pop("items", None)
            if "files" in normalized and not normalized["files"]:
                normalized.pop("files", None)
            if name == "lint_javascript":
                normalized.pop("items", None)
                normalized.pop("files", None)

        if name == "read_file":
            if "start_line" in normalized and not isinstance(normalized["start_line"], int):
                try:
                    normalized["start_line"] = int(normalized["start_line"])
                except (ValueError, TypeError):
                    pass
            if "end_line" in normalized and not isinstance(normalized["end_line"], int) and normalized["end_line"] is not None:
                try:
                    normalized["end_line"] = int(normalized["end_line"])
                except (ValueError, TypeError):
                    pass

        # 3. Normalize map_dependencies aliases to target_file
        if name == "map_dependencies":
            if "target_file" not in normalized:
                if "file_path" in normalized:
                    normalized["target_file"] = normalized.pop("file_path")
                elif "path" in normalized:
                    normalized["target_file"] = normalized.pop("path")
                elif "file" in normalized:
                    normalized["target_file"] = normalized.pop("file")
                elif "filename" in normalized:
                    normalized["target_file"] = normalized.pop("filename")
                elif "filepath" in normalized:
                    normalized["target_file"] = normalized.pop("filepath")


        if name == "locate_files_by_pattern":
            if "directory" not in normalized:
                if "path" in normalized:
                    normalized["directory"] = normalized.pop("path")
                elif "dir" in normalized:
                    normalized["directory"] = normalized.pop("dir")
                elif "folder" in normalized:
                    normalized["directory"] = normalized.pop("folder")
            if "max_depth" not in normalized:
                if "depth" in normalized:
                    normalized["max_depth"] = normalized.pop("depth")
            if "max_depth" in normalized and not isinstance(normalized["max_depth"], int):
                try:
                    normalized["max_depth"] = int(float(normalized["max_depth"]))
                except (ValueError, TypeError):
                    pass
            if "pattern" not in normalized:
                if "glob" in normalized:
                    normalized["pattern"] = normalized.pop("glob")
                elif "query" in normalized:
                    normalized["pattern"] = normalized.pop("query")

        if name == "edit_file":
            if "old_text" not in normalized:
                if "old_str" in normalized:
                    normalized["old_text"] = normalized.pop("old_str")
                elif "search" in normalized:
                    normalized["old_text"] = normalized.pop("search")
            if "new_text" not in normalized:
                if "new_str" in normalized:
                    normalized["new_text"] = normalized.pop("new_str")
                elif "replace" in normalized:
                    normalized["new_text"] = normalized.pop("replace")

        if name == "write_file" and "content" not in normalized:
            if "text" in normalized:
                normalized["content"] = normalized.pop("text")
            elif "code" in normalized:
                normalized["content"] = normalized.pop("code")

        if name == "get_assets":
            if "query" not in normalized:
                if "search_query" in normalized:
                    normalized["query"] = normalized.pop("search_query")
                elif "search" in normalized:
                    normalized["query"] = normalized.pop("search")
                elif "keyword" in normalized:
                    normalized["query"] = normalized.pop("keyword")
                elif "prompt" in normalized:
                    normalized["query"] = normalized.pop("prompt")
            if "count" not in normalized:
                if "image_count" in normalized:
                    normalized["count"] = normalized.pop("image_count")
                elif "limit" in normalized:
                    normalized["count"] = normalized.pop("limit")

        if name == "ask_human":
            if "question" not in normalized:
                if "prompt" in normalized:
                    normalized["question"] = normalized.pop("prompt")
                elif "message" in normalized:
                    normalized["question"] = normalized.pop("message")
                elif "query" in normalized:
                    normalized["question"] = normalized.pop("query")
            if "options" not in normalized:
                if "choices" in normalized:
                    normalized["options"] = normalized.pop("choices")
                elif "items" in normalized:
                    normalized["options"] = normalized.pop("items")
            if "options" in normalized and isinstance(normalized["options"], str):
                try:
                    parsed = json.loads(normalized["options"])
                    normalized["options"] = parsed if isinstance(parsed, list) else [normalized["options"]]
                except Exception:
                    normalized["options"] = [normalized["options"]]

        if name == "finish":
            if "summary" not in normalized:
                if "message" in normalized:
                    normalized["summary"] = normalized.pop("message")
                elif "result" in normalized:
                    normalized["summary"] = normalized.pop("result")
                elif "outcome" in normalized:
                    normalized["summary"] = normalized.pop("outcome")
                elif "text" in normalized:
                    normalized["summary"] = normalized.pop("text")
                elif "description" in normalized:
                    normalized["summary"] = normalized.pop("description")
                elif "work_done" in normalized:
                    normalized["summary"] = normalized.pop("work_done")

        if name == "invoke_design_agent":
            if "problem_statement" not in normalized:
                if "prompt" in normalized:
                    normalized["problem_statement"] = normalized.pop("prompt")
                elif "original_problem_statement" in normalized:
                    normalized["problem_statement"] = normalized.pop("original_problem_statement")
                elif "query" in normalized:
                    normalized["problem_statement"] = normalized.pop("query")
                elif "requirements" in normalized:
                    normalized["problem_statement"] = normalized.pop("requirements")
                elif "user_prompt" in normalized:
                    normalized["problem_statement"] = normalized.pop("user_prompt")
            if "app_type" not in normalized:
                if "type" in normalized:
                    normalized["app_type"] = normalized.pop("type")
                elif "category" in normalized:
                    normalized["app_type"] = normalized.pop("category")
            if "theme_preference" not in normalized:
                if "theme" in normalized:
                    normalized["theme_preference"] = normalized.pop("theme")
                elif "user_choices" in normalized:
                    normalized["theme_preference"] = normalized.pop("user_choices")
                elif "style" in normalized:
                    normalized["theme_preference"] = normalized.pop("style")

        if name == "invoke_troubleshoot_agent":
            if "error_log" not in normalized:
                if "error" in normalized:
                    normalized["error_log"] = normalized.pop("error")
                elif "log" in normalized:
                    normalized["error_log"] = normalized.pop("log")
                elif "stack_trace" in normalized:
                    normalized["error_log"] = normalized.pop("stack_trace")
                elif "error_messages" in normalized:
                    normalized["error_log"] = normalized.pop("error_messages")
                elif "issue" in normalized:
                    normalized["error_log"] = normalized.pop("issue")
            if "context_file" not in normalized:
                if "file" in normalized:
                    normalized["context_file"] = normalized.pop("file")
                elif "file_path" in normalized:
                    normalized["context_file"] = normalized.pop("file_path")
                elif "relevant_files" in normalized:
                    normalized["context_file"] = normalized.pop("relevant_files")
            if "recent_actions" not in normalized:
                if "actions" in normalized:
                    normalized["recent_actions"] = normalized.pop("actions")
                elif "previous_actions" in normalized:
                    normalized["recent_actions"] = normalized.pop("previous_actions")

        if name == "invoke_vision_agent":
            if "target_component_or_file" not in normalized:
                if "component" in normalized:
                    normalized["target_component_or_file"] = normalized.pop("component")
                elif "file" in normalized:
                    normalized["target_component_or_file"] = normalized.pop("file")
                elif "target_file" in normalized:
                    normalized["target_component_or_file"] = normalized.pop("target_file")
                elif "file_path" in normalized:
                    normalized["target_component_or_file"] = normalized.pop("file_path")
            if "design_intent" not in normalized:
                if "intent" in normalized:
                    normalized["design_intent"] = normalized.pop("intent")
                elif "requirements" in normalized:
                    normalized["design_intent"] = normalized.pop("requirements")
                elif "prompt" in normalized:
                    normalized["design_intent"] = normalized.pop("prompt")
                elif "aesthetic" in normalized:
                    normalized["design_intent"] = normalized.pop("aesthetic")
            if "screenshot_base64" not in normalized:
                if "screenshot" in normalized:
                    normalized["screenshot_base64"] = normalized.pop("screenshot")
                elif "image" in normalized:
                    normalized["screenshot_base64"] = normalized.pop("image")

        if name == "invoke_testing_agent":
            if "instructions" not in normalized:
                if "instruction" in normalized:
                    normalized["instructions"] = normalized.pop("instruction")
                elif "prompt" in normalized:
                    normalized["instructions"] = normalized.pop("prompt")
                elif "test_plan" in normalized:
                    normalized["instructions"] = normalized.pop("test_plan")
            if "url" not in normalized:
                if "link" in normalized:
                    normalized["url"] = normalized.pop("link")
                elif "endpoint" in normalized:
                    normalized["url"] = normalized.pop("endpoint")
                elif "target_url" in normalized:
                    normalized["url"] = normalized.pop("target_url")
                else:
                    normalized["url"] = ""

        if name == "invoke_code_reviewer_agent":
            if "target_files" not in normalized:
                if "files" in normalized:
                    normalized["target_files"] = normalized.pop("files")
                elif "file_paths" in normalized:
                    normalized["target_files"] = normalized.pop("file_paths")
                elif "file_path" in normalized:
                    normalized["target_files"] = normalized.pop("file_path")
                elif "file" in normalized:
                    normalized["target_files"] = normalized.pop("file")
                elif "targets" in normalized:
                    normalized["target_files"] = normalized.pop("targets")
            if "focus_areas" not in normalized:
                if "focus" in normalized:
                    normalized["focus_areas"] = normalized.pop("focus")
                elif "areas" in normalized:
                    normalized["focus_areas"] = normalized.pop("areas")
                elif "scope" in normalized:
                    normalized["focus_areas"] = normalized.pop("scope")

        if name in ["execute_command", "run_background_command"] and "command" not in normalized:
            if "cmd" in normalized:
                normalized["command"] = normalized.pop("cmd")

        return normalized
