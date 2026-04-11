"""
Document management API router.
Handles file uploads, directory management, and ingestion.
"""
import os
import shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional

from backend.config import DATA_DIR, SUPPORTED_EXTENSIONS
from backend.services.ingestion import ingest_file, ingest_directory, ingest_all
from backend.services.vector_store import vector_store

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload")
async def upload_files(
    files: list[UploadFile] = File(...),
    directory: str = Form(...),
):
    """
    Upload one or more files to a target directory.
    Creates the directory if it doesn't exist.
    """
    # Sanitize directory path (prevent path traversal)
    safe_dir = directory.strip().strip("/\\").replace("..", "")
    target_dir = DATA_DIR / safe_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for file in files:
        ext = Path(file.filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            results.append({
                "file": file.filename,
                "status": "skipped",
                "message": f"Unsupported file type: {ext}",
            })
            continue

        # Save file
        file_path = target_dir / file.filename
        try:
            content = await file.read()
            with open(file_path, "wb") as f:
                f.write(content)

            # Ingest immediately
            ingest_result = await ingest_file(str(file_path))
            results.append(ingest_result)

        except Exception as e:
            results.append({
                "file": file.filename,
                "status": "error",
                "message": str(e),
            })

    return {"results": results}


@router.get("/directories")
async def list_directories():
    """
    List all directories in the data folder with their file counts.
    Returns a recursive tree structure.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tree = _build_dir_tree(DATA_DIR)
    return {"directories": tree, "base_path": str(DATA_DIR)}


def _build_dir_tree(path: Path, relative_to: Path = None) -> list[dict]:
    """Build a recursive directory tree."""
    if relative_to is None:
        relative_to = path

    result = []
    try:
        for item in sorted(path.iterdir()):
            if item.name.startswith("."):
                continue

            if item.is_dir():
                children = _build_dir_tree(item, relative_to)
                file_count = sum(
                    1 for f in item.rglob("*")
                    if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
                )
                result.append({
                    "name": item.name,
                    "path": str(item.relative_to(relative_to)),
                    "type": "directory",
                    "file_count": file_count,
                    "children": children,
                })
    except PermissionError:
        pass

    return result


@router.post("/directories")
async def create_directory(name: str = Form(...), parent: str = Form("")):
    """Create a new directory. Supports nested creation."""
    safe_name = name.strip().strip("/\\").replace("..", "")
    safe_parent = parent.strip().strip("/\\").replace("..", "")

    if not safe_name:
        raise HTTPException(status_code=400, detail="Directory name is required")

    target = DATA_DIR / safe_parent / safe_name if safe_parent else DATA_DIR / safe_name
    target.mkdir(parents=True, exist_ok=True)

    return {
        "status": "success",
        "path": str(target.relative_to(DATA_DIR)),
        "full_path": str(target),
    }


@router.delete("/directories/{dir_path:path}")
async def delete_directory(dir_path: str):
    """Delete a directory and remove its documents from the vector store."""
    safe_path = dir_path.strip().strip("/\\").replace("..", "")
    target = DATA_DIR / safe_path

    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")

    # Don't allow deleting the root data directory
    if target == DATA_DIR:
        raise HTTPException(status_code=400, detail="Cannot delete root data directory")

    # Remove from vector store
    top_level = safe_path.split("/")[0]
    vector_store.delete_by_directory(top_level)

    # Remove from filesystem
    shutil.rmtree(str(target))

    return {"status": "success", "deleted": safe_path}


@router.get("/files/{dir_path:path}")
async def list_files(dir_path: str):
    """List files in a specific directory."""
    safe_path = dir_path.strip().strip("/\\").replace("..", "")
    target = DATA_DIR / safe_path

    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")

    files = []
    for item in sorted(target.iterdir()):
        if item.is_file() and not item.name.startswith("."):
            files.append({
                "name": item.name,
                "path": str(item.relative_to(DATA_DIR)),
                "size": item.stat().st_size,
                "type": item.suffix.lower(),
                "modified": item.stat().st_mtime,
            })

    return {"files": files, "directory": safe_path}


@router.delete("/files/{file_path:path}")
async def delete_file(file_path: str):
    """Delete a file and remove its chunks from the vector store."""
    safe_path = file_path.strip().strip("/\\").replace("..", "")
    target = DATA_DIR / safe_path

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    # Remove from vector store
    vector_store.delete_by_file(str(target))

    # Remove from filesystem
    target.unlink()

    return {"status": "success", "deleted": safe_path}


@router.post("/reindex")
async def reindex_all():
    """Force re-index all documents in the data directory."""
    results = await ingest_all()
    success = sum(1 for r in results if r.get("status") == "success")
    errors = sum(1 for r in results if r.get("status") == "error")
    skipped = sum(1 for r in results if r.get("status") == "skipped")

    return {
        "status": "success",
        "total": len(results),
        "indexed": success,
        "errors": errors,
        "skipped": skipped,
        "details": results,
    }


@router.get("/stats")
async def get_stats():
    """Get document and vector store statistics."""
    vs_stats = vector_store.get_stats()

    # Count files on disk
    file_count = 0
    dir_count = 0
    if DATA_DIR.exists():
        for item in DATA_DIR.rglob("*"):
            if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS:
                file_count += 1
            elif item.is_dir():
                dir_count += 1

    return {
        "files_on_disk": file_count,
        "directories": dir_count,
        "vector_store": vs_stats,
    }
