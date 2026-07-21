"""Task list panel — displays EmailTask rows with live countdown timers."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from core import EmailTask, Task

# type alias so panel works with either task type
AnyTask = EmailTask | Task

_RISK_COLOURS = {
    "CRITICAL": "#f87171",
    "HIGH":     "#fb923c",
    "MEDIUM":   "#fbbf24",
    "LOW":      "#a3e635",
    "NONE":     "#6ee7b7",
}


class TaskPanel(QWidget):
    add_requested      = Signal()
    edit_requested     = Signal(str)
    complete_requested = Signal(str)
    delete_requested   = Signal(str)
    focus_requested    = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tasks: list[AnyTask] = []

        # ── header bar ───────────────────────────────────────────────────────
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search tasks…")
        self.filter = QComboBox()
        self.filter.addItems(["Active", "All", "Completed"])
        self.add = QPushButton("+ New task")

        # ── action buttons ───────────────────────────────────────────────────
        self.edit     = QPushButton("Edit")
        self.complete = QPushButton("Complete")
        self.focus    = QPushButton("Set North Star")
        self.delete   = QPushButton("Delete")

        # ── table: Task | Risk | Deadline | Time Left | Status ────────────
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Task", "Risk", "Deadline", "Time Left", "Status"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 5):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

        # ── layout ───────────────────────────────────────────────────────────
        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("Tasks"))
        header_row.addStretch()
        header_row.addWidget(self.search)
        header_row.addWidget(self.filter)
        header_row.addWidget(self.add)

        action_row = QHBoxLayout()
        action_row.addWidget(self.edit)
        action_row.addWidget(self.complete)
        action_row.addWidget(self.focus)
        action_row.addStretch()
        action_row.addWidget(self.delete)

        layout = QVBoxLayout(self)
        layout.addLayout(header_row)
        layout.addWidget(self.table)
        layout.addLayout(action_row)

        # ── signals ──────────────────────────────────────────────────────────
        self.search.textChanged.connect(self.refresh)
        self.filter.currentTextChanged.connect(self.refresh)
        self.add.clicked.connect(self.add_requested)
        self.edit.clicked.connect(self._edit_selected)
        self.complete.clicked.connect(lambda: self._with_selected(self.complete_requested))
        self.focus.clicked.connect(lambda: self._with_selected(self.focus_requested))
        self.delete.clicked.connect(lambda: self._with_selected(self.delete_requested))
        self.table.cellDoubleClicked.connect(lambda *_: self._edit_selected())
        self.table.itemSelectionChanged.connect(self._update_actions)
        # Single click → view detail page
        self.table.cellClicked.connect(lambda *_: self._with_selected(self.edit_requested))

        # ── live countdown refresh (every 30 s) ──────────────────────────────
        self._tick = QTimer(self)
        self._tick.setInterval(30_000)
        self._tick.timeout.connect(self._refresh_countdowns)
        self._tick.start()

        self._update_actions()

    # ── public API ───────────────────────────────────────────────────────────

    def set_tasks(self, tasks: list[AnyTask]) -> None:
        self.tasks = tasks
        self.refresh()

    # ── refresh ──────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        selected = self.selected_id()
        query = self.search.text().casefold().strip()
        mode  = self.filter.currentText()

        rows = [
            t for t in self.tasks
            if (
                mode == "All"
                or (mode == "Active"    and not t.completed)
                or (mode == "Completed" and     t.completed)
            ) and (
                not query
                or query in (t.title + " " + (t.notes or "")).casefold()
            )
        ]

        # Sort: incomplete first, then by priority_value ascending (lower = more urgent)
        def _sort_key(t: AnyTask):
            pv = t.priority_value if isinstance(t, EmailTask) else 5000.0
            return (t.completed, pv)

        rows.sort(key=_sort_key)

        self.table.setRowCount(len(rows))
        for row, task in enumerate(rows):
            self._fill_row(row, task)
            if task.id == selected:
                self.table.selectRow(row)

        self._update_actions()

    def _fill_row(self, row: int, task: AnyTask) -> None:
        is_email = isinstance(task, EmailTask)

        # Col 0 — task title
        prefix = "✦ " if task.is_north_star else ""
        title_item = self._make_item(f"{prefix}{task.title}", task.id)
        if task.is_north_star:
            title_item.setForeground(QColor("#ffd166"))

        # Col 1 — risk level
        risk = task.risk_level if is_email else "—"
        risk_item = self._make_item(risk, task.id)
        risk_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        risk_colour = _RISK_COLOURS.get(risk, "#c5dff5")
        risk_item.setForeground(QColor(risk_colour))

        # Col 2 — deadline date
        dl = task.deadline.split(" ")[0] if (is_email and task.deadline) else (task.due_date or "—")
        dl_item = self._make_item(dl, task.id)
        dl_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        # Col 3 — time left countdown
        tl = task.time_left() if is_email else "—"
        tl_item = self._make_item(tl, task.id)
        tl_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if tl == "Overdue":
            tl_item.setForeground(QColor("#f87171"))
        elif is_email and task.deadline_dt():
            secs = int((task.deadline_dt() - datetime.now()).total_seconds())
            if secs < 3600:
                tl_item.setForeground(QColor("#fbbf24"))

        # Col 4 — status
        status = "Done" if task.completed else "Open"
        st_item = self._make_item(status, task.id)
        st_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        if task.completed:
            for item in (title_item, risk_item, dl_item, tl_item, st_item):
                item.setForeground(QColor("#555e6a"))

        for col, item in enumerate([title_item, risk_item, dl_item, tl_item, st_item]):
            self.table.setItem(row, col, item)

    def _refresh_countdowns(self) -> None:
        """Update only the Time Left column without full redraw."""
        for row in range(self.table.rowCount()):
            id_item = self.table.item(row, 0)
            if not id_item:
                continue
            task_id = id_item.data(Qt.ItemDataRole.UserRole)
            task = next((t for t in self.tasks if t.id == task_id), None)
            if not isinstance(task, EmailTask):
                continue
            tl = task.time_left()
            tl_item = self.table.item(row, 3)   # col 3 = Time Left (no priority col)
            if tl_item:
                tl_item.setText(tl)
                if tl == "Overdue":
                    tl_item.setForeground(QColor("#f87171"))

    # ── helpers ──────────────────────────────────────────────────────────────

    def _make_item(self, text: str, task_id: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, task_id)
        return item

    def selected_id(self) -> str | None:
        item = self.table.item(self.table.currentRow(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _with_selected(self, signal) -> None:
        task_id = self.selected_id()
        if task_id:
            signal.emit(task_id)

    def _edit_selected(self) -> None:
        self._with_selected(self.edit_requested)

    def _update_actions(self) -> None:
        task_id = self.selected_id()
        task = next((t for t in self.tasks if t.id == task_id), None)
        for btn in (self.edit, self.complete, self.focus, self.delete):
            btn.setEnabled(task is not None)
        if task:
            self.complete.setText("Reopen" if task.completed else "Complete")
            self.focus.setEnabled(not task.completed)
