"""Floating always-on-top star icon for NorthStar.

Behaviour:
- A small icon-only button sits in the top-right corner of the screen.
- On mouse-enter: a task list panel slides out to the left.
- On mouse-leave (both icon and panel): panel hides after a short delay.
- Single-clicking a task shows a lightweight read-only summary popup.
- Draggable by clicking and dragging the icon.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QSize, QTimer, Qt, Signal
from PySide6.QtGui import (
    QColor, QIcon, QPainter, QPainterPath, QPixmap,
)
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QVBoxLayout, QWidget,
)

from core import Task

_ICON_SIZE    = 48          # floating icon diameter
_PANEL_W      = 300         # width of the slide-out task list
_PANEL_MAX_H  = 360         # max height of the task list
_HIDE_DELAY   = 450         # ms before panel hides after mouse leaves
_MARGIN       = 16          # gap from screen edge

_ASSETS = Path(__file__).resolve().parent.parent / "assets"


# ---------------------------------------------------------------------------
# Summary popup — shown on single task click
# ---------------------------------------------------------------------------

class _SummaryPopup(QWidget):
    """Read-only task detail card. Click it to open the main app."""

    open_app_requested = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._task = None  # current EmailTask being shown

        self._card = QFrame()
        self._card.setObjectName("card")
        self._card.setStyleSheet("""
            #card {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #0d1b2e, stop:1 #0a1220);
                border: 1px solid #1e4a7a;
                border-radius: 12px;
            }
            #card:hover { border: 1px solid #3b9eff; }
        """)

        self._title = QLabel()
        self._title.setWordWrap(True)
        self._title.setStyleSheet(
            "color:#ffffff; font-weight:700; font-size:14px; background:transparent;"
        )
        self._badge = QLabel()
        self._badge.setStyleSheet("font-size:11px; background:transparent;")

        self._timer_lbl = QLabel()
        self._timer_lbl.setStyleSheet(
            "color:#5baeff; font-size:13px; font-weight:600; background:transparent;"
        )

        self._notes = QLabel()
        self._notes.setWordWrap(True)
        self._notes.setMaximumWidth(_PANEL_W - 32)
        self._notes.setStyleSheet(
            "color:#8dafc8; font-size:12px; background:transparent;"
        )

        self._hint = QLabel("click to open app")
        self._hint.setStyleSheet(
            "color:#2e5079; font-size:10px; background:transparent;"
        )

        inner = QVBoxLayout(self._card)
        inner.setContentsMargins(16, 14, 16, 12)
        inner.setSpacing(5)
        inner.addWidget(self._title)
        inner.addWidget(self._badge)
        inner.addWidget(self._timer_lbl)
        inner.addWidget(self._notes)
        inner.addWidget(self._hint)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._card)

        # Auto-hide after 8 s
        self._auto_hide = QTimer(self)
        self._auto_hide.setSingleShot(True)
        self._auto_hide.setInterval(8000)
        self._auto_hide.timeout.connect(self.hide)

        # Live 1-second tick for the countdown label
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._refresh_timer)

    def show_for(self, task, anchor: QPoint) -> None:
        from core import EmailTask
        self._task = task
        self._title.setText(task.title)

        if isinstance(task, EmailTask):
            risk_colours = {
                "CRITICAL": "#f87171", "HIGH": "#fb923c",
                "MEDIUM": "#fbbf24",  "LOW": "#a3e635", "NONE": "#6ee7b7",
            }
            rc = risk_colours.get(task.risk_level, "#8dafc8")
            badge_parts = [f"<span style='color:{rc};font-weight:600'>{task.risk_level}</span>"]
            if task.deadline:
                badge_parts.append(f"<span style='color:#57606a'> · due {task.deadline}</span>")
            self._badge.setText("".join(badge_parts))
            method = task.execution_method.strip()
            self._notes.setText(
                f"<b style='color:#8dafc8'>How:</b> {method}"
                if method else "<i style='color:#4a6a82'>No instructions</i>"
            )
            self._timer_lbl.show()
            self._refresh_timer()
            self._tick.start()
        else:
            colours = {"High": "#f87171", "Medium": "#fbbf24", "Low": "#34d399"}
            colour = colours.get(task.priority, "#8dafc8")
            badge_parts = [f"<span style='color:{colour};font-weight:600'>{task.priority}</span>"]
            if task.due_date:
                badge_parts.append(f"<span style='color:#8dafc8'> · due {task.due_date}</span>")
            self._badge.setText("".join(badge_parts))
            self._notes.setText(task.notes.strip() or "<i style='color:#4a6a82'>No notes</i>")
            self._timer_lbl.hide()
            self._tick.stop()

        self.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        x = anchor.x() - self.width() - 8
        y = anchor.y() - self.height() // 2
        x = max(screen.left() + 4, x)
        y = max(screen.top() + 4, min(y, screen.bottom() - self.height() - 4))
        self.move(x, y)
        self.show()
        self._auto_hide.start()

    def _refresh_timer(self) -> None:
        from core import EmailTask
        if not isinstance(self._task, EmailTask):
            return
        tl = self._task.time_left()
        colour = "#f87171" if tl == "Overdue" else "#5baeff"
        self._timer_lbl.setText(
            f"<span style='color:{colour}'>⏱ {tl}</span>"
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_app_requested.emit()
            self.hide()
        super().mousePressEvent(event)

    def hide(self) -> None:
        self._auto_hide.stop()
        self._tick.stop()
        super().hide()


# ---------------------------------------------------------------------------
# Slide-out task list panel
# ---------------------------------------------------------------------------

class _TaskPanel(QWidget):
    task_clicked = Signal(str)

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._card = QFrame()
        self._card.setObjectName("panel")
        self._card.setStyleSheet("""
            #panel {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #0d1b2e, stop:1 #08111e);
                border: 1px solid #1e4a7a;
                border-radius: 14px;
            }
            QListWidget {
                background: transparent;
                border: none;
                color: #c5dff5;
                font-size: 13px;
                outline: none;
            }
            QListWidget::item {
                padding: 8px 12px;
                border-radius: 6px;
                margin: 1px 6px;
            }
            QListWidget::item:hover {
                background: rgba(59,158,255,0.15);
                color: #ffffff;
            }
            QListWidget::item:selected {
                background: rgba(59,158,255,0.22);
                color: #ffffff;
            }
        """)

        self._header = QLabel("✦  Tasks")
        self._header.setStyleSheet(
            "color:#5baeff; font-weight:700; font-size:11px; "
            "letter-spacing:1px; text-transform:uppercase; "
            "padding:12px 14px 4px; background:transparent;"
        )

        self._sep = QFrame()
        self._sep.setFrameShape(QFrame.Shape.HLine)
        self._sep.setStyleSheet("color:#1e4a7a; background:#1e4a7a; margin:0 10px;")
        self._sep.setFixedHeight(1)

        self._list = QListWidget()
        self._list.setMaximumHeight(_PANEL_MAX_H)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.itemClicked.connect(self._on_click)

        inner = QVBoxLayout(self._card)
        inner.setContentsMargins(0, 0, 0, 8)
        inner.setSpacing(0)
        inner.addWidget(self._header)
        inner.addWidget(self._sep)
        inner.addWidget(self._list)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._card)
        self.setFixedWidth(_PANEL_W)

        self._tasks: list = []

    def set_tasks(self, tasks: list) -> None:
        self._tasks = [t for t in tasks if not t.completed]
        self._list.clear()
        for task in self._tasks:
            from core import EmailTask
            prefix = "✦ " if task.is_north_star else "   "
            tl = task.time_left() if isinstance(task, EmailTask) else ""
            suffix = f"  [{tl}]" if tl and tl not in ("No deadline", "—") else ""
            item = QListWidgetItem(f"{prefix}{task.title}{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, task.id)
            if task.is_north_star:
                item.setForeground(QColor("#ffd166"))
            elif isinstance(task, EmailTask) and tl == "Overdue":
                item.setForeground(QColor("#f87171"))
            self._list.addItem(item)
        row_h = self._list.sizeHintForRow(0) if self._tasks else 36
        self._list.setFixedHeight(
            min(_PANEL_MAX_H, max(40, row_h * len(self._tasks) + 10))
        )
        self.adjustSize()

    def _on_click(self, item: QListWidgetItem) -> None:
        tid = item.data(Qt.ItemDataRole.UserRole)
        if tid:
            self.task_clicked.emit(tid)


# ---------------------------------------------------------------------------
# Floating star icon
# ---------------------------------------------------------------------------

class StarWidget(QWidget):
    """Icon-only floating widget. Shows task panel on hover."""

    complete_requested   = Signal(str)
    choose_requested     = Signal()
    focus_task_requested = Signal(str)
    open_app_requested   = Signal()

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(_ICON_SIZE, _ICON_SIZE)

        self._task:  Task | None = None
        self._tasks: list[Task]  = []
        self._drag_pos: QPoint | None = None
        self._hovered = False

        # SVG icon fills the whole widget
        self._svg = QSvgWidget(str(_ASSETS / "northstar.svg"), self)
        self._svg.setFixedSize(_ICON_SIZE, _ICON_SIZE)
        self._svg.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        # Child panels (top-level windows)
        self._panel   = _TaskPanel()
        self._summary = _SummaryPopup()
        self._panel.task_clicked.connect(self._on_task_clicked)
        self._summary.open_app_requested.connect(self.open_app_requested)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(_HIDE_DELAY)
        self._hide_timer.timeout.connect(self._hide_panel)

        self._panel.installEventFilter(self)

        self._position_to_corner()

    # ── public API ──────────────────────────────────────────────────────────

    def set_task(self, task: Task | None) -> None:
        self._task = task
        self.update()   # repaint glow intensity

    def set_tasks(self, tasks: list[Task]) -> None:
        self._tasks = tasks
        self._panel.set_tasks(tasks)

    # ── positioning ─────────────────────────────────────────────────────────

    def _position_to_corner(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - _ICON_SIZE - _MARGIN,
                  screen.top()  + _MARGIN)

    def _position_panel(self) -> None:
        bar = self.frameGeometry()
        px  = bar.left() - _PANEL_W - 6
        py  = bar.top()
        screen = QApplication.primaryScreen().availableGeometry()
        px = max(screen.left() + 4, px)
        py = max(screen.top()  + 4, min(py, screen.bottom() - self._panel.height() - 4))
        self._panel.move(px, py)

    # ── hover ────────────────────────────────────────────────────────────────

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._hide_timer.stop()
        self._show_panel()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._hide_timer.start()
        self.update()
        super().leaveEvent(event)

    def _show_panel(self) -> None:
        self._panel.set_tasks(self._tasks)
        self._position_panel()
        self._panel.show()

    def _hide_panel(self) -> None:
        self._panel.hide()
        self._summary.hide()

    def eventFilter(self, obj, event) -> bool:
        if obj is self._panel:
            if event.type() == QEvent.Type.Enter:
                self._hide_timer.stop()
            elif event.type() == QEvent.Type.Leave:
                self._hide_timer.start()
        return super().eventFilter(obj, event)

    # ── task click ───────────────────────────────────────────────────────────

    def _on_task_clicked(self, task_id: str) -> None:
        task = next((t for t in self._tasks if t.id == task_id), None)
        if task:
            pr = self._panel.frameGeometry()
            anchor = QPoint(pr.left(), pr.top() + pr.height() // 2)
            self._summary.show_for(task, anchor)

    # ── drag ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    # ── paint: outer glow ring ───────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Pulsing blue glow ring — brighter on hover or when a task is set
        if self._hovered:
            glow_colour = QColor(59, 158, 255, 160)
            glow_radius = 10
        elif self._task:
            glow_colour = QColor(59, 158, 255, 80)
            glow_radius = 7
        else:
            glow_colour = QColor(30, 74, 122, 60)
            glow_radius = 5

        # Draw several concentric transparent rings for a soft glow
        for i in range(glow_radius, 0, -1):
            alpha = int(glow_colour.alpha() * (i / glow_radius) * 0.5)
            c = QColor(glow_colour.red(), glow_colour.green(), glow_colour.blue(), alpha)
            path = QPainterPath()
            inset = glow_radius - i
            path.addRoundedRect(
                inset, inset,
                _ICON_SIZE - 2 * inset,
                _ICON_SIZE - 2 * inset,
                (_ICON_SIZE // 2) - inset,
                (_ICON_SIZE // 2) - inset,
            )
            painter.fillPath(path, c)
