# Explicit JSON tool schemas for Ollama tool calling

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file with line numbers, optionally sliced by a line range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The relative path to the file to read.",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Optional 1-indexed starting line number (default: 1).",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Optional 1-indexed ending line number (default: end of file).",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_bulk",
            "description": "View the contents of multiple files in a single batched operation. Ideal for exploring and reading multiple components in 1 turn.",
            "parameters": {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "description": "List of relative file paths to view in bulk (e.g. ['src/App.jsx', 'server/index.js']).",
                        "items": {
                            "type": "string",
                        },
                    },
                },
                "required": ["files"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob_files",
            "description": "Find files matching a glob pattern across workspace directories (e.g. 'src/**/*.jsx', 'server/**/*.js', '*.json'). Respects ignore rules.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "The glob pattern to match files against (e.g. '*.js', 'src/**/*.jsx').",
                    },
                    "path": {
                        "type": "string",
                        "description": "The relative directory to search within (default: current workspace root).",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_search",
            "description": "Search for a keyword or regex pattern across workspace files. Returns matching lines and line numbers (~20 tokens).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search term or regex pattern to look for.",
                    },
                    "path": {
                        "type": "string",
                        "description": "The relative path or directory to search within (default: entire workspace).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a single file, creating it and any parent directories if they don't exist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The relative path to the file to write.",
                    },
                    "content": {
                        "type": "string",
                        "description": "The full content to write to the file.",
                    },
                },
                "required": ["file_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_files",
            "description": "Write content to multiple files in a single atomic batch operation. Ideal for generating fullstack apps and multiple components in 1 turn.",
            "parameters": {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "description": "List of file objects with 'file_path' and 'content'.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "file_path": {
                                    "type": "string",
                                    "description": "The relative path to the file to write.",
                                },
                                "content": {
                                    "type": "string",
                                    "description": "The full content to write to the file.",
                                },
                            },
                            "required": ["file_path", "content"],
                        },
                    },
                },
                "required": ["files"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "insert_text",
            "description": "Insert text directly after a specific 1-indexed line number in a file without needing string matching.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The relative path to the file to modify.",
                    },
                    "line_number": {
                        "type": "integer",
                        "description": "The 1-indexed line number after which to insert the text (0 to insert at the top).",
                    },
                    "text": {
                        "type": "string",
                        "description": "The text to insert.",
                    },
                },
                "required": ["file_path", "line_number", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Edit a file by replacing a specific code snippet with new text (whitespace and indentation tolerant). Supports replace_all for global symbol renames.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The relative path to the file to edit.",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "The code snippet to find and replace.",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "The replacement code.",
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "Replace all occurrences of old_text across the file (default: false). Use this to rename variables, components, or imports.",
                    },
                },
                "required": ["file_path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List the contents of a directory, showing files and subdirectories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The relative path to the directory. Defaults to current directory.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lint_javascript",
            "description": "Run a static syntax and import validation check on JavaScript/JSX/TypeScript files to verify code correctness before testing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The relative file path or directory to lint (e.g. 'src/App.jsx', 'server/index.js', 'src'). Defaults to whole workspace.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_assets",
            "description": "Fetch verified, working Unsplash CDN image URLs, local project media, and Lucide React icon names to build rich UI without broken links or placeholders.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords describing the asset or topic (e.g. 'avatar', 'tech hero', 'dashboard analytics', 'sneaker product', 'burger', 'finance').",
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional category filter: 'avatar', 'hero', 'product', 'finance', 'food', 'nature'.",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of asset suggestions to return (default: 5).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_human",
            "description": "Ask the human user a clarifying question ONLY when requirements are fundamentally ambiguous between mutually exclusive options. NEVER call this tool to ask for permission to start, proceed, or write code. You have full autonomous authority to write and modify files directly.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The question or prompt to ask the user.",
                    },
                    "options": {
                        "type": "array",
                        "description": "Optional list of selectable option strings to make user response easy.",
                        "items": {
                            "type": "string",
                        },
                    },
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Call ONLY when all application code files (src/App.jsx, server/index.js, etc.) have been completely written, implemented, and verified on disk. NEVER call finish immediately after invoke_design_agent or before writing the actual React and Express code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Detailed summary of all completed tasks, files created/modified, and verification status.",
                    },
                    "next_steps": {
                        "type": "string",
                        "description": "Optional recommended next steps for the user (e.g. how to test or run).",
                    },
                },
                "required": ["summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "invoke_design_agent",
            "description": "Invoke the specialized UI/UX Design Subagent to generate award-winning design systems, color tokens, Google Font typography scales, and component blueprints.",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_statement": {
                        "type": "string",
                        "description": "Raw problem statement or requirements from the user describing the desired app.",
                    },
                    "app_type": {
                        "type": "string",
                        "description": "The category of app (e.g. 'dashboard', 'ecommerce', 'saas_app', 'portfolio', 'landing_page', 'fintech', 'healthcare').",
                    },
                    "theme_preference": {
                        "type": "string",
                        "description": "Optional user visual preferences (e.g. 'dark mode', 'glassmorphism', 'emerald finance', 'cyberpunk neon').",
                    },
                },
                "required": ["problem_statement"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "invoke_troubleshoot_agent",
            "description": "Invoke the specialized Troubleshoot Subagent to perform deep root cause analysis (RCA) on error logs, stack traces, Vite build failures, and crashes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "error_log": {
                        "type": "string",
                        "description": "The exact compiler output, runtime stack trace, or error message to diagnose.",
                    },
                    "context_file": {
                        "type": "string",
                        "description": "Optional relative path to the file suspected of causing the error (e.g. 'src/App.jsx').",
                    },
                    "recent_actions": {
                        "type": "string",
                        "description": "Optional brief description of what was done right before the error occurred.",
                    },
                },
                "required": ["error_log"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "invoke_vision_agent",
            "description": "Invoke the specialized Vision Expert Subagent to audit UI layout balance, visual hierarchy, color contrast ratios, and micro-interactions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_component_or_file": {
                        "type": "string",
                        "description": "Optional relative path to the UI component file to audit (e.g. 'src/App.jsx').",
                    },
                    "screenshot_base64": {
                        "type": "string",
                        "description": "Optional base64 encoded screenshot image string of the rendered UI.",
                    },
                    "design_intent": {
                        "type": "string",
                        "description": "Optional description of the desired design aesthetic or user requirements.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "Execute a short-lived shell command in the project directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "A short explanation of why this command needs to be executed.",
                    }
                },
                "required": ["command", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_background_command",
            "description": "Run a long-running process (such as a web server or dev server) in the background.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to start in the background.",
                    },
                    "log_filename": {
                        "type": "string",
                        "description": "Log filename to append output to (default: server.log).",
                    },
                    "reason": {
                        "type": "string",
                        "description": "A short explanation of why this command needs to be executed in the background.",
                    }
                },
                "required": ["command", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stop_background_command",
            "description": "Stop a running background process by its PID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pid": {
                        "type": "integer",
                        "description": "The process ID (PID) of the background command to terminate.",
                    }
                },
                "required": ["pid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "test_ui",
            "description": "Run an automated UI testing subagent on a URL to verify interactive functionality.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to test (e.g. 'http://localhost:5000').",
                    },
                    "instructions": {
                        "type": "string",
                        "description": "Detailed plain-text instructions on what to test.",
                    },
                },
                "required": ["url", "instructions"],
            },
        },
    },
]
