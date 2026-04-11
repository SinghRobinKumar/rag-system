"""
Hybrid memory manager for conversation context.
Implements sliding window + rolling summary to keep context within token limits.
Now uses JSON-based persistent disk storage to save RAM.
"""
import json
import uuid
import os
from datetime import datetime, timezone
from typing import Optional

from backend.config import SLIDING_WINDOW_TURNS, SUMMARIZE_AFTER_TURNS, SESSIONS_DIR


class ConversationSession:
    """Represents a single chat session with memory management and disk persistence."""

    def __init__(self, session_id: Optional[str] = None, title: str = "New Chat"):
        self.session_id = session_id or uuid.uuid4().hex
        self.title = title
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.messages: list[dict] = []  # Full history
        self.rolling_summary: str = ""  # Compressed older turns
        self.summary_up_to: int = 0  # Index up to which we've summarized

    def add_message(self, role: str, content: str):
        """Add a message to the conversation and write directly to disk."""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.save_to_disk()

    def get_context_messages(self) -> list[dict]:
        """Build the optimized context for the LLM."""
        context = []
        if self.rolling_summary:
            context.append({
                "role": "system",
                "content": f"Summary of earlier conversation:\n{self.rolling_summary}",
            })

        window_size = SLIDING_WINDOW_TURNS * 2
        recent = self.messages[-window_size:] if len(self.messages) > window_size else self.messages

        for msg in recent:
            context.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        return context

    def needs_summarization(self) -> bool:
        """Check if we should summarize older messages."""
        unsummarized_count = len(self.messages) - self.summary_up_to
        return unsummarized_count > SUMMARIZE_AFTER_TURNS * 2

    def get_messages_to_summarize(self) -> list[dict]:
        """Get the messages that need to be summarized."""
        window_size = SLIDING_WINDOW_TURNS * 2
        end_idx = max(0, len(self.messages) - window_size)
        if end_idx <= self.summary_up_to:
            return []
        return self.messages[self.summary_up_to:end_idx]

    def update_summary(self, new_summary: str, summarized_up_to: int):
        """Update the rolling summary and save to disk."""
        self.rolling_summary = new_summary
        self.summary_up_to = summarized_up_to
        self.save_to_disk()

    def to_dict(self) -> dict:
        """Serialize session metadata for API responses (not the full history)."""
        return {
            "session_id": self.session_id,
            "title": self.title,
            "created_at": self.created_at,
            "message_count": len(self.messages),
            "has_summary": bool(self.rolling_summary),
        }

    def save_to_disk(self):
        """Serialize complete state and save to SESSIONS_DIR."""
        file_path = SESSIONS_DIR / f"{self.session_id}.json"
        data = {
            "session_id": self.session_id,
            "title": self.title,
            "created_at": self.created_at,
            "messages": self.messages,
            "rolling_summary": self.rolling_summary,
            "summary_up_to": self.summary_up_to,
        }
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Memory] Warning: Could not save session to disk: {e}")

    @classmethod
    def load_from_disk(cls, session_id: str) -> Optional['ConversationSession']:
        """Load complete state from disk into a fresh instance."""
        file_path = SESSIONS_DIR / f"{session_id}.json"
        if not file_path.exists():
            return None
            
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            session = cls(session_id=data["session_id"], title=data.get("title", "Old Chat"))
            session.created_at = data.get("created_at", session.created_at)
            session.messages = data.get("messages", [])
            session.rolling_summary = data.get("rolling_summary", "")
            session.summary_up_to = data.get("summary_up_to", 0)
            return session
        except Exception as e:
            print(f"[Memory] Failed to load session {session_id}: {e}")
            return None


class MemoryManager:
    """Manages chat context ensuring only 1 active session exists in RAM."""

    def __init__(self):
        self.active_session: Optional[ConversationSession] = None

    def _ensure_active(self, session: ConversationSession):
        """Keep memory footprint minimal: unload old session before loading new one."""
        if self.active_session and self.active_session.session_id != session.session_id:
            # We don't really 'save' here because we auto-save on every add_message,
            # but unloading it explicitly removes it from memory.
            del self.active_session 
            
        self.active_session = session

    def create_session(self, title: str = "New Chat") -> ConversationSession:
        """Create a new disk-backed session."""
        session = ConversationSession(title=title)
        session.save_to_disk()
        self._ensure_active(session)
        return session

    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Fetch session from memory if active, or disk if not."""
        if self.active_session and self.active_session.session_id == session_id:
            return self.active_session
            
        session = ConversationSession.load_from_disk(session_id)
        if session:
            self._ensure_active(session)
        return session

    def get_or_create_session(self, session_id: Optional[str] = None) -> ConversationSession:
        """Get existing session or create a new one."""
        if session_id:
            session = self.get_session(session_id)
            if session:
                return session
        return self.create_session()

    def delete_session(self, session_id: str) -> bool:
        """Delete from RAM (if active) and completely remove from disk."""
        if self.active_session and self.active_session.session_id == session_id:
            self.active_session = None
            
        file_path = SESSIONS_DIR / f"{session_id}.json"
        if file_path.exists():
            try:
                os.remove(file_path)
                return True
            except Exception as e:
                print(f"[Memory] Failed to delete session file: {e}")
                return False
        return False

    def list_sessions(self) -> list[dict]:
        """Quickly list standard metadata for the UI by parsing JSON files."""
        sessions_meta = []
        for file_path in SESSIONS_DIR.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    sessions_meta.append({
                        "session_id": data.get("session_id"),
                        "title": data.get("title", "Old Chat"),
                        "created_at": data.get("created_at", ""),
                        "message_count": len(data.get("messages", [])),
                        "has_summary": bool(data.get("rolling_summary", "")),
                    })
            except Exception:
                continue
                
        return sorted(sessions_meta, key=lambda x: x["created_at"], reverse=True)

    async def summarize_if_needed(self, session: ConversationSession):
        """Check if session needs summarization and perform it."""
        if not session.needs_summarization():
            return

        from backend.services.ollama_client import ollama_client

        messages_to_summarize = session.get_messages_to_summarize()
        if not messages_to_summarize:
            return

        conv_text = ""
        for msg in messages_to_summarize:
            role = "User" if msg["role"] == "user" else "Assistant"
            conv_text += f"{role}: {msg['content']}\\n\\n"

        existing = f"Previous summary:\\n{session.rolling_summary}\\n\\n" if session.rolling_summary else ""

        summarize_prompt = [
            {
                "role": "system",
                "content": (
                    "You are a conversation summarizer. Create a concise but comprehensive summary "
                    "of the conversation below. Keep it under 300 words."
                ),
            },
            {
                "role": "user",
                "content": f"{existing}New conversation to incorporate:\\n\\n{conv_text}",
            },
        ]

        try:
            summary = await ollama_client.chat(summarize_prompt)
            window_size = SLIDING_WINDOW_TURNS * 2
            summarized_up_to = max(0, len(session.messages) - window_size)
            session.update_summary(summary, summarized_up_to)
            print(f"[Memory] Session {session.session_id[:8]}: Summarized {len(messages_to_summarize)} messages")
        except Exception as e:
            print(f"[Memory] Summarization failed: {e}")


# Global singleton
memory_manager = MemoryManager()
