"""Task dialogs and detail pages for NorthStar."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, QTimer, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog,
                               QDialogButtonBox, QFormLayout, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QScrollArea, QSizePolicy,
                               QTextEdit, QVBoxLayout, QWidget)

from core import EmailTask, Task


# ---------------------------------------------------------------------------
# Original manual-task create/edit dialog (unchanged)
# ---------------------------------------------------------------------------

class TaskDetailDialog(QDialog):
    def __init__(self, task: Task | None = None, parent=None):
        super().__init__(parent)
        self.task = task
        self.setWindowTitle("Edit task" if task else "New task")
        self.setMinimumWidth(440)
        self.title = QLineEdit(task.title if task else "")
        self.title.setPlaceholderText("What needs to be done?")
        self.notes = QTextEdit(task.notes if task else "")
        self.notes.setPlaceholderText("Notes (optional)")
        self.priority = QComboBox()
        self.priority.addItems(["Low", "Medium", "High"])
        self.priority.setCurrentText(task.priority if task else "Medium")
        self.has_due_date = QCheckBox("Set a due date")
        self.due_date = QDateEdit(calendarPopup=True)
        self.due_date.setDisplayFormat("dd MMM yyyy")
        if task and task.due_date:
            parsed = date.fromisoformat(task.due_date)
            self.has_due_date.setChecked(True)
            self.due_date.setDate(QDate(parsed.year, parsed.month, parsed.day))
        else:
            self.due_date.setDate(QDate.currentDate())
        self.due_date.setEnabled(self.has_due_date.isChecked())
        self.has_due_date.toggled.connect(self.due_date.setEnabled)
        self.focus = QCheckBox("Make this my North Star task")
        self.focus.setChecked(task.is_north_star if task else False)
        form = QFormLayout()
        form.addRow("Title", self.title)
        form.addRow("Notes", self.notes)
        form.addRow("Priority", self.priority)
        form.addRow(self.has_due_date, self.due_date)
        form.addRow("Focus", self.focus)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _validate(self) -> None:
        if not self.title.text().strip():
            QMessageBox.warning(self, "Title required", "Please give the task a title.")
            return
        self.accept()

    def apply_to(self, task: Task) -> Task:
        task.title = self.title.text().strip()
        task.notes = self.notes.toPlainText().strip()
        task.priority = self.priority.currentText()
        task.due_date = self.due_date.date().toString("yyyy-MM-dd") if self.has_due_date.isChecked() else None
        task.is_north_star = self.focus.isChecked() and not task.completed
        task.touch()
        return task


# ---------------------------------------------------------------------------
# Full detail page for EmailTask — shown when a task row is clicked
# ---------------------------------------------------------------------------

_RISK_COLOURS = {
    "CRITICAL": "#f87171",
    "HIGH":     "#fb923c",
    "MEDIUM":   "#fbbf24",
    "LOW":      "#a3e635",
    "NONE":     "#6ee7b7",
}

_PAGE_STYLE = """
    QWidget#detailPage {
        background: #07111f;
    }
    QLabel#sectionHeader {
        color: #5baeff;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1px;
    }
    QFrame#card {
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 #0d1b2e, stop:1 #0a1520);
        border: 1px solid #1e3d5c;
        border-radius: 10px;
    }
    QLabel#fieldLabel {
        color: #4a7a9b;
        font-size: 12px;
    }
    QLabel#fieldValue {
        color: #d0e8f5;
        font-size: 13px;
    }
    QLabel#taskTitle {
        color: #ffffff;
        font-size: 18px;
        font-weight: 700;
    }
    QLabel#timerLabel {
        font-size: 22px;
        font-weight: 700;
    }
    QPushButton#backBtn {
        background: transparent;
        color: #5baeff;
        border: 1px solid #1e4a7a;
        border-radius: 6px;
        padding: 6px 16px;
        font-size: 13px;
    }
    QPushButton#backBtn:hover {
        background: rgba(59,158,255,0.12);
    }
