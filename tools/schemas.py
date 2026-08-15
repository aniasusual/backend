# Explicit JSON tool schemas for Ollama tool calling

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The relative path to the file to read.",
                    }
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file, creating it and any parent directories if they don't exist.",
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
            "name": "edit_file",
            "description": "Edit a file by replacing a specific text occurrence with new text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The relative path to the file to edit.",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "The exact text to find and replace.",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "The text to replace it with.",
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
