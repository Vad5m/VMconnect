import os
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction, QApplication
from PyQt5.QtGui import QIcon


class TrayIcon(QSystemTrayIcon):
    _instances = []

    def __init__(self, parent=None):
        super().__init__(parent)

        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "icon.png")
        self.setIcon(QIcon(icon_path))

        self._setup_menu()
        self.activated.connect(self._on_activated)

    @classmethod
    def create_for_all_screens(cls, parent=None):
        cls._instances.clear()
        for screen in QApplication.screens():
            tray = cls(parent)
            cls._instances.append(tray)
            tray.show()
        return cls._instances

    def _setup_menu(self):
        menu = QMenu()

        self.show_action = QAction("Показать окно", self)
        self.show_action.triggered.connect(self._on_show)

        self.quit_action = QAction("Выйти", self)
        self.quit_action.triggered.connect(self._on_quit)

        menu.addAction(self.show_action)
        menu.addSeparator()
        menu.addAction(self.quit_action)

        self.setContextMenu(menu)

    def _on_show(self):
        callback = getattr(self, "on_show", None)
        if callback:
            callback()

    def _on_quit(self):
        callback = getattr(self, "on_quit", None)
        if callback:
            callback()

    def _on_activated(self, reason):
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self._on_show()

    def notify(self, title, message, msecs=2000):
        self.showMessage(title, message, QSystemTrayIcon.Information, msecs)
