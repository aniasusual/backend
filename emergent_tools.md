Listed directory mono
Viewed CLAUDE.md:1-256
Ran command: `find . -maxdepth 2 -not -path '*/.*'`
Ran command: `find cortex -maxdepth 4`
Ran command: `find cortex/core cortex/tools cortex/pkg/agentsdk/tools -type f`
Ran command: `find cortex/core/workflows cortex/core/activities -type f`
Ran command: `find wingman -maxdepth 4`
Ran command: `find wingman/base wingman/skills -type f`
Ran command: `find emergent/plugin_library emergent/agents -type f`
Ran command: `find emergent/plugin_library -type f`
Ran command: `find xtools mcp mcp-gateway oracle agentivity app-builder envcore enterprise wisp harbor-harness -maxdepth 4`
Ran command: `find xtools mcp mcp-gateway oracle agentivity enterprise envcore wisp -type f`
Ran command: `find xtools mcp mcp-gateway oracle agentivity enterprise -type f`
Ran command: `find xtools mcp mcp-gateway oracle -type f`
Ran command: `find . -name "*agent*.yaml" -o -name "*agent*.yml" -o -name "*agent*.json" -o -name "*tool*.yaml" -o -name "*tool*.json"`
Viewed tools.yaml:1-621
Viewed subagent.go:1-100
Searched for "RegisterSubagentTool"
Viewed tools.go:1-567
Viewed toolsets.go:1-240
Viewed memory_tools.go:1-312
Viewed runtime_job_tools.go:1-210
Viewed skills_tools.go:1-800
Viewed skills_tools.go:801-1056
Viewed server.go:1-53
Viewed server.py:1-70
Viewed descriptions.py:1-415
Viewed server.py:1-449
Viewed mcp_server.py:1-204
Viewed mcp_tools.py:1-800
Searched for "@mcp.tool"
Searched for "def "
Ran command: `python3 -c '
import re

for filepath in [
    "emergent/plugin_library/plugins/tools/agent/mcp_tools.py",
    "emergent/plugin_library/plugins/tools/agent/bash_tools.py",
    "emergent/plugin_library/plugins/tools/agent/skill_tools.py",
    "emergent/plugin_library/plugins/tools/agent/screenshot_tools.py",
    "emergent/plugin_library/plugins/tools/agent/system_tools.py",
    "emergent/plugin_library/plugins/tools/agent/todo_tools.py",
]:
    with open(filepath) as f:
        content = f.read()
    tools = re.findall(r"@mcp\.tool\([^\)]*\)\s*(?:async\s+)?def\s+([a-zA-Z0-9_]+)", content)
    print(f"=== {filepath} ===")
    for t in tools:
        print(f"  - {t}")
'`
Ran command: `python3 -c '
import ast, glob

for filepath in glob.glob("emergent/plugin_library/**/*.py", recursive=True):
    try:
        with open(filepath) as f:
            tree = ast.parse(f.read(), filename=filepath)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    dec_str = ast.unparse(dec)
                    if "mcp.tool" in dec_str or "tool" in dec_str:
                        print(f"{filepath} : {node.name} (dec: {dec_str})")
            elif isinstance(node, ast.Call):
                call_str = ast.unparse(node.func)
                if "register_" in call_str:
                    print(f"{filepath} : call {ast.unparse(node)}")
    except Exception as e:
        pass
'`
Ran command: `python3 -c '
import ast

for filepath in [
    "emergent/plugin_library/plugins/tools/agent/bash_tools.py",
    "emergent/plugin_library/plugins/tools/agent/screenshot_tools.py",
    "emergent/plugin_library/plugins/tools/agent/skill_tools.py",
    "emergent/plugin_library/plugins/tools/agent/todo_tools.py",
]:
    with open(filepath) as f:
        tree = ast.parse(f.read(), filename=filepath)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                dec_str = ast.unparse(dec)
                if "mcp.tool" in dec_str or "tool" in dec_str:
                    print(f"{filepath} : {node.name} (dec: {dec_str})")
'`
Ran command: `python3 -c '
import os, glob

for f in sorted(glob.glob("emergent/agents/**/*.py", recursive=True)):
    with open(f) as fp:
        content = fp.read()
    if "Agent" in content or "Tool" in content or "subagent" in content or "Subagent" in content:
        # Check class definitions
        for line in content.splitlines():
            if line.startswith("class ") or "class " in line and line.strip().startswith("class "):
                if any(k in line for k in ["Agent", "Tool", "Service", "Assistant", "Runner"]):
                    print(f"{f}: {line.strip()}")
'`
Ran command: `find emergent/agents/tools/impl -type f`
Ran command: `python3 -c '
import ast, glob

for f in sorted(glob.glob("emergent/agents/tools/impl/*.py")):
    with open(f) as fp:
        tree = ast.parse(fp.read(), filename=f)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Check for tool_name or similar attributes
            tool_name = None
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name) and target.id in ("tool_name", "name", "TOOL_NAME"):
                            if isinstance(item.value, ast.Constant):
                                tool_name = item.value.value
            print(f"{f} -> Class: {node.name}, Tool Name: {tool_name}")
'`
Ran command: `find emergent/agents/emergent_e1/sub_agents -type f`
Viewed skilled_assistant.py:1-120
Viewed constant.py:1-503
Viewed tool_set.py:1-348
Ran command: `find wingman -name "*tool*.py" -o -name "*agent*.py" -o -name "*skill*.py"`
Viewed tool_registry.py:1-64
Searched for "mcp_tools"
Searched for "Tool("
Searched for "Tool("
Viewed mcp_server.py:1-630
Viewed mcp_endpoint.py:1-800
Viewed mcp_endpoint.py:801-1073
Ran command: `find oracle -type f`
Ran command: `python3 -c '
import glob, yaml

for f in sorted(glob.glob("oracle/resources/agents/**/*.yaml", recursive=True)):
    print(f"=== {f} ===")
    with open(f) as fp:
        try:
            data = yaml.safe_load(fp)
            print(f"  name: {data.get(\"name\")}")
            print(f"  model: {data.get(\"model\")}")
            print(f"  toolsets: {[ts.get(\"name\") for ts in data.get(\"toolsets\", [])]}")
        except Exception as e:
            print(f"  error: {e}")
'`
Ran command: `python3 -c '
import glob, yaml

for f in sorted(glob.glob("oracle/resources/agents/**/*.yaml", recursive=True)):
    print(f"=== {f} ===")
    with open(f) as fp:
        try:
            data = yaml.safe_load(fp)
            name = data.get("name") if isinstance(data, dict) else None
            model = data.get("model") if isinstance(data, dict) else None
            toolsets = [ts.get("name") for ts in data.get("toolsets", [])] if isinstance(data, dict) and "toolsets" in data else []
            print(f"  name: {name}")
            print(f"  model: {model}")
            print(f"  toolsets: {toolsets}")
        except Exception as e:
            print(f"  error: {e}")
'`
Ran command: `python3 -c '
import glob

for f in sorted(glob.glob("oracle/resources/agents/**/*.yaml", recursive=True)):
    print(f"=== {f} ===")
    with open(f) as fp:
        for line in fp:
            line_s = line.strip()
            if any(line_s.startswith(k) for k in ["name:", "model:", "description:", "- name:"]):
                print(f"  {line_s}")
'`
Viewed index.yaml:1-19
Ran command: `find xtools/core -type f`
Ran command: `find agentivity/core -name "*tool*.go" -o -name "*agent*.go"`
Viewed tools.go:1-28
Searched for "subagent"
Searched for "AgentName"
Ran command: `grep -rE "(agent_name|subagent_name|agentRef|\"name\": \"subagents-|\"name\": \"EA-)" cortex/ experiments/ oracle/ emergent/ | head -n 40`
Used tool: manage_task
Listed directory subagents
Listed directory configs
Listed directory resources
Ran command: `find cortex/resources/agents cortex/resources/agents_local -type f`
Ran command: `python3 -c '
import glob

for f in sorted(glob.glob("cortex/resources/agents/**/subagents-*.yaml", recursive=True)):
    print(f"=== {f} ===")
    with open(f) as fp:
        for line in fp:
            line_s = line.strip()
            if any(line_s.startswith(k) for k in ["name:", "model:", "description:"]):
                print(f"  {line_s}")
'`
Ran command: `python3 -c '
import os, glob

for d in ["harbor-harness", "wisp", "deployer", "envcore", "enterprise", "experiments"]:
    files = glob.glob(f"{d}/**/*tool*.go", recursive=True) + glob.glob(f"{d}/**/*agent*.go", recursive=True) + glob.glob(f"{d}/**/*tool*.py", recursive=True) + glob.glob(f"{d}/**/*agent*.py", recursive=True)
    if files:
        print(f"=== {d} ===")
        for f in files:
            print(" ", f)
'`
Viewed tool.go:1-46
Searched for "Register("
Viewed mcp.go:1-262
Viewed support_mcp.go:1-88
Listed directory tools

