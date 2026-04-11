"""
File system watcher using Watchdog.
Monitors the data directory for file changes and auto-ingests new/modified documents.
"""
import asyncio
import threading
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from backend.config import DATA_DIR, SUPPORTED_EXTENSIONS, WATCH_DEBOUNCE_SECONDS


class _IngestionHandler(FileSystemEventHandler):
    """Handles file system events and queues files for ingestion."""

    def __init__(self):
        super().__init__()
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()
        self._loop = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def _is_supported(self, path: str) -> bool:
        return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS

    def on_created(self, event: FileSystemEvent):
        if not event.is_directory and self._is_supported(event.src_path):
            self._schedule_ingestion(event.src_path)

    def on_modified(self, event: FileSystemEvent):
        if not event.is_directory and self._is_supported(event.src_path):
            self._schedule_ingestion(event.src_path)

    def on_deleted(self, event: FileSystemEvent):
        if not event.is_directory:
            self._schedule_deletion(event.src_path)

    def _schedule_ingestion(self, file_path: str):
        """Debounced ingestion: wait for file writes to complete."""
        with self._lock:
            self._pending[file_path] = time.time()

        # Schedule a delayed check in a background thread
        thread = threading.Thread(
            target=self._delayed_ingest, args=(file_path,), daemon=True
        )
        thread.start()

    def _delayed_ingest(self, file_path: str):
        """Wait for debounce period, then trigger ingestion."""
        time.sleep(WATCH_DEBOUNCE_SECONDS)

        with self._lock:
            scheduled_time = self._pending.get(file_path)
            if scheduled_time is None:
                return
            # Check if a newer event was scheduled
            if time.time() - scheduled_time < WATCH_DEBOUNCE_SECONDS:
                return
            del self._pending[file_path]

        # Run async ingestion in the event loop
        if self._loop and Path(file_path).exists():
            print(f"[Watcher] Auto-ingesting: {Path(file_path).name}")
            from backend.services.ingestion import ingest_file
            asyncio.run_coroutine_threadsafe(ingest_file(file_path), self._loop)

    def _schedule_deletion(self, file_path: str):
        """Remove deleted file's chunks from the vector store."""
        print(f"[Watcher] File deleted: {Path(file_path).name}")
        from backend.services.vector_store import vector_store
        try:
            vector_store.delete_by_file(file_path)
        except Exception as e:
            print(f"[Watcher] Error handling deletion: {e}")


class FileWatcher:
    """Manages the Watchdog observer for the data directory."""

    def __init__(self):
        self._observer = None
        self._handler = _IngestionHandler()
        self._running = False

    def start(self, loop: asyncio.AbstractEventLoop):
        """Start watching the data directory."""
        if self._running:
            return

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._handler.set_loop(loop)

        self._observer = Observer()
        self._observer.schedule(self._handler, str(DATA_DIR), recursive=True)
        self._observer.daemon = True
        self._observer.start()
        self._running = True
        print(f"[Watcher] Monitoring: {DATA_DIR}")

    def stop(self):
        """Stop the file watcher."""
        if self._observer and self._running:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._running = False
            print("[Watcher] Stopped")

    @property
    def is_running(self) -> bool:
        return self._running


# Global singleton
file_watcher = FileWatcher()
