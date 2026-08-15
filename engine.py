import json
import asyncio
import traceback
from typing import Dict, Any, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, APIRouter, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os

from harness_manager import HarnessManager
from tools.registry import ToolRegistry
from project_manager.manager import ProjectManager

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

harness_manager = HarnessManager(PLUGINS_DIR)
project_manager = ProjectManager()

# ──────────────────────────────────────────────
# REST API: Project Management
# ──────────────────────────────────────────────

projects_router = APIRouter(prefix="/api/projects", tags=["projects"])

class ProjectCreate(BaseModel):
    name: str

@projects_router.get("")
def list_projects():
    return [p.to_dict() for p in project_manager.list_projects()]

@projects_router.get("/suggest-name")
def suggest_name(base: str = "app"):
    return {"suggested_name": project_manager.suggest_name(base)}

@projects_router.post("")
def create_project(data: ProjectCreate):
    try:
        project = project_manager.create_project(data.name)
        return project.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@projects_router.delete("/{name}")
def delete_project(name: str):
    try:
        project_manager.delete_project(name)
        return {"status": "deleted"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@projects_router.post("/{name}/open-in-finder")
def open_in_finder(name: str):
    try:
        project_manager.open_in_finder(name)
        return {"status": "opened"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

app.include_router(projects_router)

# ──────────────────────────────────────────────
# WebSocket: Agent Execution & Chat
# ──────────────────────────────────────────────

import uuid

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    session_messages: List[Dict[str, Any]] = []
    
    def sync_send_event(event: dict):
        try:
            loop = asyncio.get_running_loop()
            asyncio.run_coroutine_threadsafe(websocket.send_json(event), loop)
            
            # Also update project metadata if it's a preview event
            if event["type"] == "preview_ready":
                project_manager.update_meta(active_project.name, port=event.get("port"))
            elif event["type"] == "preview_stopped":
                project_manager.update_meta(active_project.name, port=None)
        except Exception as e:
            print(f"Error in event callback: {e}")

    active_project = project_manager.get_or_create_project("default")
        
    active_registry = ToolRegistry(active_project.path, event_callback=sync_send_event)

    pending_approvals: Dict[str, asyncio.Future] = {}
    harness_task = None
    
    async def request_approval(command: str, reason: str) -> bool:
        req_id = str(uuid.uuid4())
        fut = asyncio.get_running_loop().create_future()
        pending_approvals[req_id] = fut
        
        await websocket.send_json({
            "type": "command_approval_request",
            "request_id": req_id,
            "command": command,
            "reason": reason,
            "project": active_project.name
        })
        
        # Wait for user response
        approved = await fut
        if req_id in pending_approvals:
            del pending_approvals[req_id]
        return approved

    async def run_harness_task(prompt: str, harness_name: str):
        try:
            harness = harness_manager.get_harness(harness_name)
            context = {
                "registry": active_registry,
                "messages": session_messages,
                "request_approval": request_approval,
            }
            async for update in harness.process_prompt(prompt, context):
                await websocket.send_json(update)
        except asyncio.CancelledError:
            pass # Task was cancelled to start a new one
        except Exception as e:
            traceback.print_exc()
            try:
                await websocket.send_json({"type": "status", "content": f"Harness Error: {str(e)}"})
            except Exception:
                pass

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("action") == "command_approval":
                req_id = message.get("request_id")
                approved = message.get("approved", False)
                if req_id in pending_approvals:
                    pending_approvals[req_id].set_result(approved)
                continue

            if message.get("action") == "open_project":
                project_name = message.get("name")
                if not project_name:
                    await websocket.send_json({"type": "error", "content": "Project name required."})
                    continue
                
                try:
                    active_registry.cleanup()
                    active_project = project_manager.get_project(project_name)
                    active_registry = ToolRegistry(active_project.path, event_callback=sync_send_event)
                    session_messages.clear()
                    await websocket.send_json({"type": "project_opened", "project": active_project.to_dict()})
                except ValueError as e:
                    await websocket.send_json({"type": "error", "content": str(e)})
                continue

            if message.get("action") == "close_project":
                active_registry.cleanup()
                session_messages.clear()
                continue

            if message.get("action") == "clear":
                session_messages.clear()
                await websocket.send_json({"type": "status", "content": "Session context reset."})
                continue

            prompt = message.get("prompt", "")
            harness_name = message.get("harness", "CodingHarness")

            if prompt:
                if harness_task and not harness_task.done():
                    harness_task.cancel()
                    await asyncio.sleep(0) # Let event loop process cancellation
                
                harness_task = asyncio.create_task(run_harness_task(prompt, harness_name))

    except WebSocketDisconnect:
        print("Client disconnected")
        active_registry.cleanup()
        if harness_task and not harness_task.done():
            harness_task.cancel()
    except Exception as e:
        print(f"WebSocket error: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("engine:app", host="127.0.0.1", port=8000, reload=True, reload_excludes=["venv/*", "*.log"])