"""


class EmailTaskDetailPage(QWidget):
    """Full-page organised view of one EmailTask's JSON data."""

    back_requested = Signal()

    def __init__(self, task: EmailTask, parent=None):
        super().__init__(parent)
        self.setObjectName("detailPage")
        self.setStyleSheet(_PAGE_STYLE)
        self._task = task

        # ── scroll area wrapping all content ─────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(content)
        vbox.setContentsMargins(32, 24, 32, 32)
        vbox.setSpacing(20)

        # ── top bar: back button + title ─────────────────────────────────────
        back_btn = QPushButton("← Back")
        back_btn.setObjectName("backBtn")
        back_btn.setFixedWidth(90)
        back_btn.clicked.connect(self.back_requested)

        top_bar = QHBoxLayout()
        top_bar.addWidget(back_btn)
        top_bar.addStretch()
        vbox.addLayout(top_bar)

        # ── task title ───────────────────────────────────────────────────────
        title_lbl = QLabel(task.task)
        title_lbl.setObjectName("taskTitle")
        title_lbl.setWordWrap(True)
        vbox.addWidget(title_lbl)

        # ── countdown timer ──────────────────────────────────────────────────
        self._timer_lbl = QLabel()
        self._timer_lbl.setObjectName("timerLabel")
        self._timer_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._refresh_timer()
        vbox.addWidget(self._timer_lbl)

        # ── section: Origin ──────────────────────────────────────────────────
        vbox.addWidget(self._section_header("ORIGIN"))
        vbox.addWidget(self._card([
            ("Email ID",  task.email_id),
            ("From",      task.sender),
            ("Summary",   task.summary),
        ]))

        # ── section: Action ──────────────────────────────────────────────────
        vbox.addWidget(self._section_header("ACTION"))
        vbox.addWidget(self._card([
            ("Task",             task.task),
            ("How to execute",   task.execution_method),
            ("Deadline",         task.deadline or "—"),
        ]))

        # ── section: Risk ────────────────────────────────────────────────────
        vbox.addWidget(self._section_header("RISK ASSESSMENT"))
        risk_colour = _RISK_COLOURS.get(task.risk_level, "#c5dff5")
        risk_val = (
            f"<span style='color:{risk_colour};font-weight:700'>{task.risk_level}</span>"
        )
        suspicious_val = (
            "<span style='color:#f87171;font-weight:600'>⚠ Yes — treat with caution</span>"
            if task.is_suspicious else
            "<span style='color:#6ee7b7'>No</span>"
        )
        vbox.addWidget(self._card([
            ("Risk Level",   risk_val,       True),
            ("Risk Reason",  task.risk_reason or "—"),
            ("Suspicious",   suspicious_val, True),
            ("Priority Score", f"{task.priority_value:.1f} (lower = more urgent)"),
        ]))

        vbox.addStretch()
        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # Live timer tick every second
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._refresh_timer)
        self._tick.start()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _section_header(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionHeader")
        return lbl

    def _card(self, rows: list) -> QFrame:
        frame = QFrame()
        frame.setObjectName("card")
        grid = QVBoxLayout(frame)
        grid.setContentsMargins(16, 12, 16, 12)
        grid.setSpacing(10)
        for entry in rows:
            label, value = entry[0], entry[1]
            rich = len(entry) > 2 and entry[2]

            row = QHBoxLayout()
            row.setSpacing(12)

            lbl = QLabel(label)
            lbl.setObjectName("fieldLabel")
            lbl.setFixedWidth(130)
            lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.VLine)
            sep.setStyleSheet("color: #1e3d5c;")
            sep.setFixedWidth(1)

            val = QLabel(value if rich else "")
            val.setObjectName("fieldValue")
            val.setWordWrap(True)
            val.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            if rich:
                val.setTextFormat(Qt.TextFormat.RichText)
            else:
                val.setText(str(value))

            row.addWidget(lbl)
            row.addWidget(sep)
            row.addWidget(val, 1)
            grid.addLayout(row)

            # Separator line between rows (except last)
            if entry != rows[-1]:
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setStyleSheet("color: #0f2035; background: #0f2035;")
                line.setFixedHeight(1)
                grid.addWidget(line)

        return frame

    def _refresh_timer(self) -> None:
        tl = self._task.time_left()
        if tl == "Overdue":
            colour = "#f87171"
        elif tl == "No deadline":
            colour = "#4a7a9b"
        else:
            colour = "#5baeff"
        self._timer_lbl.setText(f"<span style='color:{colour}'>⏱  {tl}</span>")
