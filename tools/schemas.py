# Explicit JSON tool schemas for Ollama tool calling

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file with line numbers, optionally sliced by a line range (maximum 250 lines per call). Unbounded reads are automatically clamped to 250 lines with pagination notices.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The relative path to the file to read."
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Optional 1-indexed starting line number (default: 1)."
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Optional 1-indexed ending line number (default: min(start_line + 249, end of file); maximum 250 lines per call)."
                    }
                },
                "required": [
                    "file_path"
                ]
            }
        }
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
                        "description": "The glob pattern to match files against (e.g. '*.js', 'src/**/*.jsx')."
                    },
                    "path": {
                        "type": "string",
                        "description": "The relative directory to search within (default: current workspace root)."
                    }
                },
                "required": [
                    "pattern"
                ]
            }
        }
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
                        "description": "The search term or regex pattern to look for."
                    },
                    "path": {
                        "type": "string",
                        "description": "The relative path or directory to search within (default: entire workspace)."
                    }
                },
                "required": [
                    "query"
                ]
            }
        }
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
                        "description": "The relative path to the file to write."
                    },
                    "content": {
                        "type": "string",
                        "description": "The full content to write to the file."
                    }
                },
                "required": [
                    "file_path",
                    "content"
                ]
            }
        }
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
                        "description": "The relative path to the file to edit."
                    },
                    "old_text": {
                        "type": "string",
                        "description": "The code snippet to find and replace. Include surrounding lines for unique context."
                    },
                    "new_text": {
                        "type": "string",
                        "description": "The replacement code."
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "Replace all occurrences of old_text across the file (default: False). Use this to rename variables, components, or imports."
                    }
                },
                "required": [
                    "file_path",
                    "old_text",
                    "new_text"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "locate_files_by_pattern",
            "description": "Explore the repository topology as a hierarchical visual file tree up to a limited depth, without reading file contents. Ideal for rapid architectural discovery.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "The relative path to the directory to explore (default: '.')."
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum directory traversal depth (default: 3, max: 10)."
                    },
                    "pattern": {
                        "type": "string",
                        "description": "File pattern to filter results (e.g. '*.js', '*.jsx', default: '*')."
                    }
                },
                "required": []
            }
        }
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
                        "description": "The relative file path or directory to lint (e.g. 'src/App.jsx', 'server/index.js', 'src'). Defaults to whole workspace."
                    }
                },
                "required": []
            }
        }
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
                        "description": "Keywords describing the asset or topic (e.g. 'avatar', 'tech hero', 'dashboard analytics', 'sneaker product', 'burger', 'finance')."
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional category filter: 'avatar', 'hero', 'product', 'finance', 'food', 'nature'."
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of asset suggestions to return (default: 5)."
                    }
                },
                "required": [
                    "query"
                ]
            }
        }
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
                        "description": "The question or prompt to ask the user."
                    },
                    "options": {
                        "type": "array",
                        "description": "Optional list of selectable option strings to make user response easy.",
                        "items": {
                            "type": "string"
                        }
                    }
                },
                "required": [
                    "question"
                ]
            }
        }
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
                        "description": "Detailed summary of all completed tasks, files created/modified, and verification status."
                    },
                    "next_steps": {
                        "type": "string",
                        "description": "Optional recommended next steps for the user (e.g. how to test or run)."
                    }
                },
                "required": [
                    "summary"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "task",
            "description": "Delegate tasks to specialized background subagents. Supports single-agent spawn ({agent, task}) or concurrent batch-agent spawns ({context, tasks}).",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent": {
                        "type": "string",
                        "description": "Agent role name (e.g. 'task', 'scout', 'reviewer', 'security_reviewer', 'troubleshoot', 'design', 'tester'). Defaults to 'task'."
                    },
                    "task": {
                        "type": "string",
                        "description": "Complete, self-contained instructions for the subagent."
                    },
                    "name": {
                        "type": "string",
                        "description": "Optional label or handle for this subagent."
                    },
                    "context": {
                        "type": "string",
                        "description": "Shared background context, contracts, and goals (required when spawning batch tasks)."
                    },
                    "tasks": {
                        "type": "array",
                        "description": "List of task items to spawn concurrently in batch mode.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string"
                                },
                                "agent": {
                                    "type": "string"
                                },
                                "task": {
                                    "type": "string"
                                },
                                "tools": {
                                    "type": "array",
                                    "items": {
                                        "type": "string"
                                    }
                                },
                                "isolated": {
                                    "type": "boolean"
                                }
                            },
                            "required": [
                                "task"
                            ]
                        }
                    },
                    "tools": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "Optional explicit tool names to grant this subagent."
                    },
                    "isolated": {
                        "type": "boolean",
                        "description": "Run subagent in an isolated Git worktree."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "hub",
            "description": "Agent coordination: peer messaging, background-job control, and process supervision.",
            "parameters": {
                "type": "object",
                "properties": {
                    "op": {
                        "type": "string",
                        "enum": [
                            "send",
                            "wait",
                            "inbox",
                            "list",
                            "jobs",
                            "cancel"
                        ],
                        "description": "Hub operation to perform."
                    },
                    "to": {
                        "type": "string",
                        "description": "Recipient agent ID or 'all' to broadcast."
                    },
                    "message": {
                        "type": "string",
                        "description": "Message content to send to peer."
                    },
                    "reply_to": {
                        "type": "string",
                        "description": "ID of message being answered."
                    },
                    "ids": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "Job IDs to cancel or query."
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Seconds to wait for incoming message."
                    }
                },
                "required": [
                    "op"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Navigate the headless browser to a specified application URL (e.g. 'http://localhost:3000'). Returns live DOM interactive elements, page title, and in-DOM errors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Target webpage URL to open."
                    }
                },
                "required": [
                    "url"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Click on an interactive element by data-sdet-id (e.g. 'el_0', 'el_1') or CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "Element ID (e.g. 'el_0') or CSS selector to click."
                    }
                },
                "required": [
                    "selector"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_fill",
            "description": "Fill an input field or textarea with text using an element ID (e.g. 'el_1') or CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "Element ID or CSS selector of input field."
                    },
                    "value": {
                        "type": "string",
                        "description": "Text string to enter into the input."
                    }
                },
                "required": [
                    "selector",
                    "value"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_snapshot",
            "description": "Inspect the current DOM state, visible interactive buttons, inputs, links, and active console/in-DOM errors.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Capture a screenshot of the currently rendered web page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Optional destination path to save PNG screenshot."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_scroll",
            "description": "Scroll the active webpage 'up' or 'down' by a specified pixel amount.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": [
                            "up",
                            "down"
                        ],
                        "description": "Direction to scroll."
                    },
                    "amount": {
                        "type": "integer",
                        "description": "Pixel amount to scroll (default: 500)."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "Execute a shell command strictly within the current project directory. Use this to install ANY needed npm packages (e.g. 'npm install recharts framer-motion canvas-confetti axios') before importing them, or run build/audit scripts. Commands must run strictly within the current app project directory; executing commands outside the project folder or using path traversal is strictly forbidden.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute (e.g. 'npm install recharts', 'npm ls')."
                    },
                    "reason": {
                        "type": "string",
                        "description": "A short explanation of why this command needs to be executed."
                    }
                },
                "required": [
                    "command",
                    "reason"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mount_file",
            "description": "Mounts an active workspace file into Dynamic Virtual RAM. The file remains pinned in your working memory across multiple conversation turns without needing to re-read it. It automatically updates whenever edited. Strictly capped at 60% of the context window.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The relative path to the workspace file to mount into Virtual RAM (e.g. 'src/App.jsx')."
                    }
                },
                "required": [
                    "file_path"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "unmount_file",
            "description": "Unmounts an active workspace file from Dynamic Virtual RAM, releasing working memory attention and token budget.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The relative path to the mounted file to remove from Virtual RAM (e.g. 'src/App.jsx')."
                    }
                },
                "required": [
                    "file_path"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "extract_signatures",
            "description": "Extracts structural code signatures (classes, methods, functions, Express routes, interfaces, exports, docstrings) from Python, JavaScript, TypeScript, or JSX files, stripping interior execution bodies. Saves 80-90% of tokens while retaining full architectural awareness.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The relative path to the source code file to extract signatures from (e.g. 'server/index.js', 'src/App.jsx', 'app.py')."
                    }
                },
                "required": [
                    "file_path"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "map_dependencies",
            "description": "Maps repository import/export relationships across the workspace. When target_file is provided, performs an impact analysis detailing what the file imports, what it exports, and all downstream files that depend on it. When target_file is omitted, returns a complete workspace dependency topology map.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_file": {
                        "type": "string",
                        "description": "Optional relative path to a specific file to audit for dependencies and downstream impact (e.g. 'src/components/TodoItem.jsx', 'server/routes/items.js'). If omitted, maps the entire workspace."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web using DuckDuckGo for live documentation, APIs, error solutions, or technical references without API keys.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to look up (e.g. 'FastAPI lifespan handlers', 'Tailwind v4 grid syntax')."
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of search results to return (default: 5, range: 1-10)."
                    }
                },
                "required": [
                    "query"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "close_file",
            "description": "Alias for unmount_file. Unmounts an active workspace file from Dynamic Virtual RAM, releasing working memory attention and token budget.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The relative path to the file to unmount from Virtual RAM."
                    }
                },
                "required": [
                    "file_path"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_mounted_files",
            "description": "Lists all files currently mounted in Dynamic Virtual RAM, along with their line counts, token usage, and remaining budget capacity.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]
