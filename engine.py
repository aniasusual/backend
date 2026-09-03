import json
import asyncio
import traceback
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, APIRouter, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import os
import ollama

from config.settings import (
    BACKEND_HOST,
    BACKEND_PORT,
    OLLAMA_HOST,
    DEFAULT_MODEL_ID,
    CORS_ORIGINS,
)
from harness_manager import HarnessManager
from tools.registry import ToolRegistry
from project_manager.manager import ProjectManager
from project_manager.chat_history import ChatHistoryManager
from utils.hardware import detect_hardware
from config.models import build_model_catalog

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
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
# REST API: System & Hardware Inspection
# ──────────────────────────────────────────────

system_router = APIRouter(prefix="/api/system", tags=["system"])


@system_router.get("/models-and-hardware")
async def get_models_and_hardware():
    """Returns detected hardware specifications, annotated model catalog, and Ollama connection status."""
    hw = detect_hardware()
    ollama_running = True
    installed_tags: List[Dict[str, Any]] = []

    try:
        client = ollama.AsyncClient(host=OLLAMA_HOST)
        tags_res = await client.list()
        installed_tags = [
            m.model_dump() if hasattr(m, "model_dump") else m.__dict__
            for m in tags_res.models
        ]
    except Exception as e:
        ollama_running = False
        print(f"[SystemAPI] Ollama connection error: {e}")

    catalog = build_model_catalog(installed_tags, hw)
    return {
        "hardware": hw,
        "models": catalog,
        "active_model": DEFAULT_MODEL_ID,
        "ollama_running": ollama_running,
    }


app.include_router(system_router)

# ──────────────────────────────────────────────
# REST API: Model Management (Pull & Delete)
# ──────────────────────────────────────────────

models_router = APIRouter(prefix="/api/models", tags=["models"])


class ModelPullRequest(BaseModel):
    model: str


@models_router.post("/pull")
async def pull_model(data: ModelPullRequest):
    """Streams pull/download progress for an Ollama model via Server-Sent Events."""
    model_name = data.model.strip()
    if not model_name:
        raise HTTPException(status_code=400, detail="Model name is required")

    async def progress_generator():
        client = ollama.AsyncClient(host=OLLAMA_HOST)
        try:
            stream = await client.pull(model=model_name, stream=True)
            async for chunk in stream:
                total = getattr(chunk, "total", 0) or 0
                completed = getattr(chunk, "completed", 0) or 0
                status = getattr(chunk, "status", "") or "downloading"
                percent = round((completed / total) * 100, 1) if total > 0 else 0.0

                payload = {
                    "status": status,
                    "completed": completed,
                    "total": total,
                    "percent": percent,
                    "done": status == "success",
                }
                yield f"data: {json.dumps(payload)}\n\n"
        except Exception as e:
            payload = {"status": "error", "error": str(e), "done": True}
            yield f"data: {json.dumps(payload)}\n\n"

    return StreamingResponse(progress_generator(), media_type="text/event-stream")


@models_router.delete("/{model_name:path}")
async def delete_model(model_name: str):
    """Deletes an installed model from local Ollama storage."""
    model_name = model_name.strip()
    if not model_name:
        raise HTTPException(status_code=400, detail="Model name is required")

    try:
        client = ollama.AsyncClient(host=OLLAMA_HOST)
        await client.delete(model=model_name)
        return {"status": "deleted", "model": model_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete model: {str(e)}")


app.include_router(models_router)

# ──────────────────────────────────────────────
# REST API: Project Management
# ──────────────────────────────────────────────

projects_router = APIRouter(prefix="/api/projects", tags=["projects"])

class ProjectCreate(BaseModel):
    name: str
    template: str = "node_react"

@projects_router.get("")
def list_projects():
    return [p.to_dict() for p in project_manager.list_projects()]

@projects_router.get("/suggest-name")
def suggest_name(base: str = "app"):
    return {"suggested_name": project_manager.suggest_name(base)}

@projects_router.post("")
def create_project(data: ProjectCreate):
    try:
        project = project_manager.create_project(data.name, template=data.template)
        return project.to_dict()
    except (ValueError, RuntimeError) as e:
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

@projects_router.get("/{name}/chat")
def get_project_chat(name: str):
    try:
        project = project_manager.get_project(name)
        return {
            "history": ChatHistoryManager.load_history(project.path),
            "ui_events": ChatHistoryManager.get_ui_events(project.path),
        }
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
    
    active_project = project_manager.get_or_create_project("default")
    session_messages: List[Dict[str, Any]] = ChatHistoryManager.get_llm_messages(active_project.path)
    
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

    async def run_harness_task(prompt: str, harness_name: str, model_name: Optional[str] = None):
        try:
            harness = harness_manager.get_harness(harness_name)
            context = {
                "registry": active_registry,
                "messages": session_messages,
                "request_approval": request_approval,
                "project": active_project,
                "model": model_name or DEFAULT_MODEL_ID,
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
                    session_messages.extend(ChatHistoryManager.get_llm_messages(active_project.path))
                    await websocket.send_json({"type": "project_opened", "project": active_project.to_dict()})

                    # Send persistent visual chat history to the frontend
                    ui_events = ChatHistoryManager.get_ui_events(active_project.path)
                    await websocket.send_json({
                        "type": "chat_history_loaded",
                        "project": active_project.name,
                        "messages": ui_events,
                    })

                    # Auto-boot dev server if package.json exists to render preview immediately
                    if (active_project.path / "package.json").exists():
                        try:
                            active_registry.start_dev_server()
                        except Exception as dev_err:
                            print(f"[AutoBoot] Error starting dev server: {dev_err}")

                except ValueError as e:
                    await websocket.send_json({"type": "error", "content": str(e)})
                continue

            if message.get("action") == "stop_preview":
                active_registry.cleanup()
                continue

            if message.get("action") == "restart_preview":
                active_registry.cleanup()
                if (active_project.path / "package.json").exists():
                    active_registry.start_dev_server()
                continue

            if message.get("action") == "close_project":
                active_registry.cleanup()
                session_messages.clear()
                continue

            if message.get("action") == "clear":
                session_messages.clear()
                ChatHistoryManager.clear_history(active_project.path)
                await websocket.send_json({"type": "chat_history_loaded", "project": active_project.name, "messages": []})
                await websocket.send_json({"type": "status", "content": "Session context reset."})
                continue

            prompt = message.get("prompt", "")
            harness_name = message.get("harness", "CodingHarness")
            model_name = message.get("model")

            if prompt:
                if harness_task and not harness_task.done():
                    harness_task.cancel()
                    await asyncio.sleep(0) # Let event loop process cancellation
                
                harness_task = asyncio.create_task(run_harness_task(prompt, harness_name, model_name))

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
    uvicorn.run("engine:app", host=BACKEND_HOST, port=BACKEND_PORT, reload=True, reload_excludes=["venv/*", "*.log"])