Here is the comprehensive and verified list of all **Tools**, **Agents**, and **Subagents** across the entire monorepo, categorized by service and layer.

---

# 1. Cortex (Temporal Workflow Engine & Agent SDK)

### Built-in Agent SDK Tools
*Location: [`cortex/pkg/agentsdk/tools/builtin/tools.yaml`](file:///Users/animeshdhillon/Desktop/work/projects/mono/cortex/pkg/agentsdk/tools/builtin/tools.yaml) and [`cortex/pkg/agentsdk/tools/`](file:///Users/animeshdhillon/Desktop/work/projects/mono/cortex/pkg/agentsdk/tools/)*

| Tool Name | Type | Description |
| :--- | :--- | :--- |
| `bash` | Builtin | Executes shell commands in the container via bash (stdout, stderr, exit code). |
| `ask_human` | Builtin | Pauses workflow to ask the user clarifying questions, get confirmation, or request human credentials. |
| `emergent_integrations_manager` | Builtin | Fetches the universal Emergent LLM key for OpenAI, Anthropic, or Google integrations. |
| `finish` | Builtin | Delivers task completion summary (MVP creation, feature addition, bug fix) and updates PRD. |
| `test_finish` | Builtin | Delivers end-of-task test results, env status, and generated report file paths. |
| `finish_plan` | Builtin | Delivers the final architecture & implementation plan gathered during brainstorming. |
| `think` | Builtin | Scratchpad / chain-of-thought reasoning tool (appends thoughts to trajectory). |
| `plan` | Builtin | Generates (`create`) or modifies (`update`) implementation plans in `/app/plan.md`. |
| `start_device_pairing` | Builtin | Initiates Wisp BYOD pairing and returns device code and install instructions. |
| `device_bash` | Builtin | Executes shell commands on a user's paired local BYOD machine. |
| `memory_list` | Builtin | Lists workspace memory and identity documents. |
| `memory_fetch` | Builtin | Fetches contents of a workspace memory document. |
| `memory_write` | Builtin | Appends text to a workspace memory document. |
| `memory_update` | Builtin | Searches and replaces specific text within a workspace memory document. |
| `search_skills` | Builtin | Searches skills across the internal registry, curated catalog, and community `skills.sh`. |
| `share_skill` | Builtin | Packages and publishes a skill (`private`, `access_controlled`, or `public`) from the pod to the registry. |
| `install_skill` | Builtin | Installs a skill onto the pod filesystem and auto-activates it. |
| `get_agent_details` | Builtin | Returns LLM model and version details for the agent. |
| `tool_exec` | Builtin | Sandboxed V8 isolate executing JavaScript code that programmatically chains and loops over multiple tools. |
| `check_secret` | Builtin | Checks if a named environment secret exists in vault. |
| `secret_request` | Builtin | Asynchronously requests a secret from the human user. |
| `secret_set` | Builtin | Encrypts and saves a key-value secret. |
| `secret_list` | Builtin | Lists all stored secret names and descriptions. |
| `secret_delete` | Builtin | Deletes a stored secret by name. |

---

### Wingman & Background Subagent Management Tools
*Location: [`cortex/core/workflows/wingman/toolsets.go`](file:///Users/animeshdhillon/Desktop/work/projects/mono/cortex/core/workflows/wingman/toolsets.go)*

| Tool Name | Type | Description |
| :--- | :--- | :--- |
| `spawn_agent` | Dynamic Subagent | Spawns a background or inline child agent with difficulty settings, optional fork context, and task. |
| `agent_status` | Inline Tool | Checks the execution status of a running background subagent. |
| `close_agent` | Inline Tool | Cancels and terminates a running background subagent. |
| `agent_list` | Inline Tool | Lists all active and completed background subagents. |
| `resume_agent` | Inline Tool | Resumes a completed background subagent with follow-up instructions. |
| `agent_output` | Inline Tool | Fetches summary or full paginated conversation history of a background subagent. |
| `send_input` | Inline Tool | Sends additional input / messages to an active background subagent. |

---

### Cortex Debugger MCP Server Tools
*Location: [`cortex/core/debugger/tools/`](file:///Users/animeshdhillon/Desktop/work/projects/mono/cortex/core/debugger/tools/)*

| Tool Name | Description |
| :--- | :--- |
| `get_workflow_history` | Fetches full Temporal workflow execution history. |
| `get_message_content` | Retrieves full content of a specific message ID. |
| `get_job_sessions` | Lists all sessions associated with a job ID. |
| `get_workflows_by_job` | Returns all Temporal workflows executed for a job. |
| `get_session_messages` | Fetches full chronological message trajectory for a session. |
| `get_activity_logs` | Retrieves execution logs for a specific Temporal activity. |
| `get_recent_workflows` | Lists recent workflow executions across the cluster. |
| `get_agent_spec` | Returns the resolved Agent Spec YAML/JSON from the database. |
| `get_job_logs` | Queries Loki/pod logs for a job ID. |
| `get_agent_config` | Returns runtime configuration for an agent. |
| `get_job_cost_summary` | Returns token consumption and cost breakdown for a job. |

---

### Cortex Subagent Definitions
*Location: [`cortex/resources/agents/`](file:///Users/animeshdhillon/Desktop/work/projects/mono/cortex/resources/agents/)*

* **QA & Testing Subagents:**
  - `testing_agent_v4_sonnet_4_6` (Farm testing subagent v4)
  - `testing_agent_t2_opus_4_6` (Farm testing subagent T2)
  - `testing_agent_v4_fork_sonnet_4_6` (Fork testing subagent v4)
  - `testing_agent_v3_fork_opus_4_5` (Fork testing subagent v3)
  - `testing_agent_t2_fork_opus_4_5` (Fork testing subagent T2)
  - `deep_testing_backend_nextjs_sonnet_4` (Next.js backend testing subagent)
  - `deep_testing_frontend_nextjs_sonnet_4` (Next.js frontend UI testing subagent)
  - `expo_testing_agent_v4_sonnet_4_6` / `...fork_sonnet_4_6` (Mobile Expo testing subagents)
  - `expo_frontend_testing_agent_sonnet_4` (Expo frontend testing subagent)
  - `expo_testing_agent_codex_5_3` (Expo Codex testing subagent)
  - `expo_testing_agent_v3_sonnet_4_5` (Expo v3 testing subagent)
* **Domain & Advisory Subagents:**
  - `vision_expert_agent_sonnet_4` (Vision and image asset curation subagent)
  - `design_agent_full_y_snowball` (Frontend UI/UX design subagent)
  - `troubleshoot_agent_sonnet_4_5` (Read-only root cause analysis and diagnosis subagent)
  - `support_agent_sonnet_4_5` / `support_agent_sonnet_4` (Support inquiries and platform capability subagent)
  - `deployment_agent_sonnet_4_5` (Deployment verification and pipeline subagent)
  - `expert_opinion_agent_opus` (High-reasoning architecture and code review subagent)
* **Wingman Specialized Subagents:**
  - `wingman-coder` (Autonomous coding and repository execution agent)
  - `wingman-schedule` (Cron & one-shot background scheduled task runner)
  - `wingman-nurture` (Autonomous customer relationship & proactive outreach agent)

---

# 2. Wingman Service (Autonomous Personal Assistant)

### Gateway MCP Server Tools
*Location: [`wingman/base/mcp_endpoint.py`](file:///Users/animeshdhillon/Desktop/work/projects/mono/wingman/base/mcp_endpoint.py)*

| Tool Name | Description |
| :--- | :--- |
| `channel_search` | Natural language search for channel-specific tools; dynamically injects matching tools into context. |
| `create_schedule` | Creates recurring (cron) or one-shot (`fire_at`) scheduled tasks with timezone support. |
| `list_schedules` | Lists all active and paused schedules for the user. |
| `delete_schedule` | Permanently deletes a schedule. |
| `pause_schedule` | Pauses an active recurring schedule. |
| `resume_schedule` | Resumes a paused schedule. |
| `edit_schedule` | Updates schedule parameters in-place (task, cron, time, channel, execution mode). |
| `get_schedule_runs` | Retrieves historical execution logs and outputs for a schedule. |
| `schedule_state_get` | Reads durable state key/values for the currently executing schedule. |
| `schedule_state_set` | Writes durable state key/values for the currently executing schedule. |
| `schedule_state_delete` | Deletes durable state key/values for the current schedule run. |
| `upload_file` | Uploads environment files to cloud storage and generates markdown-embeddable public URLs. |
| `get_nurture_context` | Fetches nurture cadence progress, past events, and user context. |
| `send_nurture_message` | Evaluates guardrails and delivers candidate nurture messages. |
| `unsubscribe_nurture` | Disables future nurture messages and cancels nurture schedules. |
| `run_info` | Persists durable user facts (preferences, timezone, names, contacts) across sessions. |
| `connect_<channel>` | Hidden registration tools (`connect_telegram`, `connect_whatsapp`, `connect_slack`, `connect_imessage`). |

---

### Channel Outbound Action Tools
*Location: [`wingman/base/channels/`](file:///Users/animeshdhillon/Desktop/work/projects/mono/wingman/base/channels/)*

| Channel | Tool Name | Description |
| :--- | :--- | :--- |
| **Telegram** | `telegram_send_message` | Sends text message to a Telegram chat. |
| | `telegram_send_inline_keyboard` | Sends interactive buttons to Telegram. |
| | `telegram_send_photo` | Sends photo attachment to Telegram. |
| **WhatsApp** | `whatsapp_send_message` | Sends text message to a WhatsApp recipient. |
| | `whatsapp_send_quick_reply` | Sends interactive quick-reply buttons. |
| | `whatsapp_send_media` | Sends media/document attachments. |
| | `whatsapp_send_reaction` | Reacts to messages with emojis. |
| **Slack** | `slack_send_message` | Sends messages or thread replies to Slack channels/DMs. |
| **iMessage** | `imessage_send_message` | Sends Apple iMessage to a phone number. |
| **Web** | `web_send_message` | Sends streaming message to Web UI. |
| **Test** | `test_send_message` | Sends message to mock test harness channel. |

---

### Composio & Third-Party Integration Meta-Tools
*Location: [`wingman/base/integrations/mcp_server.py`](file:///Users/animeshdhillon/Desktop/work/projects/mono/wingman/base/integrations/mcp_server.py)*

| Tool Name | Description |
| :--- | :--- |
| `search_tools` (`composio_search_tools`) | Searches third-party app actions (Gmail, GitHub, Notion, Calendar, etc.) by natural language query. |
| `get_tool_schemas` (`composio_get_tool_schemas`) | Fetches input/output parameter schemas for Composio action slugs. |
| `manage_connections` (`composio_manage_connections`) | Generates OAuth connection links for external apps. |
| `disconnect_integration` (`composio_disconnect_integration`) | Revokes and disconnects an external OAuth integration. |
| `execute_tool` (`composio_multi_execute_tool`) | Executes third-party actions with automatic parameter validation and data sanitization. |

---

# 3. Emergent Plugin Library (Sandbox & Pod MCP Server)

*Location: [`emergent/plugin_library/plugins/tools/agent/mcp_tools.py`](file:///Users/animeshdhillon/Desktop/work/projects/mono/emergent/plugin_library/plugins/tools/agent/mcp_tools.py), [`bash_tools.py`](file:///Users/animeshdhillon/Desktop/work/projects/mono/emergent/plugin_library/plugins/tools/agent/bash_tools.py), [`skill_tools.py`](file:///Users/animeshdhillon/Desktop/work/projects/mono/emergent/plugin_library/plugins/tools/agent/skill_tools.py), [`screenshot_tools.py`](file:///Users/animeshdhillon/Desktop/work/projects/mono/emergent/plugin_library/plugins/tools/agent/screenshot_tools.py)*

| Tool Name | Category | Description |
| :--- | :--- | :--- |
| `view_file` | File Ops | Reads file contents with 1-indexed pagination (up to 2000 lines) or lists directory trees. |
| `view_bulk` | File Ops | Reads multiple files or directory listings in a single batched call. |
| `read` | File Ops | Universal reader for files, images, PDFs, or HTTP/HTTPS URLs. |
| `create_file` | File Ops | Creates or overwrites files with exact text content. |
| `apply_patch` | File Ops | Applies OpenAI V4A/Codex unified diffs to create, update, or delete files. |
| `apply_patch_freeform` | File Ops | Applies lenient freeform patches across the codebase. |
| `search_replace` | File Ops | Replaces exact strings in a file with whitespace preservation. |
| `multi_search_replace` | File Ops | Executes multiple atomic search-and-replace edits in sequence. |
| `insert_text` | File Ops | Inserts text after a specified 1-indexed line number. |
| `bulk_file_writer` | File Ops | Concurrently creates/updates multiple files with atomic disk writes. |
| `glob_files` | File Ops | Fast pattern matcher searching files while honoring `.gitignore`. |
| `lint_python` | Linters | Runs Ruff linter on Python code with optional safe autofixing. |
| `lint_javascript` | Linters | Runs ESLint on JS/TS/JSX/TSX code with optional safe autofixing. |
| `execute_bash` | Shell | Runs bash commands with stdout/stderr capture and process management. |
| `execute_bash_streaming` | Shell | Runs commands with partial streaming capture and background `process_id` support. |
| `manage_bash_process` | Shell | Polls stdout/stderr, checks status, or kills background processes started by streaming bash. |
| `browser_automation` | Browser QA | Runs Python Playwright scripts in headless Chromium with console log capture. |
| `screenshot_tool` | Browser QA | Captures webpage screenshots using Python Playwright. |
| `screenshot_tool_ts` / `take_screenshot` | Browser QA | Captures webpage screenshots using inline TypeScript Playwright. |
| `run_ts_playwright` | Browser QA | Runs complete TypeScript `.spec.ts` files or inline specs with assertions and screenshot attachments. |
| `run_browser_use` | Browser QA | Autonomous AI browser agent driven by natural language test cases returning pass/fail verdicts. |
| `todo_write` | Planning | Manages session task lists (`pending`, `in_progress`, `completed`, `cancelled`). |
| `check_pod_resources` | System | Checks cgroup memory usage, CPU load, and disk space on the pod. |
| `list_skills` | Skills | Lists all local skill definitions installed on the pod. |
| `load_skill` | Skills | Loads `SKILL.md` content and resources for a local skill. |

---

# 4. Emergent Agent Service (Python Engine)

### Core Python Tools
*Location: [`emergent/agents/tools/tool_set.py`](file:///Users/animeshdhillon/Desktop/work/projects/mono/emergent/agents/tools/tool_set.py) and [`emergent/agents/tools/impl/`](file:///Users/animeshdhillon/Desktop/work/projects/mono/emergent/agents/tools/impl/)*

| Class Name | Wire Name | Description |
| :--- | :--- | :--- |
| `AnalyzeFileTool` | `analyze_file_tool` | Deep AST and semantic code structure analyzer. |
| `AskHumanTool` | `ask_human` | Human-in-the-loop requirement gathering tool. |
| `BatchTool` | `batch_tool` | Batch execution wrapper for multiple tools. |
| `BrowserAutomationTool` | `browser_automation_tool` | Headless browser execution bridge. |
| `BulkFileEditorTool` | `bulk_file_editor_tool` | Bulk file editing tool. |
| `BulkFileWriterTool` / `BulkFileWriterToolV1` | `bulk_file_writer` | Multi-file writer. |
| `ClaudeTool` | `claude_tool` | Direct Claude tool caller. |
| `CmdRunTool` | `cmd_run` | Shell execution tool on the pod. |
| `ComputerUseTool` | `computer_use` | Anthropic Computer Use / OS GUI automation tool. |
| `ComputerUseStatusTool` | `computer_use_status_tool` | Status monitor for Computer Use sessions. |
| `CrawlTool` | `crawl_tool` | Webpage crawler and scraper. |
| `DefaultTool` | `default_tool` | Generic tool fallback handler. |
| `DeployLogsTool` | `deploy_logs_tool` | Pipeline build and deployment log reader. |
| `ExternalIntegrationTool` | `external_integration_tool` | External integration invoker. |
| `ExtractFileTool` | `extract_file_tool` | Archive/zip extractor. |
| `FileEditorCreateTool` | `create` | File creation tool. |
| `FileEditorInsertTool` | `insert` | Line insertion tool. |
| `FileEditorSearchReplaceTool` | `search_replace` | String search and replace tool. |
| `FileEditorViewTool` | `view` | File viewing tool. |
| `FindFileTool` | `find_file` | File search by path. |
| `FinishTool` | `finish` | Task completion and PRD update tool. |
| `GetAssetsTool` | `get_assets_tool` | Asset and media fetcher. |
| `GlobTool` | `glob_tool` | Glob pattern file matcher. |
| `GrepTool` | `grep_tool` | Regex text search tool. |
| `ImageGenerationTool` | `image_generation_tool` | AI image generation. |
| `ImageSelectorTool` | `image_selector_tool` | Stock image search and context ranking tool. |
| `IntegrationTool` | `integration_tool` | Playbook knowledge tool. |
| `MCPDirectExecutionTool` | `mcp_direct_execution_tool` | Direct MCP caller. |
| `OpenAITool` | `openai_tool` | OpenAI LLM execution tool. |
| `PerplexityDeepResearchTool` | `perplexity_deep_research_tool` | Web research via Perplexity. |
| `PlanTool` | `plan_tool` | Implementation plan generator. |
| `ProxyTool` | `proxy_tool` | LLM proxy wrapper. |
| `ReplyTool` | `reply_tool` | Chat response generator. |
| `QueryRepoExpertTool` | `repo_expert_tool` | Codebase Q&A and semantic repository query tool. |
| `ScreenshotTool` | `screenshot_tool` | Webpage screenshot tool. |
| `SearchDirNameTool` | `search_dir_name` | Directory name search tool. |
| `SearchFileNameTool` | `search_file_name` | File name search tool. |
| `SkilledAgentTool` | `skill_tool` | Dynamic subagent invoker for user & system skills. |
| `StrReplaceEditorTool` / `StrReplaceEditorToolV1` | `str_replace_editor` | String replacement editor. |
| `StyleSelectorTool` | `style_selector_tool` | Design system / styling selector. |
| `SummaryTool` | `summary_tool` | Trajectory summarizer. |
| `TestingAgentFinishTool` | `testing_agent_finish_tool` | Testing subagent completion tool. |
| `ThinkTool` | `think_tool` | Reasoning scratchpad. |
| `TimHandoffTool` | `tim_handoff_tool` | Agent handoff tool. |
| `ValidationTool` | `validation_tool` | Code and build validation tool. |
| `ViewBulkTool` | `view_bulk` | Batch file reader. |
| `WebSearchTool` / `WebSearchToolV2` | `web_search_tool` | Web search tool. |

---

### Python Agent & Subagent Roles
*Location: [`emergent/agents/emergent_e1/`](file:///Users/animeshdhillon/Desktop/work/projects/mono/emergent/agents/emergent_e1/)*

* `EmergentAssistant` — Primary full-stack application builder agent.
* `ChatAssistant` — Conversational, brainstorming, and support agent.
* `SkilledAssistant` — Dynamic subagent executor for specialized skills.
* `AgenticCodeQnaAgent` — Semantic repository Q&A subagent.
* `CUAAgent` — Computer use & browser agent via Browserbase.
* `EditAssistant` (`str_replace_editor`, `edit_agent_v0`, `edit_agent_v1`) — Specialized code-editing agents.

---

# 5. Emergent Platform MCP Server

*Location: [`mcp/server.py`](file:///Users/animeshdhillon/Desktop/work/projects/mono/mcp/server.py) and [`mcp/tools/`](file:///Users/animeshdhillon/Desktop/work/projects/mono/mcp/tools/)*

### User Tools (API-Only)
| Tool Name | Description |
| :--- | :--- |
| `login` | Authenticates user session with credentials. |
| `submit_job` | Submits a new agent job / app build. |
| `list_jobs` | Lists user jobs and current statuses. |
| `get_job_status` | Retrieves status and progress for a job. |
| `send_hitl` | Sends human feedback / prompt to an active job. |
| `cancel_job` | Cancels a running job. |
| `watch_job` | Streams realtime events from a running job. |

### Dev / Admin Tools (Admin-Gated)
| Tool Name | Description |
| :--- | :--- |
| `get_messages` | Fetches full conversation message logs for a job. |
| `get_tool_summary` | Returns aggregated tool call metrics for a job. |
| `get_errors` | Extracts errors from logs. |
| `get_test_results` | Fetches test results from the sandbox pod. |
| `get_testing_analysis` | Returns comprehensive QA testing analysis. |
| `rollback_job` | Rolls back codebase to a previous checkpoint. |
| `list_rollback_points` | Lists available rollback commit points. |
| `get_pod` | Fetches Kubernetes pod status for a job. |
| `pod_exec` | Executes bash commands inside the job's pod. |
| `query_db` | Runs readonly SQL queries on the database. |
| `pause_environment` | Pauses the sandbox pod. |
| `restart_environment` | Wakes up / restarts the sandbox pod. |
| `get_env` | Fetches environment variables and configs. |

---

# 6. XTools Service

*Location: [`xtools/core/`](file:///Users/animeshdhillon/Desktop/work/projects/mono/xtools/core/) and [`xtools/resources/skills/emergent/`](file:///Users/animeshdhillon/Desktop/work/projects/mono/xtools/resources/skills/emergent/)*

### Skills MCP Tools
| Tool Name | Description |
| :--- | :--- |
| `list_skills` | Lists all curated integration skill packs. |
| `search_skills` | Searches curated skills by keyword or intent. |
| `load_skill` | Loads `SKILL.md` content and reference file list. |
| `explore_skill` | Reads reference implementation documents inside a skill. |
| `filter_skills` | Filters skills by category, tag, or technology. |

### Agent & Orchestrator Tools
| Tool Name | Category | Description |
| :--- | :--- | :--- |
| `status` | Agent | Gets agent execution status. |
| `send_message` | Agent | Sends a message to the agent. |
| `pause` | Agent | Pauses agent execution. |
| `preview` | Agent | Retrieves agent preview URL. |
| `trajectories` | Agent | Queries agent event trajectories. |
| `create_job` | Orchestrator | Creates a new orchestrator job. |
| `list_jobs` | Orchestrator | Lists orchestrator jobs. |
| `job_status` | Orchestrator | Returns status of an orchestrator job. |
| `job_preview` | Orchestrator | Retrieves preview URL of an orchestrator job. |
| `job_send_message` | Orchestrator | Sends a message to an orchestrator job. |
| `job_pause` | Orchestrator | Pauses an orchestrator job. |
| `job_trajectories` | Orchestrator | Queries trajectories for an orchestrator job. |
| `deploy_job` | Orchestrator | Deploys an orchestrator job. |

### Curated Integration Skillpacks
* `stripe-payment`
* `emergent-auth`
* `jwt-auth`
* `llm-chat`
* `universal-key`
* `llm-chat-image-attachments`
* `openai-image-generation`
* `gemini-image-generation`
* `razorpay`
* `paypal`
* `resend-email`
* `sendgrid`
* `twilio-sms`
* `openai-speech-to-text`
* `openai-text-to-speech`
* `sora-video-generation`
* `emergent-object-store`

---

# 7. Deployer MCP Server

*Location: [`deployer/core/mcp/tools/`](file:///Users/animeshdhillon/Desktop/work/projects/mono/deployer/core/mcp/tools/) and [`deployer/cmd/`](file:///Users/animeshdhillon/Desktop/work/projects/mono/deployer/cmd/)*

| Tool Name | Category | Description |
| :--- | :--- | :--- |
| `get_app_details` | Deployment | Fetches app configurations, domains, and deployment state. |
| `get_recent_deployments` | Deployment | Lists recent deployment pipeline runs. |
| `get_pipeline_logs` | Deployment | Fetches build and deploy pipeline logs. |
| `get_app_logs` | Deployment | Queries runtime application logs from Loki. |
| `get_job_logs` | Deployment | Queries logs for a specific job ID. |
| `get_cloud_build_logs` | Deployment | Fetches Google Cloud Build logs. |
| `get_domain_status` | Deployment | Queries Cloudflare DNS and domain routing status. |
| `get_app_secrets` | Deployment | Fetches application secrets and environment variables. |
| `mongo_query` | Deployment | Runs readonly queries on customer MongoDB databases. |
| `get_pod_details` | Deployment | Queries Kubernetes pod health and resource usage via kubectl. |
| `create_deployment_manifest` | Deployment | Generates deployment manifest YAML. |
| `update_deployment_manifest` | Deployment | Updates existing deployment manifest in GCS. |
| `get_deployment_manifest` | Deployment | Downloads deployment manifest from GCS. |
| `support_ticket_messages` | Support | Fetches message thread from Atlas.so support tickets. |
| `support_ticket_internal_note` | Support | Posts internal investigation notes to Atlas.so tickets. |

---

# 8. Oracle Support Agents & Subagents

*Location: [`oracle/resources/agents/`](file:///Users/animeshdhillon/Desktop/work/projects/mono/oracle/resources/agents/)*

### Main Support Agents
* `oracle_ticket_agent_sonnet_4_5` — Primary ticket routing and finding synthesis agent.
* `oracle_ticket_agent_sonnet_4_5_testing` — Testing version of ticket triage agent.
* `l3_assistant_agent` — Interactive L3 admin support agent for ticket investigation.

### Specialized Support Subagents
* `subagents-troubleshoot_agent_sonnet_4_5` (`troubleshoot_agent_sonnet_4_5`) — Read-only RCA diagnosis subagent.
* `subagents-support_agent_sonnet_4_5` / `...sonnet_4` (`support_agent_sonnet_4_5`) — Customer Q&A and capabilities subagent.
* `subagents-vision_expert_agent_sonnet_4` (`vision_expert_agent_sonnet_4`) — Image asset curation subagent.
* `subagents-preview_support_agent_sonnet_4_5` / `...testing` — Preview environment debugging subagent.
* `subagents-deployment_support_agent_sonnet_4_5` / `...testing` — Deployment error analysis subagent.
* `subagents-expo_support_agent_sonnet_4_5` — Mobile Expo debugging subagent.
* `subagents-deployment_agent_sonnet_4_5` — Deployment pipeline verification subagent.
* `subagents-expert_opinion_agent_opus` — Opus code review and architectural opinion subagent.
* `subagents-general_support_agent_sonnet_4_5` / `...testing` — General customer inquiry subagent.
* `subagents-auto_support_investigator_sonnet_4_5` — Autonomous ticket investigation subagent.