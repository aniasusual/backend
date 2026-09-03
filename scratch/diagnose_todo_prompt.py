"""
Diagnostic script to test 'build me a to-do app' prompt with local qwen2.5-coder:7b,
recording every token, tool call, turn, and analyzing why it may stop prematurely.
"""

import asyncio
import json
import time
from pathlib import Path

from project_manager.manager import ProjectManager
from plugins.coding_harness import CodingHarness
from tools.registry import ToolRegistry


async def diagnose():
    print("=" * 80)
    print("🔍 DIAGNOSTIC RUN: Prompt = 'build me a to-do app'")
    print("=" * 80)

    pm = ProjectManager()
    if "diag-todo-app" in [p.name for p in pm.list_projects()]:
        pm.delete_project("diag-todo-app")

    project = pm.create_project("diag-todo-app", template="node_react")
    print(f"Project scaffolded at: {project.path}")

    registry = ToolRegistry(project.path)
    server_res = registry.start_dev_server()
    print(f"Dev server started: Frontend :{server_res['port']} | API :{server_res['backend_port']}")

    prompt = "build me a to-do app"
    print(f"\nUser Prompt: \"{prompt}\"")

    harness = CodingHarness(model_name="qwen2.5-coder:7b")
    context = {
        "registry": registry,
        "messages": [],
        "project": project,
        "request_approval": None,
    }

    turn_count = 0
    all_events = []
    start_time = time.time()

    print("\n--- STREAMING AGENT EXECUTION ---")
    async for update in harness.process_prompt(prompt, context):
        all_events.append(update)
        u_type = update.get("type")
        
        if u_type == "thought":
            thought_preview = update.get("content", "")
            print(f"[Thought Token] {repr(thought_preview)}")
        elif u_type == "tool_call":
            turn_count += 1
            print(f"\n⚡ [Turn {turn_count}] TOOL CALL: {update.get('name')}")
            print(f"   Args: {json.dumps(update.get('arguments', {}), indent=2)}")
        elif u_type == "tool_result":
            print(f"   Result: {str(update.get('result', ''))[:120]}...")
        elif u_type == "token":
            print(f"[Content Token] {repr(update.get('content', ''))}")
        elif u_type == "status":
            print(f"\nℹ️ [Status] {update.get('content')}")

    duration = time.time() - start_time
    print(f"\nExecution finished in {duration:.2f}s across {turn_count} tool turns.")

    print("\n" + "=" * 80)
    print("📊 POST-MORTEM ANALYSIS:")
    print("=" * 80)

    # Inspect files
    server_path = project.path / "server" / "index.js"
    app_path = project.path / "src" / "App.jsx"
    css_path = project.path / "src" / "index.css"

    print("\n1. File State Check:")
    print(f"   server/index.js: {len(server_path.read_text())} chars")
    print(f"   src/App.jsx:      {len(app_path.read_text())} chars")
    print(f"   src/index.css:    {len(css_path.read_text())} chars")

    print("\n2. server/index.js Content:")
    print("-" * 50)
    print(server_path.read_text()[:600])
    print("-" * 50)

    print("\n3. src/App.jsx Content:")
    print("-" * 50)
    print(app_path.read_text()[:600])
    print("-" * 50)

    print("\n4. Message History Dump:")
    print(json.dumps(context["messages"], indent=2)[:1500])

    registry.cleanup()
    pm.delete_project("diag-todo-app")


if __name__ == "__main__":
    asyncio.run(diagnose())
