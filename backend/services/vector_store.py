"""
ChromaDB vector store operations.
Manages the persistent document collection with metadata filtering.
"""
import chromadb
from chromadb.config import Settings
from typing import Optional
from pathlib import Path

from backend.config import CHROMA_DIR, CHROMA_COLLECTION_NAME, TOP_K_RESULTS


class VectorStore:
    """Manages ChromaDB collection for RAG document storage and retrieval."""

    def __init__(self):
        self._client = None
        self._collection = None

    def initialize(self):
        """Initialize ChromaDB client and collection."""
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
        )

        self._collection = self._client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        print(f"[VectorStore] Initialized. Collection '{CHROMA_COLLECTION_NAME}' has {self._collection.count()} documents.")

    @property
    def collection(self):
        if self._collection is None:
            self.initialize()
        return self._collection

    def add_documents(
        self,
        ids: list[str],
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
    ):
        """Add document chunks with embeddings and metadata to the collection."""
        self.collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def query(
        self,
        query_embedding: list[float],
        top_k: int = TOP_K_RESULTS,
        where: Optional[dict] = None,
        where_document: Optional[dict] = None,
    ) -> dict:
        """
        Query the collection with a vector and optional metadata filters.

        Args:
            query_embedding: The query vector
            top_k: Number of results to return
            where: Metadata filter (e.g., {"source_dir": "clients"})
            where_document: Document content filter

        Returns:
            dict with 'ids', 'documents', 'metadatas', 'distances'
        """
        kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": min(top_k, self.collection.count()) if self.collection.count() > 0 else top_k,
        }
        if where:
            kwargs["where"] = where
        if where_document:
            kwargs["where_document"] = where_document

        if self.collection.count() == 0:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

        results = self.collection.query(**kwargs)
        return results

    def delete_by_file(self, file_path: str):
        """Remove all chunks associated with a specific file."""
        try:
            # Get all IDs matching this file path
            results = self.collection.get(
                where={"file_path": file_path},
            )
            if results["ids"]:
                self.collection.delete(ids=results["ids"])
                print(f"[VectorStore] Deleted {len(results['ids'])} chunks for {file_path}")
        except Exception as e:
            print(f"[VectorStore] Error deleting chunks for {file_path}: {e}")

    def delete_by_directory(self, dir_path: str):
        """Remove all chunks associated with files in a directory."""
        try:
            results = self.collection.get(
                where={"source_dir": dir_path},
            )
            if results["ids"]:
                self.collection.delete(ids=results["ids"])
                print(f"[VectorStore] Deleted {len(results['ids'])} chunks for directory {dir_path}")
        except Exception as e:
            print(f"[VectorStore] Error deleting chunks for directory {dir_path}: {e}")

    def get_stats(self) -> dict:
        """Get collection statistics."""
        total = self.collection.count()

        # Get unique directories
        dir_counts = {}
        if total > 0:
            try:
                all_data = self.collection.get(include=["metadatas"])
                for meta in all_data["metadatas"]:
                    d = meta.get("source_dir", "unknown")
                    dir_counts[d] = dir_counts.get(d, 0) + 1
            except Exception:
                pass

        return {
            "total_chunks": total,
            "directory_counts": dir_counts,
        }

    def get_all_directories(self) -> list[str]:
        """Get list of all unique source directories in the collection."""
        if self.collection.count() == 0:
            return []

        try:
            all_data = self.collection.get(include=["metadatas"])
            dirs = set()
            for meta in all_data["metadatas"]:
                d = meta.get("source_dir")
                if d:
                    dirs.add(d)
            return sorted(list(dirs))
        except Exception:
            return []

    def get_all_by_directory(self, source_dir: str) -> dict[str, list[dict]]:
        """
        Get ALL chunks from a specific directory, grouped by filename.
        Used for aggregate queries that need data from every file.

        Returns:
            dict mapping filename -> list of {text, metadata} dicts, sorted by chunk_index
        """
        if self.collection.count() == 0:
            return {}

        try:
            results = self.collection.get(
                where={"source_dir": source_dir},
                include=["documents", "metadatas"],
            )

            # Group by filename
            by_file: dict[str, list[dict]] = {}
            for doc, meta in zip(results["documents"], results["metadatas"]):
                fname = meta.get("file_name", "unknown")
                if fname not in by_file:
                    by_file[fname] = []
                by_file[fname].append({
                    "text": doc,
                    "metadata": meta,
                })

            # Sort chunks within each file by chunk_index
            for fname in by_file:
                by_file[fname].sort(key=lambda x: x["metadata"].get("chunk_index", 0))

            return by_file
        except Exception as e:
            print(f"[VectorStore] Error getting all by directory: {e}")
            return {}

    def get_file_list(self, source_dir: str) -> list[str]:
        """Get list of all unique filenames in a directory."""
        if self.collection.count() == 0:
            return []

        try:
            results = self.collection.get(
                where={"source_dir": source_dir},
                include=["metadatas"],
            )
            files = set()
            for meta in results["metadatas"]:
                f = meta.get("file_name")
                if f:
                    files.add(f)
            return sorted(list(files))
        except Exception:
            return []


# Global singleton
vector_store = VectorStore()
