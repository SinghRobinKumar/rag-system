"""
RAG System — FastAPI Application Entry Point.

A local Retrieval-Augmented Generation system with:
- Directory-based document organization
- Ollama LLM integration (swappable models)
- ChromaDB vector storage
- Hybrid memory management
- File upload + automatic directory watching
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.config import FRONTEND_DIR, DATA_DIR
from backend.services.vector_store import vector_store
from backend.services.file_watcher import file_watcher
from backend.routers import chat, documents, settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # ── Startup ──
    print("=" * 60)
    print("  RAG System Starting Up...")
    print("=" * 60)

    # Initialize vector store
    vector_store.initialize()

    # Create default data directories
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for default_dir in ["clients", "vendors", "customers"]:
        (DATA_DIR / default_dir).mkdir(exist_ok=True)

    # Start file watcher
    loop = asyncio.get_running_loop()
    file_watcher.start(loop)

    print("=" * 60)
    print("  RAG System Ready!")
    print(f"  Frontend:  http://localhost:8000")
    print(f"  API Docs:  http://localhost:8000/docs")
    print(f"  Data Dir:  {DATA_DIR}")
    print("=" * 60)

    yield

    # ── Shutdown ──
    print("\n[Shutdown] Cleaning up...")
    file_watcher.stop()
    await vector_store._client.close() if hasattr(vector_store, '_client') else None
    print("[Shutdown] Done.")


# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="RAG Document System",
    description="Local RAG system with directory-based document intelligence",
    version="1.0.0",
    lifespan=lifespan,
)

# ─── CORS ────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── API Routers ─────────────────────────────────────────────────────────────

app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(settings.router)

# ─── Static Files (Frontend) ────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def serve_frontend():
    """Serve the main frontend page."""
    return FileResponse(str(FRONTEND_DIR / "index.html"))
