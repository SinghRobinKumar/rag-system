"""
Chat API router.
Handles chat messages, streaming responses, and session management.
"""
import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from backend.services.ollama_client import ollama_client
from backend.services.vector_store import vector_store
from backend.services.query_router import route_query, clean_query
from backend.services.memory_manager import memory_manager
from backend.config import TOP_K_RESULTS

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class SessionCreate(BaseModel):
    title: Optional[str] = "New Chat"


# ─── System Prompt ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a helpful document assistant. You answer questions based on the documents that have been indexed in the system.

Rules:
- Answer questions using ONLY the provided context from retrieved documents.
- The context below contains the ACTUAL content extracted from the user's documents. USE IT.
- If the context contains tables, data, numbers, names, or lists — include them in your answer.
- When asked to show data in a table, format it as a markdown table using the data from the context.
- Always mention which file(s) your answer is based on.
- Be thorough — include ALL relevant data from the context, do not summarize unless asked to.
- Format your responses with markdown for readability.
- If asked about something not in the context, clearly state that you don't have that information.
- NEVER say 'the document doesn't contain this information' if the data IS present in the context below."""


@router.post("")
async def chat(request: ChatRequest):
    """
    Main chat endpoint with RAG pipeline.
    Returns a streaming response (Server-Sent Events).
    """
    user_message = request.message
    session = memory_manager.get_or_create_session(request.session_id)

    # If this is the first message, set the title
    if len(session.messages) == 0:
        session.title = user_message[:50] + ("..." if len(user_message) > 50 else "")

    # Step 1: Route the query to determine target directories
    route_result = await route_query(user_message)

    # Step 2: Determine if this is an aggregate query (needs ALL docs, not just top-K)
    is_aggregate = _is_aggregate_query(user_message)

    # Step 3: Retrieve context
    clean_q = clean_query(user_message)
    retrieved_context = ""
    sources = []

    try:
        if is_aggregate and route_result.get("target_dirs"):
            # AGGREGATE MODE: Fetch ALL chunks from the target directory, grouped by file
            target_dir = route_result["target_dirs"][0]
            all_files = vector_store.get_all_by_directory(target_dir)

            if all_files:
                retrieved_context = f"[Aggregate data from ALL files in '{target_dir}' directory]\n"
                for fname, chunks in all_files.items():
                    full_text = "\n".join(c["text"] for c in chunks)
                    retrieved_context += f"\n{'='*40}\n[File: {target_dir}/{fname}]\n{full_text}\n"
                    sources.append({
                        "file": fname,
                        "directory": target_dir,
                        "sub_dir": chunks[0]["metadata"].get("sub_dir", "") if chunks else "",
                    })
                print(f"[Chat] Aggregate retrieval: {len(all_files)} files from '{target_dir}'")
            else:
                retrieved_context = f"[No documents found in '{target_dir}' directory.]"
        else:
            # STANDARD MODE: Semantic search with top-K
            query_embedding = await ollama_client.embed(clean_q)

            search_results = vector_store.query(
                query_embedding=query_embedding,
                top_k=TOP_K_RESULTS,
                where=route_result.get("filter"),
            )

            # Build context from results
            if search_results["documents"] and search_results["documents"][0]:
                for i, (doc, meta) in enumerate(
                    zip(search_results["documents"][0], search_results["metadatas"][0])
                ):
                    source_info = f"{meta.get('source_dir', '?')}/{meta.get('file_name', '?')}"
                    retrieved_context += f"\n---\n[Source: {source_info}]\n{doc}\n"
                    sources.append({
                        "file": meta.get("file_name", "unknown"),
                        "directory": meta.get("source_dir", "unknown"),
                        "sub_dir": meta.get("sub_dir", ""),
                    })
    except Exception as e:
        print(f"[Chat] Retrieval error: {e}")
        retrieved_context = "[No documents could be retrieved. The vector database may be empty.]"

    # Step 3: Build the LLM prompt with memory context
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add conversation memory
    context_messages = session.get_context_messages()
    messages.extend(context_messages)

    # Add retrieved context + user question
    if retrieved_context:
        augmented_message = (
            f"Retrieved document context:\n{retrieved_context}\n\n"
            f"User question: {user_message}"
        )
    else:
        augmented_message = user_message

    messages.append({"role": "user", "content": augmented_message})

    # Step 4: Store the user message in memory
    session.add_message("user", user_message)

    # Step 5: Stream the response
    async def generate():
        full_response = ""
        try:
            # Send metadata first
            metadata = {
                "type": "metadata",
                "session_id": session.session_id,
                "route": {
                    "strategy": route_result.get("strategy", "unknown"),
                    "target_dirs": route_result.get("target_dirs", []),
                    "reason": route_result.get("reason", ""),
                },
                "sources": sources,
            }
            yield f"data: {json.dumps(metadata)}\n\n"

            # Stream LLM response
            async for chunk in ollama_client.chat_stream(messages):
                full_response += chunk
                yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

            # Store assistant response in memory
            session.add_message("assistant", full_response)

            # Check if we need to summarize
            await memory_manager.summarize_if_needed(session)

            # Send done signal
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions")
async def list_sessions():
    """List all chat sessions."""
    return {"sessions": memory_manager.list_sessions()}


@router.post("/sessions/new")
async def create_session(request: SessionCreate):
    """Create a new chat session."""
    session = memory_manager.create_session(title=request.title)
    return {"session": session.to_dict()}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a chat session."""
    success = memory_manager.delete_session(session_id)
    return {"success": success}


# ─── Aggregate Query Detection ───────────────────────────────────────────────

import re

# Patterns that indicate the user wants data from ALL files, not just the most relevant
AGGREGATE_PATTERNS = [
    r"\ball\b.*\b(po|purchase\s*order|invoice|document|file|contract|report)s?\b",
    r"\b(po|purchase\s*order|invoice|document|file|contract|report)s?\b.*\ball\b",
    r"\b(summary|summari[sz]e|overview|breakdown|consolidat|combin|total|compare|comparison)\b.*\b(po|purchase\s*order|invoice|document|file|contract|report)s?\b",
    r"\b(every|each)\b.*\b(po|purchase\s*order|invoice|document|file|contract|report)\b",
    r"\b(list|show|give|get)\b.*\ball\b",
    r"\bhow\s+many\b.*\b(po|purchase\s*order|invoice|document|file|contract|report)s?\b",
    r"\btotal\b.*\b(value|amount|cost|price|order)\b",
    r"\bacross\s+all\b",
    r"\bfrom\s+(all|every)\b",
]


def _is_aggregate_query(message: str) -> bool:
    """
    Detect if a query needs data from ALL documents (aggregate mode)
    vs. a specific question that can be answered with top-K retrieval.
    """
    msg_lower = message.lower().strip()
    for pattern in AGGREGATE_PATTERNS:
        if re.search(pattern, msg_lower):
            return True
    return False

