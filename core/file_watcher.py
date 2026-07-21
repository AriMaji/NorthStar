"""Small polling watcher used to notice external task-file changes."""

from __future__ import annotations

from pathlib import Path


class FileWatcher:
    """Tracks a file's modification time without a platform-specific dependency."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._stamp: int | None = self._current_stamp()

    def changed(self) -> bool:
        stamp = self._current_stamp()
        if stamp != self._stamp:
            self._stamp = stamp
            return True
        return False

    def mark_current(self) -> None:
        self._stamp = self._current_stamp()

    def _current_stamp(self) -> int | None:
        try:
            return self.path.stat().st_mtime_ns
        except FileNotFoundError:
            return None
