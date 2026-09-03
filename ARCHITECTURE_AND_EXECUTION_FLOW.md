# Lowkey: Complete Architecture & End-to-End Execution Flow

This document provides a comprehensive technical reference for the complete execution lifecycle of Lowkey—from when a user enters a prompt on the UI to project scaffolding, local dev-server booting, agentic reasoning with local Ollama models, tool execution, and live hot-reloaded preview.

---

## Table of Contents
1. [High-Level Architecture Overview](#1-high-level-architecture-overview)
2. [Visual Execution Diagrams](#2-visual-execution-diagrams)
3. [Step-by-Step Execution Sequence (File by File)](#3-step-by-step-execution-sequence-file-by-file)
   - [Phase 1: Prompt Ingestion & Project Naming](#phase-1-prompt-ingestion--project-naming)
   - [Phase 2: Project Creation & Zero-Install Scaffolding](#phase-2-project-creation--zero-install-scaffolding)
   - [Phase 3: WebSocket Connection & Dev Server Booting](#phase-3-websocket-connection--dev-server-booting)
   - [Phase 4: Agent Profile Resolution & Tool Whitelisting](#phase-4-agent-profile-resolution--tool-whitelisting)
   - [Phase 5: Context Window Management & Turn Compaction](#phase-5-context-window-management--turn-compaction)
   - [Phase 6: The Agentic Loop & Ollama Streaming](#phase-6-the-agentic-loop--ollama-streaming)
   - [Phase 7: Tool Dispatch, Subagents & File Execution](#phase-7-tool-dispatch-subagents--file-execution)
   - [Phase 8: Live Preview Health Polling & Debounced Reload](#phase-8-live-preview-health-polling--debounced-reload)
4. [WebSocket Protocol & Event Reference](#4-websocket-protocol--event-reference)
5. [Tool Registry & Specialized Subagents Reference](#5-tool-registry--specialized-subagents-reference)
6. [Core Files Map](#6-core-files-map)

---

## 1. High-Level Architecture Overview

Lowkey is composed of two primary layers:

1. **Frontend (React 18 + Vite / Electron)**:
   - **Minimalist Notion-Style UI**: Includes Welcome Landing View, Resizable Split Workspace, Chat Stream Viewer, Model Selector, and Live Iframe Preview Panel.
   - **Real-Time WebSocket Client**: Consumes streaming tokens, thinking/reasoning chunks, tool execution cards, command approval modals, and file change signals.

2. **Backend Engine (Python 3.10+ / FastAPI / AsyncIO / Ollama)**:
   - **Project Manager**: Manages independent sandboxes under `~/.lowkey/projects/` with pre-cached symlinked dependencies.
   - **Harness & Agent Loader**: Dynamically tailors system prompts and tool whitelists based on model parameter tiers (1.5B, 7B, 14B, 32B+, DeepSeek-R1).
   - **Tool Registry & Subagents**: Coordinates safe sandbox operations (`file_tools`, `process_tools`, `linter_tools`, `asset_tools`, `design_subagent`, `troubleshoot_subagent`).
   - **Stream Normalizer**: Suppresses raw tool JSON from leaking into the user chat while passing live thoughts and markdown tokens.

---

## 2. Visual Execution Diagrams

### Universal System Flow Diagram

```
+----------------------------------------------------------------------------------------------------+
|                                         LOWKEY FRONTEND (React)                                    |
|                                                                                                    |
|  [WelcomeView.jsx]                                                                                 |
|   1. User types prompt -> GET /api/projects/suggest-name -> User confirms name                     |
|   2. Calls onSubmit(prompt, projectName)                                                           |
|          |                                                                                         |
|          v                                                                                         |
|  [App.jsx]                                                                                         |
|   3. POST /api/projects (Express + React Vite scaffolding)                                         |
|   4. Switch view -> [WorkspaceView.jsx]                                                            |
|   5. WS send: {"action": "open_project", "name": "kanban-app"}                                     |
|   6. WS send: {"prompt": "Build a Kanban...", "model": "qwen2.5-coder:7b"}                         |
+------------------------------------+----------------------------------+----------------------------+
                                     |                                  ^
                     REST & WS Calls |                                  | Real-time WS Stream
                                     v                                  | (Tokens / Tools / Status)
+-----------------------------------------------------------------------+----------------------------+
|                                         LOWKEY BACKEND (FastAPI)                                   |
|                                                                                                    |
|  [engine.py]                                                                                       |
|   7. REST: project_manager.create_project()                                                        |
|      └──> [template_manager.py] scaffolds files & symlinks ~/.lowkey/template_cache/node_modules   |
|   8. WS: active_registry = ToolRegistry(project_path)                                              |
|      └──> [process_tools.py] start_dev_server() -> Vite (3000) & Express (5001)                    |
|      └──> Emits WS event: {"type": "preview_ready", "port": 3000, "backend_port": 5001}           |
|   9. WS: run_harness_task(prompt, "CodingHarness", model)                                          |
|                                                                                                    |
|  [coding_harness.py]                                                                               |
|  10. [agent_loader.py] loads model YAML spec (e.g. qwen2.5_coder_7b.yaml) -> whitelist tools       |
|  11. [context_manager.py] compacts message history & injects system prompt + recency anchor        |
|                                                                                                    |
|  === THE AGENTIC LOOP (Ollama Local LLM) ========================================================  |
|  12. Streams Ollama chat response:                                                                 |
|      - Thinking chunks   ──> [stream_normalizer.py] ──> WS {"type": "thinking"}                    |
|      - Text tokens       ──> [stream_normalizer.py] ──> WS {"type": "token"}                       |
|      - Tool Call parsed  ──> [plugins/argument_normalizer.py]                                      |
|                                                                                                    |
|  13. Tool Execution via [tools/registry.py]:                                                       |
|      ├─> invoke_design_agent   ──> [design_subagent.py]  (Writes HSL variables to src/index.css)   |
|      ├─> get_assets            ──> [asset_tools.py]     (Fetches Unsplash URLs & Lucide icons)     |
|      ├─> write_files           ──> [file_tools.py]      (Writes server/index.js & src/App.jsx)     |
|      │                             └──> Emits WS event: {"type": "file_changed"}                  |
|      ├─> lint_javascript       ──> [linter_tools.py]    (Validates syntax & imports)               |
|      └─> finish                ──> [interaction_tools.py]                                          |
|                                                                                                    |
|  14. Loop repeats until finish() or no more tool calls -> Emits WS {"type": "status", "Done"}     |
+-----------------------------------------------------------------------+----------------------------+
                                                                        |
                                                                        v
+----------------------------------------------------------------------------------------------------+
|                                         LIVE FRONTEND UPDATE                                       |
|                                                                                                    |
|  [ChatMessage.jsx]                                                                                 |
|   - Renders live token stream, reasoning thoughts, and expandable tool execution cards             |
|   - Collapses cards upon "Done"                                                                    |
|                                                                                                    |
|  [PreviewPanel.jsx]                                                                                |
|   - Receives "file_changed" -> Triggers debounced iframe reload (`setFrameKey(k => k + 1)`)        |
|   - Live application is immediately running and fully interactive!                                 |
+----------------------------------------------------------------------------------------------------+
```

### Complete Sequence Diagram

```
USER                  FRONTEND (React)             BACKEND (FastAPI)              OLLAMA LLM
 |                           |                             |                          |
 |--- 1. Enters Prompt ----->|                             |                          |
 |                           |--- 2. POST /api/projects -->|                          |
 |                           |    (Scaffold & Symlink)     |                          |
 |                           |<-- 3. Project Created ------|                          |
 |                           |                             |                          |
 |                           |--- 4. WS "open_project" --->|                          |
 |                           |    (Boot Dev Server)        |                          |
 |                           |<-- 5. "preview_ready" ------|                          |
 |                           |    (Vite:3000, Exp:5001)    |                          |
 |                           |                             |                          |
 |                           |--- 6. WS "prompt" --------->|                          |
 |                           |                             |--- 7. chat(messages) --->|
 |                           |                             |<-- 8. stream tokens -----|
 |                           |<-- 9. {"type": "token"} ----|                          |
 |<-- 10. Sees Chat Stream --|                             |                          |
 |                           |                             |<-- 11. invoke_design --->|
 |                           |<-- 12. {"tool_call"} -------|                          |
 |                           |                             | (Injects src/index.css)  |
 |                           |                             |--- 13. tool_result ----->|
 |                           |                             |                          |
 |                           |                             |<-- 14. write_files ----->|
 |                           |                             | (Writes App.jsx, index.js|
 |                           |<-- 15. {"file_changed"} ----|                          |
 |                           |    (Iframe Auto-Reloads)    |                          |
 |                           |                             |--- 16. tool_result ----->|
 |                           |                             |                          |
 |                           |                             |<-- 17. finish() ---------|
 |                           |<-- 18. {"status": "Done"} --|                          |
 |<-- 19. Full App Ready ----|                             |                          |
```

---

## 3. Step-by-Step Execution Sequence (File by File)

### Phase 1: Prompt Ingestion & Project Naming
- **File**: `frontend/src/components/WelcomeView.jsx`
- **Actions**:
  1. User enters natural language request (e.g., *"A Kanban board with drag-and-drop, tags, and local storage"*).
  2. `handleInitialSubmit` intercepts the form and queries `GET /api/projects/suggest-name?base=...`.
  3. User reviews/edits the slugified folder name and clicks **Start building**.
  4. Calls `onSubmit(prompt, projectName)` passing the parameters up to `App.jsx`.

---

### Phase 2: Project Creation & Zero-Install Scaffolding
- **Files**:
  - `frontend/src/App.jsx` (`handleCreateProject`)
  - `backend/engine.py` (`projects_router.post("")`)
  - `backend/project_manager/manager.py` (`ProjectManager.create_project`)
  - `backend/project_manager/template_manager.py` (`TemplateManager.scaffold_project`)
- **Actions**:
  1. `App.jsx` issues `POST /api/projects` with payload `{"name": projectName, "template": "node_react"}`.
  2. `ProjectManager` creates a sandboxed directory at `~/.lowkey/projects/<project-name>`.
  3. `TemplateManager` scaffolds the full-stack starter template (`templates/node_react`):
     - `server/index.js` (Express ES Module API)
     - `src/App.jsx` & `src/index.css` (React 18 + Vite)
     - `package.json`, `vite.config.js`, `index.html`
  4. **Zero-Install Symlink**: Symlinks `~/.lowkey/template_cache/node_react/node_modules` into the project's `node_modules` folder, eliminating `npm install` wait time.
  5. Saves `.lowkey_meta.json` in the project root and returns the `ProjectInfo` object.

---

### Phase 3: WebSocket Connection & Dev Server Booting
- **Files**:
  - `frontend/src/App.jsx` (`handleOpenProject`, `handleSendMessage`)
  - `backend/engine.py` (`websocket_endpoint`)
  - `backend/tools/registry.py` (`ToolRegistry.__init__`)
  - `backend/tools/process_tools.py` (`ProcessTools.start_dev_server`)
- **Actions**:
  1. `App.jsx` transitions UI state from `welcome` to `workspace` view and sends:
     `{"action": "open_project", "name": projectName}`
  2. `engine.py` initializes a sandbox-restricted `ToolRegistry` instance for the project path.
  3. `engine.py` invokes `active_registry.start_dev_server()`.
  4. `ProcessTools` finds free ports (e.g. `3000` for Vite, `5001` for Express), spawns `npm run dev`, and emits over WebSocket:
     ```json
     {
       "type": "preview_ready",
       "port": 3000,
       "backend_port": 5001,
       "url": "http://localhost:3000"
     }
     ```
  5. `App.jsx` receives `preview_ready` and passes `previewData` to `PreviewPanel.jsx`, which begins health polling the URL.

---

### Phase 4: Agent Profile Resolution & Tool Whitelisting
- **Files**:
  - `backend/engine.py` (`run_harness_task`)
  - `backend/plugins/coding_harness.py` (`CodingHarness.process_prompt`)
  - `backend/config/agent_loader.py` (`AgentLoader.get_profile_for_model`)
  - `backend/config/prompts.py` (`get_system_prompt_for_profile`)
- **Actions**:
  1. `App.jsx` sends the prompt message:
     `{"prompt": prompt, "harness": "CodingHarness", "model": selectedModel}`
  2. `engine.py` launches an asynchronous coroutine `run_harness_task`.
  3. `CodingHarness` queries `AgentLoader` with the active model ID (e.g. `qwen2.5-coder:7b`).
  4. `AgentLoader` matches the model against YAML configurations (`config/agents/*.yaml`) to construct an `AgentProfile`:
     - **Whitelisted Tools**: e.g., `read_file`, `write_file`, `write_files`, `edit_file`, `lint_javascript`, `get_assets`, `ask_human`, `finish`.
     - **Active Subagents**: `invoke_design_agent`, `invoke_troubleshoot_agent`, `invoke_vision_agent`.
     - **System Prompt**: Injects the 6-phase engineering lifecycle instructions.

---

### Phase 5: Context Window Management & Turn Compaction
- **File**: `backend/utils/context_manager.py` (`ContextManager.prepare_messages`)
- **Actions**:
  1. Compacts previous chat history, removing raw code blocks and intermediate tool payloads from past turns to enforce a clean **Disk-First architecture**.
  2. Injects the system prompt at message index 0.
  3. Appends a **Recency Anchor** instruction to the user prompt:
     `\n\n[Instruction: Directly execute tools (write_files, edit_file, read_file) to inspect and modify project files on disk. Do not output raw code blocks in chat.]`
  4. Truncates history if total messages exceed 30 turns.

---

### Phase 6: The Agentic Loop & Ollama Streaming
- **Files**:
  - `backend/plugins/coding_harness.py` (`CodingHarness.process_prompt`)
  - `backend/utils/stream_normalizer.py` (`StreamEventDispatcher`)
- **Actions**:
  1. `CodingHarness` calls `ollama.AsyncClient().chat(model, messages, tools=active_schemas, stream=True)`.
  2. `StreamEventDispatcher` analyzes streaming chunks:
     - **Thinking Tokens** (`<think>` or `chunk.message.thinking`): Dispatched as `{"type": "thinking", "content": "..."}`.
     - **Conversational Content**: Dispatched as `{"type": "token", "content": "..."}`.
     - **Tool JSON Blocks**: Suppressed from token emissions to prevent raw JSON from cluttering the chat bubble.
  3. Native structured tool calls (or parsed markdown fallback tools) are extracted and queued for execution.

---

### Phase 7: Tool Dispatch, Subagents & File Execution
- **Files**:
  - `backend/plugins/coding_harness.py` (`_execute_tool_calls`)
  - `backend/plugins/argument_normalizer.py` (`ToolArgumentNormalizer.normalize`)
  - `backend/subagents/design_subagent.py` (`DesignSubagent.generate_layout_blueprint`)
  - `backend/tools/asset_tools.py` (`AssetTools.get_assets`)
  - `backend/tools/file_tools.py` (`FileTools.write_files`, `write_file`)
  - `backend/tools/linter_tools.py` (`LinterTools.lint_javascript`)
  - `backend/tools/interaction_tools.py` (`InteractionTools.finish`)
- **Actions**:
  1. `_execute_tool_calls` emits `{"type": "tool_call", "name": func_name, "arguments": func_args}`.
  2. **Design Subagent** (`invoke_design_agent`):
     - Selects domain palette (e.g. `dark_glass_indigo`, `emerald_fintech`, `violet_cyberpunk`).
     - Injects HSL variables, glassmorphism tokens, and Google Fonts into `src/index.css`.
  3. **Asset Resolution** (`get_assets`):
     - Returns verified Unsplash URLs and Lucide icon components.
  4. **Code Writing** (`write_file` / `write_files`):
     - Writes the Express REST API in `server/index.js`.
     - Writes the React application UI in `src/App.jsx`.
     - Emits `{"type": "file_changed", "file": "src/App.jsx"}` over WebSocket.
  5. **Verification** (`lint_javascript`):
     - Runs fast syntax validation on JSX and JavaScript files.
  6. **Lifecycle Completion** (`finish`):
     - Emits `{"type": "tool_result", "name": "finish", "result": "..."}`.
  7. Yields `{"type": "status", "content": "Done"}`.

---

### Phase 8: Live Preview Health Polling & Debounced Reload
- **Files**:
  - `frontend/src/components/ChatMessage.jsx`
  - `frontend/src/components/PreviewPanel.jsx`
- **Actions**:
  1. `ChatMessage.jsx` streams tokens live, formats reasoning thoughts into accordions, and attaches file badges to tool execution cards.
  2. On status `"Done"`, `App.jsx` sets `isAgentRunning = false` and auto-collapses tool cards.
  3. `PreviewPanel.jsx` detects the `file_changed` event timestamp and triggers a debounced iframe key increment (`setFrameKey(k => k + 1)`), refreshing the running React app without dropping server connection.

---

## 4. WebSocket Protocol & Event Reference

All real-time communication between the UI and backend runs through the `/ws` endpoint.

### Client -> Backend Messages

| Action / Field | Example Payload | Description |
|---|---|---|
| `open_project` | `{"action": "open_project", "name": "todo-app"}` | Opens project sandbox and auto-starts dev server |
| `prompt` | `{"prompt": "Add dark mode", "harness": "CodingHarness", "model": "qwen2.5-coder:7b"}` | Sends prompt to start agent execution loop |
| `command_approval` | `{"action": "command_approval", "request_id": "uuid", "approved": true}` | Approves/denies shell command execution |
| `stop_preview` | `{"action": "stop_preview"}` | Stops active dev server background process |
| `restart_preview` | `{"action": "restart_preview"}` | Restarts Vite and Express dev server processes |
| `close_project` | `{"action": "close_project"}` | Cleans up background processes and resets session |

### Backend -> Client Events

| Event `type` | Payload Structure | Description |
|---|---|---|
| `preview_ready` | `{"type": "preview_ready", "port": 3000, "backend_port": 5001, "url": "http://localhost:3000"}` | Emitted when dev server is live |
| `file_changed` | `{"type": "file_changed", "file": "src/App.jsx"}` | Emitted whenever a file is written or edited |
| `token` | `{"type": "token", "content": "Here is what I built:"}` | Conversational markdown token chunk |
| `thinking` | `{"type": "thinking", "content": "Planning component structure..."}` | Model reasoning chunk (R1 / thinking models) |
| `tool_call` | `{"type": "tool_call", "name": "write_files", "arguments": {...}}` | Emitted when agent invokes a tool |
| `tool_result` | `{"type": "tool_result", "name": "write_files", "result": "Successfully wrote 2 files"}` | Tool execution output |
| `command_approval_request` | `{"type": "command_approval_request", "request_id": "uuid", "command": "npm i", "reason": "..."}` | Triggers permission modal in UI |
| `status` | `{"type": "status", "content": "Done"}` | Emitted when execution concludes |

---

## 5. Tool Registry & Specialized Subagents Reference

| Tool Name | Subsystem / File | Purpose |
|---|---|---|
| `read_file` | `tools/file_tools.py` | Slices and reads numbered file lines from the sandbox. |
| `view_bulk` | `tools/file_tools.py` | Views up to 15 files in a single batched operation. |
| `glob_files` | `tools/file_tools.py` | Discovers files matching glob patterns (e.g. `src/**/*.jsx`). |
| `grep_search` | `tools/file_tools.py` | Performs keyword and regex searching across project files. |
| `write_file` | `tools/file_tools.py` | Creates or overwrites a single file atomically. |
| `write_files` | `tools/file_tools.py` | Writes multiple files simultaneously in one atomic batch. |
| `edit_file` | `tools/file_tools.py` | Resilient string search-and-replace with fuzzy matching fallback. |
| `insert_text` | `tools/file_tools.py` | Inserts text after a specified line number. |
| `list_directory` | `tools/file_tools.py` | Lists directory contents with file size and type. |
| `lint_javascript` | `tools/linter_tools.py` | Runs fast AST syntax and import checks on JS/JSX. |
| `get_assets` | `tools/asset_tools.py` | Resolves real Unsplash image URLs and Lucide icon components. |
| `execute_command` | `tools/process_tools.py` | Executes short-lived CLI commands with sandbox safety checks. |
| `start_dev_server` | `tools/process_tools.py` | Allocates dual ports and runs background dev servers. |
| `invoke_design_agent` | `subagents/design_subagent.py` | Synthesizes domain design systems, HSL tokens, and Google Fonts into `src/index.css`. |
| `invoke_troubleshoot_agent` | `subagents/troubleshoot_subagent.py` | Automated root-cause analysis for runtime and compiler errors. |
| `invoke_vision_agent` | `subagents/vision_subagent.py` | Visual aesthetic audit and screenshot analysis. |
| `ask_human` | `tools/interaction_tools.py` | Solicits clarification or multi-choice decisions from the user. |
| `finish` | `tools/interaction_tools.py` | Signals turn completion with summary and next steps. |

---

## 6. Core Files Map

```
lowkey/
├── backend/
│   ├── engine.py                      # FastAPI app, REST routes, WebSocket handler
│   ├── harness_manager.py             # Plugin loader for agent harnesses
│   ├── plugins/
│   │   ├── coding_harness.py          # Primary agentic execution loop
│   │   └── argument_normalizer.py     # Tool call argument sanitizer
│   ├── config/
│   │   ├── agent_loader.py            # YAML agent profile manager
│   │   ├── models.py                  # Hardware detection & model catalog
│   │   ├── prompts.py                 # Multi-phase system prompts
│   │   └── settings.py                # Environment & directory configuration
│   ├── project_manager/
│   │   ├── manager.py                 # Project lifecycle (~/.lowkey/projects/)
│   │   └── template_manager.py        # Template unpacking & cached node_modules symlinking
│   ├── tools/
│   │   ├── registry.py                # Central tool registry & dispatcher
│   │   ├── file_tools.py              # File reading, writing, and editing
│   │   ├── process_tools.py           # Shell execution & dual-port dev servers
│   │   ├── linter_tools.py            # Fast JS/JSX syntax checking
│   │   ├── asset_tools.py             # Unsplash & Lucide asset resolver
│   │   └── schemas.py                 # Ollama JSON tool schemas
│   ├── subagents/
│   │   ├── design_subagent.py         # UI/UX theme generator (HSL & Google Fonts)
│   │   ├── troubleshoot_subagent.py   # Root-cause bug analyzer
│   │   └── vision_subagent.py         # Visual & screenshot inspector
│   └── utils/
│       ├── context_manager.py         # History compaction & Disk-First context
│       ├── stream_normalizer.py       # Stream event dispatcher & JSON suppressor
│       └── hardware.py                # System RAM, GPU, and chip detection
│
└── frontend/
    └── src/
        ├── App.jsx                    # Root state, WebSocket client, project transitions
        ├── components/
        │   ├── WelcomeView.jsx        # Landing page, prompt input, recent projects
        │   ├── WorkspaceView.jsx      # Split panel layout & resizable divider
        │   ├── ChatPanel.jsx          # Message stream container & input box
        │   ├── ChatMessage.jsx        # Token rendering, thinking blocks, tool cards
        │   ├── PreviewPanel.jsx       # Live iframe, health polling & auto-reload
        │   ├── ModelSelector.jsx      # Model picker with hardware compatibility tags
        │   └── CommandApproval.jsx    # Permission prompt for shell commands
        └── config.js                  # API and WebSocket base URLs
```
