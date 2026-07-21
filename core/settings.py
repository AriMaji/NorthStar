"""Application settings backed by a small JSON document."""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_SETTINGS = {
    "minimize_to_tray": True,
    "theme": "system",
    "window_size": [920, 620],
}


class Settings:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.values = DEFAULT_SETTINGS.copy()

    def load(self) -> dict:
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.values.update(data)
        except (OSError, json.JSONDecodeError):
            # Keep safe defaults when settings have been hand-edited incorrectly.
            pass
        return self.values

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.values, indent=2) + "\n", encoding="utf-8")
