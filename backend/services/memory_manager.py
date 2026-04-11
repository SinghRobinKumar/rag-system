"""
Hybrid memory manager for conversation context.
Implements sliding window + rolling summary to keep context within token limits.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from backend.config import SLIDING_WINDOW_TURNS, SUMMARIZE_AFTER_TURNS


class ConversationSession:
    """Represents a single chat session with memory management."""

    def __init__(self, session_id: Optional[str] = None, title: str = "New Chat"):
        self.session_id = session_id or uuid.uuid4().hex
        self.title = title
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.messages: list[dict] = []  # Full history
        self.rolling_summary: str = ""  # Compressed older turns
        self.summary_up_to: int = 0  # Index up to which we've summarized

    def add_message(self, role: str, content: str):
        """Add a message to the conversation."""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def get_context_messages(self) -> list[dict]:
        """
        Build the optimized context for the LLM.

        Returns a list of messages containing:
        1. Rolling summary of older turns (if any)
        2. Last N raw turns (sliding window)
        """
        context = []

        # Add rolling summary if we have one
        if self.rolling_summary:
            context.append({
                "role": "system",
                "content": f"Summary of earlier conversation:\n{self.rolling_summary}",
            })

        # Add recent messages (sliding window)
        window_size = SLIDING_WINDOW_TURNS * 2  # Each turn = user + assistant
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
        # Messages between summary_up_to and the start of current window
        end_idx = max(0, len(self.messages) - window_size)
        if end_idx <= self.summary_up_to:
            return []
        return self.messages[self.summary_up_to:end_idx]

    def update_summary(self, new_summary: str, summarized_up_to: int):
        """Update the rolling summary."""
        self.rolling_summary = new_summary
        self.summary_up_to = summarized_up_to

    def to_dict(self) -> dict:
        """Serialize session for API responses."""
        return {
            "session_id": self.session_id,
            "title": self.title,
            "created_at": self.created_at,
            "message_count": len(self.messages),
            "has_summary": bool(self.rolling_summary),
        }


class MemoryManager:
    """Manages multiple conversation sessions with hybrid memory."""

    def __init__(self):
        self.sessions: dict[str, ConversationSession] = {}

    def create_session(self, title: str = "New Chat") -> ConversationSession:
        """Create a new conversation session."""
        session = ConversationSession(title=title)
        self.sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get a session by ID."""
        return self.sessions.get(session_id)

    def get_or_create_session(self, session_id: Optional[str] = None) -> ConversationSession:
        """Get existing session or create a new one."""
        if session_id and session_id in self.sessions:
            return self.sessions[session_id]
        return self.create_session()

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False

    def list_sessions(self) -> list[dict]:
        """List all sessions."""
        return [
            session.to_dict()
            for session in sorted(
                self.sessions.values(),
                key=lambda s: s.created_at,
                reverse=True,
            )
        ]

    async def summarize_if_needed(self, session: ConversationSession):
        """
        Check if session needs summarization and perform it.
        Uses the LLM to compress older messages into a summary.
        """
        if not session.needs_summarization():
            return

        from backend.services.ollama_client import ollama_client

        messages_to_summarize = session.get_messages_to_summarize()
        if not messages_to_summarize:
            return

        # Build the conversation text to summarize
        conv_text = ""
        for msg in messages_to_summarize:
            role = "User" if msg["role"] == "user" else "Assistant"
            conv_text += f"{role}: {msg['content']}\n\n"

        # Include existing summary for continuity
        existing = f"Previous summary:\n{session.rolling_summary}\n\n" if session.rolling_summary else ""

        summarize_prompt = [
            {
                "role": "system",
                "content": (
                    "You are a conversation summarizer. Create a concise but comprehensive summary "
                    "of the conversation below. Preserve key facts, decisions, questions asked, "
                    "and important details. Keep it under 300 words."
                ),
            },
            {
                "role": "user",
                "content": f"{existing}New conversation to incorporate:\n\n{conv_text}",
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
