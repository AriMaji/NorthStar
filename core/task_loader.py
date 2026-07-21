"""Task models and JSON storage for NorthStar.

Two loaders exist:
- TaskLoader   – original manual tasks (data/tasks.json legacy format).
- EmailTaskLoader – reads the AI-analysed email JSON format and presents
                    each action item as an EmailTask.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


class TaskDataError(RuntimeError):
    """Raised when the task database cannot be read safely."""


# ---------------------------------------------------------------------------
# Original manual Task (kept for backward compatibility)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Task:
    id: str
    title: str
    notes: str = ""
    completed: bool = False
    priority: str = "Medium"
    due_date: str | None = None
    is_north_star: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Task":
        title = str(value.get("title", "")).strip()
        if not title:
            raise ValueError("Every task needs a title.")
        due_date = value.get("due_date") or None
        if due_date:
            date.fromisoformat(str(due_date))
        priority = str(value.get("priority", "Medium"))
        if priority not in {"Low", "Medium", "High"}:
            priority = "Medium"
        return cls(
            id=str(value.get("id") or uuid4()), title=title,
            notes=str(value.get("notes", "")), completed=bool(value.get("completed", False)),
            priority=priority, due_date=str(due_date) if due_date else None,
            is_north_star=bool(value.get("is_north_star", False)),
            created_at=str(value.get("created_at") or datetime.now().isoformat(timespec="seconds")),
            updated_at=str(value.get("updated_at") or datetime.now().isoformat(timespec="seconds")),
        )

    def touch(self) -> None:
        self.updated_at = datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Email-derived task (from AI-analysed email JSON)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class EmailTask:
    """One action item extracted from an AI-analysed email."""
    id: str                        # unique id (email_id + index)
    email_id: str                  # original email identifier
    sender: str                    # sender email address
    summary: str                   # email summary
    task: str                      # the specific action required
    execution_method: str          # how to execute the task
    priority_value: float          # lower = more important
    deadline: str | None           # "YYYY-MM-DD HH:MM" or None
    risk_level: str                # NONE / LOW / MEDIUM / HIGH / CRITICAL
    risk_reason: str | None        # why it's risky, if applicable
    is_suspicious: bool            # flagged by analyser
    completed: bool = False
    is_north_star: bool = False

    # ── derived helpers ──────────────────────────────────────────────────────

    @property
    def title(self) -> str:
        """Alias so UI code can treat EmailTask like Task."""
        return self.task

    @property
    def notes(self) -> str:
        return self.execution_method

    @property
    def due_date(self) -> str | None:
        """Return only the date portion for legacy UI compatibility."""
        if self.deadline:
            return self.deadline.split(" ")[0]
        return None

    def deadline_dt(self) -> datetime | None:
        """Parse deadline as a datetime object."""
        if not self.deadline:
            return None
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(self.deadline, fmt)
            except ValueError:
                continue
        return None

    def time_left(self) -> str:
        """Human-readable countdown to deadline, e.g. '2h 34m 12s' or 'Overdue'."""
        dt = self.deadline_dt()
        if dt is None:
            return "No deadline"
        delta = dt - datetime.now()
        total_secs = int(delta.total_seconds())
        if total_secs <= 0:
            return "Overdue"
        days, rem = divmod(total_secs, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        if minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    def touch(self) -> None:
        pass  # email tasks are read-only; satisfy interface


# ---------------------------------------------------------------------------
# Loader for the email JSON format
# ---------------------------------------------------------------------------

class EmailTaskLoader:
    """Read the AI-analysed email JSON file and return EmailTask instances."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> list[EmailTask]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise TaskDataError(f"Could not read {self.path.name}: {error}") from error
        if not isinstance(raw, list):
            raise TaskDataError("The email task file must contain a JSON list.")

        tasks: list[EmailTask] = []
        for email in raw:
            if not isinstance(email, dict):
                continue
            if not email.get("action_required", False):
                continue  # skip non-actionable emails
            for idx, item in enumerate(email.get("action_items", [])):
                if not isinstance(item, dict):
                    continue
                task_text = str(item.get("task", "")).strip()
                if not task_text:
                    continue
                uid = f"{email.get('email_id', 'unknown')}-{idx}"
                tasks.append(EmailTask(
                    id=uid,
                    email_id=str(email.get("email_id", "")),
                    sender=str(email.get("sender", "")),
                    summary=str(email.get("summary", "")),
                    task=task_text,
                    execution_method=str(item.get("execution_method", "Review email to complete task.")),
                    priority_value=float(email.get("priority_value", 9999.0)),
                    deadline=str(email.get("deadline")) if email.get("deadline") else None,
                    risk_level=str(email.get("risk_level", "NONE")),
                    risk_reason=str(email.get("risk_reason")) if email.get("risk_reason") else None,
                    is_suspicious=bool(email.get("is_suspicious", False)),
                ))

        # Sort ascending: lower priority_value = more important = comes first
        tasks.sort(key=lambda t: t.priority_value)
        return tasks


# ---------------------------------------------------------------------------
# Original manual TaskLoader (unchanged)
# ---------------------------------------------------------------------------

class TaskLoader:
    """Read and write the user's manual tasks, using atomic writes."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> list[Task]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise TaskDataError(f"Could not read {self.path.name}: {error}") from error
        if not isinstance(raw, list):
            raise TaskDataError("The task file must contain a JSON list.")
        try:
            tasks = [Task.from_dict(item) for item in raw if isinstance(item, dict)]
        except (TypeError, ValueError) as error:
            raise TaskDataError(f"The task file contains an invalid task: {error}") from error
        focused = False
        for task in tasks:
            if task.completed or (task.is_north_star and focused):
                task.is_north_star = False
            elif task.is_north_star:
                focused = True
        return tasks

    def save(self, tasks: list[Task]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps([asdict(task) for task in tasks], indent=2, ensure_ascii=False) + "\n"
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=self.path.parent, suffix=".tmp") as file:
                file.write(payload)
                temporary_path = Path(file.name)
            os.replace(temporary_path, self.path)
        except OSError as error:
            raise TaskDataError(f"Could not save {self.path.name}: {error}") from error

    @staticmethod
    def new_task(title: str) -> Task:
        return Task(id=str(uuid4()), title=title.strip())
