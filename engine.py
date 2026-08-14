import json
import asyncio
import traceback
from typing import Dict, Any, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import os

from harness_manager import HarnessManager
from tools.registry import ToolRegistry

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize singletons
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGINS_DIR = os.path.join(BASE_DIR, "plugins")
SANDBOX_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "sandbox")

harness_manager = HarnessManager(PLUGINS_DIR)
tool_registry = ToolRegistry(SANDBOX_DIR)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # Maintain conversation message history for the lifetime of this connection
    session_messages: List[Dict[str, Any]] = []

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            # Support clearing session history on explicit command
            if message.get("action") == "clear":
                session_messages.clear()
                await websocket.send_json(
                    {"type": "status", "content": "Session context reset."}
                )
                continue

            prompt = message.get("prompt", "")
            harness_name = message.get("harness", "CodingHarness")

            if not prompt:
                continue

            try:
                harness = harness_manager.get_harness(harness_name)
            except ValueError as e:
                await websocket.send_json(
                    {"type": "status", "content": f"Error: {e}"}
                )
                continue

            context = {
                "registry": tool_registry,
                "messages": session_messages,  # Pass persistent session history
            }

            # Process prompt and stream back
            try:
                async for update in harness.process_prompt(prompt, context):
                    await websocket.send_json(update)
            except WebSocketDisconnect:
                raise
            except Exception as e:
                traceback.print_exc()
                try:
                    await websocket.send_json(
                        {"type": "status", "content": f"Harness Error: {str(e)}"}
                    )
                except Exception:
                    pass

    except WebSocketDisconnect:
        print("Client disconnected")
        tool_registry.cleanup()
    except Exception as e:
        print(f"WebSocket error: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("engine:app", host="127.0.0.1", port=8000, reload=True, reload_excludes=["sandbox/*", "venv/*", "*.log"])
