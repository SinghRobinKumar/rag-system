"""
Settings API router.
Handles model management and system configuration.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from backend.services.ollama_client import ollama_client
from backend.services.vector_store import vector_store
from backend.services.file_watcher import file_watcher

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ModelSwitch(BaseModel):
    model_type: str  # "chat" or "embed"
    model_name: str


@router.get("/models")
async def list_models():
    """List all available Ollama models."""
    models = await ollama_client.list_models()
    return {
        "models": [
            {
                "name": m.get("name", "unknown"),
                "size": m.get("size", 0),
                "modified_at": m.get("modified_at", ""),
                "details": m.get("details", {}),
            }
            for m in models
        ],
        "current": ollama_client.get_current_models(),
    }


@router.get("/current")
async def get_current_config():
    """Get current system configuration."""
    return {
        "models": ollama_client.get_current_models(),
        "watcher_running": file_watcher.is_running,
    }


@router.put("/model")
async def switch_model(request: ModelSwitch):
    """Switch the active chat or embedding model."""
    if request.model_type == "chat":
        ollama_client.set_chat_model(request.model_name)
        return {
            "status": "success",
            "message": f"Chat model switched to {request.model_name}",
            "current": ollama_client.get_current_models(),
        }
    elif request.model_type == "embed":
        ollama_client.set_embed_model(request.model_name)
        return {
            "status": "success",
            "message": f"Embedding model switched to {request.model_name}",
            "current": ollama_client.get_current_models(),
        }
    else:
        return {
            "status": "error",
            "message": "model_type must be 'chat' or 'embed'",
        }


@router.get("/status")
async def system_status():
    """Full system health check."""
    ollama_available = await ollama_client.is_available()
    vs_stats = vector_store.get_stats()

    return {
        "ollama": {
            "available": ollama_available,
            "url": ollama_client.base_url,
            "models": ollama_client.get_current_models(),
        },
        "vector_store": vs_stats,
        "file_watcher": {
            "running": file_watcher.is_running,
        },
    }
