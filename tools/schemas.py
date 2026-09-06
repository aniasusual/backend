# Explicit JSON tool schemas for Ollama tool calling

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file with line numbers, optionally sliced by a line range. Use this before edit_file to inspect exact lines and surrounding code context.",
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
            "description": "View the contents of multiple files in a single batched operation. Ideal for exploring package.json, server/index.js, and src/App.jsx in 1 turn without multiple calls.",
            "parameters": {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "description": "List of relative file paths to view in bulk (e.g. ['src/App.jsx', 'server/index.js', 'package.json']).",
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
            "description": "Search for a keyword or regex pattern across workspace files. Returns matching lines and line numbers.",
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
            "description": "Write content to a single file, creating it and any parent directories if they don't exist. Ideal for creating new modular components (e.g. 'src/components/Header.jsx') or utility files.",
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
            "description": "Write content to multiple files in a single atomic batch operation. RECOMMENDED for initial application builds to write both 'server/index.js' (Express backend) and 'src/App.jsx' (React frontend) in 1 turn.",
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
            "description": "Edit a file by replacing a specific code snippet with new text. Indentation and whitespace tolerant. Include 2-3 lines of surrounding code context in 'old_text' to guarantee a unique match. Supports replace_all for global symbol renames.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The relative path to the file to edit.",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "The code snippet to find and replace. Include surrounding lines for unique context.",
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
            "description": "Run a static syntax and import validation check on JavaScript/JSX/TypeScript files. Call this before finish to verify zero syntax errors or broken imports in your code.",
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
            "description": "Fetch verified, working Unsplash CDN image URLs and recommended Lucide icon names tailored to your app topic (e.g. 'avatar', 'tech hero', 'crypto', 'food', 'sneakers'). Use this to populate rich UI images without broken links.",
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
            "description": "Ask the human user a clarifying question ONLY when functional requirements are fundamentally ambiguous between mutually exclusive options. NEVER call this tool to ask for permission to start, proceed, or write code. You have full autonomous authority to write and modify files directly.",
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
            "description": "Call ONLY when the application features have been completely implemented and verified on disk (server/index.js and src/App.jsx written and linted). Concludes the task with a summary of built features.",
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
            "description": "OPTIONAL: Invoke the specialized UI/UX Design Subagent to generate a brand new CSS design system in 'src/index.css' and component architecture blueprint. Use ONLY when the user explicitly requests a complete design system or theme overhaul from scratch. Does NOT write src/App.jsx or server/index.js.",
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
            "description": "Invoke the specialized Troubleshoot Subagent to perform deep root cause analysis (RCA) on compiler output, Vite build failures, runtime exceptions, and API 500 errors, returning exact surgical fix patches.",
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
            "description": "Invoke the specialized Vision Expert Subagent to audit UI layout balance, visual hierarchy, color contrast ratios (WCAG AA), and curate missing visual assets.",
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
            "description": "Execute a shell command in the project directory. Use this to install ANY needed npm packages (e.g. 'npm install recharts framer-motion canvas-confetti axios') before importing them, or run build/audit scripts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute (e.g. 'npm install recharts', 'npm ls').",
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
            "description": "Run a long-running process in the background. Note: The main fullstack dev server is already running automatically in the background; only use this for custom auxiliary background tasks.",
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
            "name": "invoke_testing_agent",
            "description": "Invoke the specialized UI & Browser Testing Subagent to autonomously drive a headless browser, click buttons, fill forms, and verify interactive workflows.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The local application URL to test (e.g. 'http://localhost:5173').",
                    },
                    "instructions": {
                        "type": "string",
                        "description": "Detailed plain-text instructions on what user flows, buttons, and views to test.",
                    },
                },
                "required": ["url", "instructions"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "invoke_code_reviewer_agent",
            "description": "Invoke the specialized Senior Staff Code Reviewer Subagent to audit code correctness, OWASP security vulnerabilities, Express async route error handling, and React performance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_files": {
                        "type": "string",
                        "description": "Optional comma-separated list of relative file paths to inspect (e.g. 'src/App.jsx, server/index.js'). If empty, automatically discovers and audits all source code files across src/ and server/.",
                    },
                    "focus_areas": {
                        "type": "string",
                        "description": "Optional specific focus areas to audit (e.g. 'security, error handling, state mutations, performance').",
                    },
                },
                "required": [],
            },
        },
    },
]

