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
from backend.services.web_search import web_search_client
from backend.config import TOP_K_RESULTS

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    mode: Optional[str] = "offline"


class SessionCreate(BaseModel):
    title: Optional[str] = "New Chat"


# ─── System Prompt ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a professional document intelligence assistant. You analyze and answer questions based on indexed documents.

RULES:
1. Answer using ONLY the provided document context below
2. Provide clear, well-structured responses with proper formatting
3. Use markdown: headers (##), bullet points, numbered lists, tables, bold text
4. Start with a direct answer, then provide supporting details
5. When showing data, use markdown tables for clarity
6. Always cite which file(s) your answer comes from
7. Include ALL relevant data from context - be thorough
8. If context lacks information, state clearly what's missing
9. You ONLY have access to local documents - no web search capability

FORMAT YOUR RESPONSE:
- Start with clear, direct answer
- Use proper markdown formatting
- Organize information logically
- Cite source files naturally in text"""


@router.post("")
async def chat(request: ChatRequest):
    """
    Main chat endpoint w/ RAG pipeline.
    Supports offline (local docs) & web (online search) modes.
    Returns streaming response (Server-Sent Events).
    """
    user_message = request.message
    mode = request.mode or "offline"
    session = memory_manager.get_or_create_session(request.session_id)

    if len(session.messages) == 0:
        session.title = user_message[:50] + ("..." if len(user_message) > 50 else "")

    # Fast path: detect greetings/chitchat
    if _is_greeting_or_chitchat(user_message):
        session.add_message("user", user_message)
        
        async def greeting_response():
            greeting_reply = _generate_greeting_response(user_message)
            session.add_message("assistant", greeting_reply)
            
            yield f"data: {json.dumps({'type': 'metadata', 'session_id': session.session_id, 'mode': mode, 'route': {'strategy': 'greeting', 'target_dirs': [], 'reason': 'Greeting detected'}, 'sources': []})}\n\n"
            yield f"data: {json.dumps({'type': 'content', 'content': greeting_reply})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        
        return StreamingResponse(
            greeting_response(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
        )

    if mode == "web":
        
        async def web_response():
            try:
                # Rewrite ambiguous follow-up queries using conversation history
                search_query = user_message
                context_messages = session.get_context_messages()
                if context_messages and len(context_messages) > 0:
                    # Use LLM to rewrite the query with conversation context
                    rewrite_messages = [
                        {"role": "system", "content": "You are a search query rewriter. Given a conversation history and a follow-up question, rewrite the follow-up into a standalone web search query that captures the full intent. Output ONLY the rewritten search query, nothing else. If the question is already clear and standalone, return it as-is."},
                    ]
                    # Add recent conversation for context (last few turns)
                    for msg in context_messages[-6:]:
                        rewrite_messages.append({"role": msg["role"], "content": msg["content"][:200]})
                    rewrite_messages.append({"role": "user", "content": f"Rewrite this follow-up as a standalone search query: {user_message}"})
                    
                    try:
                        search_query = await ollama_client.chat(rewrite_messages)
                        search_query = search_query.strip().strip('"').strip("'")
                        if not search_query or len(search_query) < 3:
                            search_query = user_message
                        print(f"[Chat] Web query rewrite: '{user_message}' -> '{search_query}'")
                    except Exception as e:
                        print(f"[Chat] Query rewrite failed, using original: {e}")
                        search_query = user_message

                search_results = await web_search_client.search(search_query, max_results=5)
                
                context = ""
                sources = []
                if search_results:
                    context = "WEB SEARCH RESULTS:\n\n"
                    for i, result in enumerate(search_results, 1):
                        context += f"Source {i}: {result['title']}\n"
                        context += f"URL: {result['url']}\n"
                        context += f"Content: {result['snippet']}\n\n"
                        sources.append({
                            "title": result['title'],
                            "url": result['url'],
                            "type": "web"
                        })
                
                system_prompt = """You are a professional web search assistant.

CRITICAL RULES:
1. Answer ONLY using the web search results provided below
2. IGNORE your training data - it may be outdated
3. Synthesize information from multiple sources into a clear, coherent answer
4. Start with a direct answer, then provide supporting details
5. Use proper formatting: paragraphs, bullet points, numbered lists
6. Cite sources naturally in text (e.g., "According to Python.org...")
7. If results conflict, mention both perspectives
8. If search results don't contain the answer, say so clearly
9. Never mention "knowledge cutoff" or training data
10. You do NOT have access to any local documents or files
11. For follow-up questions, refer to the conversation history to understand the full context of what the user is asking about

FORMAT YOUR RESPONSE:
- Start with clear, direct answer
- Use markdown formatting (headers, lists, bold)
- Group related information
- End with source links if relevant"""

                # Build messages with conversation history for context
                messages = [{"role": "system", "content": system_prompt}]

                # Include conversation history so follow-up questions work
                context_messages = session.get_context_messages()
                messages.extend(context_messages)

                # Add current user question with web search results
                if context:
                    augmented_message = f"{context}\n\nUser question: {user_message}\n\nProvide a clear, well-formatted answer using the search results above."
                else:
                    augmented_message = f"No search results found for: {user_message}\n\nPolitely inform the user that no results were found and suggest rephrasing the question."
                messages.append({"role": "user", "content": augmented_message})

                # Store user message in memory (after building context to avoid duplicate)
                session.add_message("user", user_message)
                
                yield f"data: {json.dumps({'type': 'metadata', 'session_id': session.session_id, 'mode': 'web', 'route': {'strategy': 'web_search', 'target_dirs': [], 'reason': 'Web search mode - no local file access'}, 'sources': sources})}\n\n"
                
                full_response = ""
                async for chunk in ollama_client.chat_stream(messages):
                    full_response += chunk
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"
                
                session.add_message("assistant", full_response)
                
                # Summarize older turns if conversation is getting long
                await memory_manager.summarize_if_needed(session)
                
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        
        return StreamingResponse(
            web_response(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
        )

    # OFFLINE MODE: Local RAG
    route_result = await route_query(user_message)

    is_aggregate = _is_aggregate_query(user_message)
    clean_q = clean_query(user_message)
    retrieved_context = ""
    sources = []

    try:
        if is_aggregate and route_result.get("target_dirs"):
            target_dirs = route_result["target_dirs"][:3]
            
            for target_dir in target_dirs:
                all_files = vector_store.get_all_by_directory(target_dir)
                
                if all_files:
                    retrieved_context += f"\n[Data from '{target_dir}' directory]\n"
                    for fname, chunks in list(all_files.items())[:20]:
                        full_text = "\n".join(c["text"] for c in chunks[:5])
                        retrieved_context += f"\n{'='*40}\n[File: {target_dir}/{fname}]\n{full_text}\n"
                        sources.append({
                            "file": fname,
                            "directory": target_dir,
                            "sub_dir": chunks[0]["metadata"].get("sub_dir", "") if chunks else "",
                        })
                    print(f"[Chat] Aggregate: {len(all_files)} files from '{target_dir}' (limited to 20)")
        else:
            query_embedding = await ollama_client.embed(clean_q)
            
            search_results = vector_store.query(
                query_embedding=query_embedding,
                top_k=TOP_K_RESULTS,
                where=route_result.get("filter"),
            )

            if search_results["documents"] and search_results["documents"][0]:
                for doc, meta in zip(search_results["documents"][0], search_results["metadatas"][0]):
                    source_info = f"{meta.get('source_dir', '?')}/{meta.get('file_name', '?')}"
                    retrieved_context += f"\n---\n[Source: {source_info}]\n{doc}\n"
                    sources.append({
                        "file": meta.get("file_name", "unknown"),
                        "directory": meta.get("source_dir", "unknown"),
                        "sub_dir": meta.get("sub_dir", ""),
                    })
    except Exception as e:
        print(f"[Chat] Retrieval error: {e}")
        retrieved_context = "[No documents could be retrieved. Vector database may be empty.]"

    # Build LLM prompt w/ memory context
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add conversation memory (OFFLINE MODE ONLY)
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

    # Store user message in memory
    session.add_message("user", user_message)

    # Stream response
    async def generate():
        full_response = ""
        try:
            metadata = {
                "type": "metadata",
                "session_id": session.session_id,
                "mode": "offline",
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


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get the full history and details of a specific chat session."""
    session = memory_manager.get_session(session_id)
    if not session:
        return {"error": "Session not found", "messages": []}
    
    return {
        "session_id": session.session_id,
        "title": session.title,
        "messages": session.messages
    }


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
    Detect if query needs data from ALL documents (aggregate mode)
    vs. specific question answerable w/ top-K retrieval.
    """
    msg_lower = message.lower().strip()
    for pattern in AGGREGATE_PATTERNS:
        if re.search(pattern, msg_lower):
            return True
    return False


GREETING_PATTERNS = [
    r"^(hi|hello|hey|greetings|good\s+(morning|afternoon|evening)|howdy|sup|yo)[\s!.?]*$",
    r"^(how\s+are\s+you|what'?s\s+up|how'?s\s+it\s+going)[\s!.?]*$",
    r"^(thanks?|thank\s+you|thx|ty)[\s!.?]*$",
    r"^(bye|goodbye|see\s+ya|later|cya)[\s!.?]*$",
]

def _is_greeting_or_chitchat(message: str) -> bool:
    """Detect simple greetings that don't need RAG."""
    msg = message.strip().lower()
    if len(msg) > 50:
        return False
    for pattern in GREETING_PATTERNS:
        if re.match(pattern, msg):
            return True
    return False

def _generate_greeting_response(message: str) -> str:
    """Generate quick response for greetings."""
    msg = message.strip().lower()
    if any(x in msg for x in ["hi", "hello", "hey", "howdy"]):
        return "Hello! I'm your document assistant. I can help you search through your uploaded documents and answer questions about them. What would you like to know?"
    if "how are you" in msg or "what's up" in msg or "how's it going" in msg:
        return "I'm doing great, thanks for asking! I'm ready to help you with your documents. What can I assist you with?"
    if "thank" in msg:
        return "You're welcome! Let me know if you need anything else."
    if any(x in msg for x in ["bye", "goodbye", "later"]):
        return "Goodbye! Feel free to come back anytime you need help with your documents."
    return "Hello! How can I help you with your documents today?"

