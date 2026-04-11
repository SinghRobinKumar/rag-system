"""
Intelligent query router.
Determines which directory/directories to search based on the user's question.
"""
from backend.services.ollama_client import ollama_client
from backend.services.vector_store import vector_store
from backend.config import DATA_DIR

import os
import re


async def route_query(query: str) -> dict:
    """
    Analyze a user query and determine the target directory for search.

    Three routing strategies:
    1. Explicit: User uses @directory syntax (e.g., "@clients list all")
    2. LLM-based: Ask the LLM to classify the query
    3. Fallback: Search all directories

    Returns:
        dict with 'target_dirs' (list), 'filter' (ChromaDB where clause), 'strategy' (str)
    """
    # Get available directories from filesystem
    available_dirs = _get_filesystem_dirs()

    if not available_dirs:
        return {
            "target_dirs": [],
            "filter": None,
            "strategy": "none",
            "reason": "No directories found in data folder",
        }

    # Strategy 1: Check for explicit @directory mention
    explicit_dir = _check_explicit_mention(query, available_dirs)
    if explicit_dir:
        return {
            "target_dirs": [explicit_dir],
            "filter": {"source_dir": explicit_dir},
            "strategy": "explicit",
            "reason": f"User explicitly mentioned @{explicit_dir}",
        }

    # Strategy 2: LLM-based routing
    try:
        llm_dirs = await _llm_route(query, available_dirs)
        if llm_dirs:
            if len(llm_dirs) == 1:
                return {
                    "target_dirs": llm_dirs,
                    "filter": {"source_dir": llm_dirs[0]},
                    "strategy": "llm",
                    "reason": f"LLM determined query relates to: {', '.join(llm_dirs)}",
                }
            else:
                return {
                    "target_dirs": llm_dirs,
                    "filter": {"$or": [{"source_dir": d} for d in llm_dirs]},
                    "strategy": "llm",
                    "reason": f"LLM determined query relates to: {', '.join(llm_dirs)}",
                }
    except Exception as e:
        print(f"[Router] LLM routing failed: {e}")

    # Strategy 3: Fall back to searching everything
    return {
        "target_dirs": available_dirs,
        "filter": None,
        "strategy": "fallback",
        "reason": "Could not determine specific directory, searching all",
    }


def _get_filesystem_dirs() -> list[str]:
    """Get all top-level directories in the data folder."""
    dirs = []
    if DATA_DIR.exists():
        for item in sorted(DATA_DIR.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                dirs.append(item.name)
    return dirs


def _check_explicit_mention(query: str, available_dirs: list[str]) -> str | None:
    """Check if user explicitly mentioned a directory with @ syntax."""
    # Match @directory_name pattern
    matches = re.findall(r"@(\w+)", query.lower())
    for match in matches:
        if match in available_dirs:
            return match
        # Fuzzy match: check if any directory contains the match
        for d in available_dirs:
            if match in d or d in match:
                return d
    return None


async def _llm_route(query: str, available_dirs: list[str]) -> list[str]:
    """Use LLM to determine which directory the query is about."""
    dir_list = ", ".join(available_dirs)

    routing_prompt = [
        {
            "role": "system",
            "content": (
                "You are a query router. Given a user question and a list of document directories, "
                "determine which directory or directories are most relevant to the question. "
                "Reply with ONLY the directory name(s), comma-separated. "
                "If the question could apply to ALL directories or you're not sure, reply with 'ALL'. "
                "Do not explain, just output the directory name(s)."
            ),
        },
        {
            "role": "user",
            "content": f"Directories: [{dir_list}]\n\nQuestion: {query}",
        },
    ]

    response = await ollama_client.chat(routing_prompt)
    response = response.strip().lower()

    if response == "all" or not response:
        return []

    # Parse the response to extract valid directory names
    result = []
    for part in response.split(","):
        part = part.strip().strip("'\"")
        if part in available_dirs:
            result.append(part)

    return result


def clean_query(query: str) -> str:
    """Remove @directory mentions from the query for cleaner search."""
    return re.sub(r"@\w+\s*", "", query).strip()
