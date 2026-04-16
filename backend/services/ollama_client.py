"""
Async wrapper around the Ollama REST API.
Handles chat completions (streaming), embeddings, and model management.
"""
import httpx
import json
import asyncio
from typing import AsyncGenerator, Optional
from backend.config import OLLAMA_BASE_URL, DEFAULT_CHAT_MODEL, DEFAULT_EMBED_MODEL


class OllamaClient:
    """Singleton-style client for interacting with the Ollama API."""

    def __init__(self):
        self.base_url = OLLAMA_BASE_URL
        self.chat_model = DEFAULT_CHAT_MODEL
        self.embed_model = DEFAULT_EMBED_MODEL
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)

    async def close(self):
        await self._client.aclose()

    # ─── Chat (Streaming) ────────────────────────────────────────────────

    async def chat_stream(
        self,
        messages: list[dict],
        model: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream a chat completion from Ollama.
        Yields text chunks as they arrive.
        """
        payload = {
            "model": model or self.chat_model,
            "messages": messages,
            "stream": True,
        }
        async with self._client.stream(
            "POST", "/api/chat", json=payload, timeout=300.0
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.strip():
                    try:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
                        if data.get("done", False):
                            return
                    except json.JSONDecodeError:
                        continue

    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
    ) -> str:
        """Non-streaming chat completion. Returns the full response text."""
        payload = {
            "model": model or self.chat_model,
            "messages": messages,
            "stream": False,
        }
        response = await self._client.post(
            "/api/chat", json=payload, timeout=300.0
        )
        response.raise_for_status()
        data = response.json()
        return data.get("message", {}).get("content", "")

    # ─── Embeddings ──────────────────────────────────────────────────────

    async def embed(
        self,
        text: str,
        model: Optional[str] = None,
    ) -> list[float]:
        """Generate embeddings for a single text string."""
        payload = {
            "model": model or self.embed_model,
            "input": text,
        }
        response = await self._client.post(
            "/api/embed", json=payload, timeout=120.0
        )
        response.raise_for_status()
        data = response.json()
        # Ollama returns {"embeddings": [[...]]}
        embeddings = data.get("embeddings", [[]])
        return embeddings[0] if embeddings else []

    async def embed_batch(
        self,
        texts: list[str],
        model: Optional[str] = None,
    ) -> list[list[float]]:
        """Generate embeddings for a batch of texts in parallel."""
        tasks = [self.embed(text, model) for text in texts]
        return await asyncio.gather(*tasks)

    # ─── Model Management ────────────────────────────────────────────────

    async def list_models(self) -> list[dict]:
        """List all locally available Ollama models."""
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
            data = response.json()
            return data.get("models", [])
        except Exception:
            return []

    async def is_available(self) -> bool:
        """Check if Ollama server is reachable."""
        try:
            response = await self._client.get("/api/tags")
            return response.status_code == 200
        except Exception:
            return False

    def set_chat_model(self, model_name: str):
        """Switch the active chat model."""
        self.chat_model = model_name

    def set_embed_model(self, model_name: str):
        """Switch the active embedding model."""
        self.embed_model = model_name

    def get_current_models(self) -> dict:
        """Return current model configuration."""
        return {
            "chat_model": self.chat_model,
            "embed_model": self.embed_model,
        }


# Global singleton instance
ollama_client = OllamaClient()
