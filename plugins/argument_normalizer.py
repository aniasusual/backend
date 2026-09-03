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
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}

        if isinstance(args, list):
            if name == "write_files":
                args = {"files": args}
            else:
                args = {"items": args}
        elif not isinstance(args, dict):
            args = {}

        # 1. Normalize write_files & view_bulk arguments
        if name == "write_files":
            if "files" in args:
                f = args["files"]
                # If "files": {"test.txt": "content", ...}
                if isinstance(f, dict):
                    args["files"] = [{"file_path": k, "content": str(v)} for k, v in f.items()]
                elif isinstance(f, list):
                    # Ensure each element has 'file_path' and 'content'
                    norm_list = []
                    for item in f:
                        if isinstance(item, dict):
                            fp = item.get("file_path") or item.get("path") or item.get("file")
                            c = item.get("content") or item.get("text") or item.get("code") or ""
                            if fp:
                                norm_list.append({"file_path": fp, "content": str(c)})
                    args["files"] = norm_list
            else:
                # If args itself is a dict mapping filename -> content: {"test.txt": "content"}
                norm_list = []
                for k, v in list(args.items()):
                    if isinstance(v, str):
                        norm_list.append({"file_path": k, "content": v})
                    elif isinstance(v, list) and v and isinstance(v[0], dict) and ("file_path" in v[0] or "path" in v[0]):
                        norm_list = [{"file_path": item.get("file_path") or item.get("path"), "content": item.get("content", "")} for item in v]
                        break
                if norm_list:
                    args = {"files": norm_list}

        if name == "view_bulk":
            if "files" not in args:
                if "paths" in args:
                    args["files"] = args.pop("paths")
                elif "file_paths" in args:
                    args["files"] = args.pop("file_paths")
                elif "items" in args:
                    args["files"] = args.pop("items")
            if "files" in args and isinstance(args["files"], str):
                try:
                    parsed = json.loads(args["files"])
                    args["files"] = parsed if isinstance(parsed, list) else [args["files"]]
                except Exception:
                    args["files"] = [args["files"]]

        if name == "glob_files":
            if "pattern" not in args:
                if "glob" in args:
                    args["pattern"] = args.pop("glob")
                elif "query" in args:
                    args["pattern"] = args.pop("query")

        # 2. Normalize write_file / edit_file / read_file / lint_javascript key aliases
        if name in ["write_file", "edit_file", "read_file", "insert_text", "lint_javascript"]:
            if "file_path" not in args:
                if "path" in args:
                    args["file_path"] = args.pop("path")
                elif "file" in args:
                    args["file_path"] = args.pop("file")
                elif "filename" in args:
                    args["file_path"] = args.pop("filename")
                elif "path_pattern" in args:
                    args["file_path"] = args.pop("path_pattern")

        if name == "edit_file":
            if "old_text" not in args:
                if "old_str" in args:
                    args["old_text"] = args.pop("old_str")
                elif "search" in args:
                    args["old_text"] = args.pop("search")
            if "new_text" not in args:
                if "new_str" in args:
                    args["new_text"] = args.pop("new_str")
                elif "replace" in args:
                    args["new_text"] = args.pop("replace")

        if name == "write_file" and "content" not in args:
            if "text" in args:
                args["content"] = args.pop("text")
            elif "code" in args:
                args["content"] = args.pop("code")

        if name in ["get_assets", "get_assets_tool"]:
            if "query" not in args:
                if "search_query" in args:
                    args["query"] = args.pop("search_query")
                elif "search" in args:
                    args["query"] = args.pop("search")
                elif "keyword" in args:
                    args["query"] = args.pop("keyword")
                elif "prompt" in args:
                    args["query"] = args.pop("prompt")
            if "count" not in args:
                if "image_count" in args:
                    args["count"] = args.pop("image_count")
                elif "limit" in args:
                    args["count"] = args.pop("limit")

        if name == "ask_human":
            if "question" not in args:
                if "prompt" in args:
                    args["question"] = args.pop("prompt")
                elif "message" in args:
                    args["question"] = args.pop("message")
                elif "query" in args:
                    args["question"] = args.pop("query")
            if "options" not in args:
                if "choices" in args:
                    args["options"] = args.pop("choices")
                elif "items" in args:
                    args["options"] = args.pop("items")
            if "options" in args and isinstance(args["options"], str):
                try:
                    parsed = json.loads(args["options"])
                    args["options"] = parsed if isinstance(parsed, list) else [args["options"]]
                except Exception:
                    args["options"] = [args["options"]]

        if name == "finish":
            if "summary" not in args:
                if "message" in args:
                    args["summary"] = args.pop("message")
                elif "result" in args:
                    args["summary"] = args.pop("result")
                elif "outcome" in args:
                    args["summary"] = args.pop("outcome")
                elif "text" in args:
                    args["summary"] = args.pop("text")
                elif "description" in args:
                    args["summary"] = args.pop("description")
                elif "work_done" in args:
                    args["summary"] = args.pop("work_done")

        if name in ["invoke_design_agent", "design_agent"]:
            if "problem_statement" not in args:
                if "prompt" in args:
                    args["problem_statement"] = args.pop("prompt")
                elif "original_problem_statement" in args:
                    args["problem_statement"] = args.pop("original_problem_statement")
                elif "query" in args:
                    args["problem_statement"] = args.pop("query")
                elif "requirements" in args:
                    args["problem_statement"] = args.pop("requirements")
                elif "user_prompt" in args:
                    args["problem_statement"] = args.pop("user_prompt")
            if "app_type" not in args:
                if "type" in args:
                    args["app_type"] = args.pop("type")
                elif "category" in args:
                    args["app_type"] = args.pop("category")
            if "theme_preference" not in args:
                if "theme" in args:
                    args["theme_preference"] = args.pop("theme")
                elif "user_choices" in args:
                    args["theme_preference"] = args.pop("user_choices")
                elif "style" in args:
                    args["theme_preference"] = args.pop("style")

        if name in ["invoke_troubleshoot_agent", "troubleshoot_agent"]:
            if "error_log" not in args:
                if "error" in args:
                    args["error_log"] = args.pop("error")
                elif "log" in args:
                    args["error_log"] = args.pop("log")
                elif "stack_trace" in args:
                    args["error_log"] = args.pop("stack_trace")
                elif "error_messages" in args:
                    args["error_log"] = args.pop("error_messages")
                elif "issue" in args:
                    args["error_log"] = args.pop("issue")
            if "context_file" not in args:
                if "file" in args:
                    args["context_file"] = args.pop("file")
                elif "file_path" in args:
                    args["context_file"] = args.pop("file_path")
                elif "relevant_files" in args:
                    args["context_file"] = args.pop("relevant_files")
            if "recent_actions" not in args:
                if "actions" in args:
                    args["recent_actions"] = args.pop("actions")
                elif "previous_actions" in args:
                    args["recent_actions"] = args.pop("previous_actions")

        if name in ["invoke_vision_agent", "vision_agent"]:
            if "target_component_or_file" not in args:
                if "component" in args:
                    args["target_component_or_file"] = args.pop("component")
                elif "file" in args:
                    args["target_component_or_file"] = args.pop("file")
                elif "target_file" in args:
                    args["target_component_or_file"] = args.pop("target_file")
                elif "file_path" in args:
                    args["target_component_or_file"] = args.pop("file_path")
            if "design_intent" not in args:
                if "intent" in args:
                    args["design_intent"] = args.pop("intent")
                elif "requirements" in args:
                    args["design_intent"] = args.pop("requirements")
                elif "prompt" in args:
                    args["design_intent"] = args.pop("prompt")
                elif "aesthetic" in args:
                    args["design_intent"] = args.pop("aesthetic")
            if "screenshot_base64" not in args:
                if "screenshot" in args:
                    args["screenshot_base64"] = args.pop("screenshot")
                elif "image" in args:
                    args["screenshot_base64"] = args.pop("image")

        if name in ["execute_command", "run_background_command"] and "command" not in args:
            if "cmd" in args:
                args["command"] = args.pop("cmd")

        return args
