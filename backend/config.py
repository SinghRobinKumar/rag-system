"""
Central configuration for the RAG system.
All values can be overridden via environment variables.
"""
import os
from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("RAG_DATA_DIR", str(BASE_DIR / "data")))
CHROMA_DIR = Path(os.getenv("RAG_CHROMA_DIR", str(BASE_DIR / "chroma_db")))
SESSIONS_DIR = Path(os.getenv("RAG_SESSIONS_DIR", str(DATA_DIR / "sessions")))
FRONTEND_DIR = BASE_DIR / "frontend"

SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


# ─── Ollama ──────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_CHAT_MODEL = os.getenv("RAG_CHAT_MODEL", "gemma3:1b")
DEFAULT_EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "nomic-embed-text")

# ─── Chunking ────────────────────────────────────────────────────────────────
CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "1024"))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "100"))

# ─── Retrieval ───────────────────────────────────────────────────────────────
TOP_K_RESULTS = int(os.getenv("RAG_TOP_K", "8"))

# ─── Memory / Context ───────────────────────────────────────────────────────
SLIDING_WINDOW_TURNS = int(os.getenv("RAG_SLIDING_WINDOW", "5"))
MAX_CONTEXT_TOKENS = int(os.getenv("RAG_MAX_CONTEXT_TOKENS", "6500"))
SUMMARIZE_AFTER_TURNS = int(os.getenv("RAG_SUMMARIZE_AFTER", "5"))

# ─── File Watcher ────────────────────────────────────────────────────────────
WATCH_DEBOUNCE_SECONDS = float(os.getenv("RAG_WATCH_DEBOUNCE", "3.0"))

# ─── Supported File Types ───────────────────────────────────────────────────
SUPPORTED_EXTENSIONS = {
    ".pdf", ".txt", ".md", ".csv",
    ".docx", ".doc",
    ".xlsx", ".xls",
    ".png", ".jpg", ".jpeg", ".tiff", ".bmp",
    ".html", ".htm",
    ".json",
}

# ─── ChromaDB Collection ────────────────────────────────────────────────────
CHROMA_COLLECTION_NAME = "rag_documents"
