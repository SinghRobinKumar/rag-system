"""
Document ingestion pipeline.
Handles parsing, chunking, embedding, and storing documents.
"""
import os
import uuid
import asyncio
from pathlib import Path
from datetime import datetime, timezone

from backend.config import DATA_DIR, CHUNK_SIZE, CHUNK_OVERLAP, SUPPORTED_EXTENSIONS
from backend.utils.document_parsers import parse_document
from backend.utils.text_splitter import split_text
from backend.services.ollama_client import ollama_client
from backend.services.vector_store import vector_store


async def ingest_file(file_path: str) -> dict:
    """
    Ingest a single file into the vector store.

    Steps:
    1. Parse the document to extract text
    2. Split text into chunks
    3. Generate embeddings for each chunk
    4. Store chunks with metadata in ChromaDB

    Returns:
        dict with ingestion results (status, chunk_count, etc.)
    """
    path = Path(file_path)

    if not path.exists():
        return {"status": "error", "message": f"File not found: {file_path}"}

    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return {"status": "skipped", "message": f"Unsupported file type: {path.suffix}"}

    # Determine directory context
    try:
        rel_path = path.relative_to(DATA_DIR)
        parts = rel_path.parts
        source_dir = parts[0] if len(parts) > 1 else "root"
        sub_dir = str(rel_path.parent) if len(parts) > 1 else "root"
    except ValueError:
        source_dir = "external"
        sub_dir = str(path.parent)

    print(f"[Ingestion] Processing: {path.name} (dir: {source_dir})")

    # Step 1: Parse
    text = parse_document(str(file_path))
    if not text or not text.strip():
        return {"status": "skipped", "message": f"No text extracted from {path.name}"}

    # Step 2: Chunk
    chunks = split_text(text, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    if not chunks:
        return {"status": "skipped", "message": f"No chunks created from {path.name}"}

    # Step 3: Remove old chunks for this file (re-ingestion support)
    vector_store.delete_by_file(str(file_path))

    # Step 4: Generate embeddings
    try:
        embeddings = await ollama_client.embed_batch(chunks)
    except Exception as e:
        return {"status": "error", "message": f"Embedding failed: {e}"}

    # Step 5: Build metadata and store
    ids = [f"{path.stem}_{uuid.uuid4().hex[:8]}_{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "source_dir": source_dir,
            "sub_dir": sub_dir,
            "file_name": path.name,
            "file_path": str(file_path),
            "file_type": path.suffix.lower(),
            "chunk_index": i,
            "total_chunks": len(chunks),
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }
        for i in range(len(chunks))
    ]

    vector_store.add_documents(
        ids=ids,
        texts=chunks,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    print(f"[Ingestion] ✓ {path.name}: {len(chunks)} chunks indexed")
    return {
        "status": "success",
        "file": path.name,
        "source_dir": source_dir,
        "chunks": len(chunks),
    }


async def ingest_directory(dir_path: str) -> list[dict]:
    """Ingest all supported files in a directory (recursively)."""
    path = Path(dir_path)
    if not path.exists() or not path.is_dir():
        return [{"status": "error", "message": f"Directory not found: {dir_path}"}]

    results = []
    for root, _, files in os.walk(str(path)):
        for file_name in sorted(files):
            file_path = os.path.join(root, file_name)
            ext = Path(file_name).suffix.lower()
            if ext in SUPPORTED_EXTENSIONS:
                result = await ingest_file(file_path)
                results.append(result)

    return results


async def ingest_all() -> list[dict]:
    """Ingest all documents in the entire data directory."""
    return await ingest_directory(str(DATA_DIR))
