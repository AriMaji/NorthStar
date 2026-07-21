"""System tray menu integration."""

from PySide6.QtCore import Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class Tray(QSystemTrayIcon):
    show_requested = Signal()
    add_requested = Signal()
    quit_requested = Signal()

    def __init__(self, icon: QIcon, parent=None):
        super().__init__(icon, parent)
        menu = QMenu()
        menu.addAction("Show NorthStar", self.show_requested.emit)
        menu.addAction("New task", self.add_requested.emit)
        menu.addSeparator()
        menu.addAction("Quit", self.quit_requested.emit)
        self.setContextMenu(menu)
        self.setToolTip("NorthStar")
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_requested.emit()
