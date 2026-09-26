from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction
from PyQt5.QtGui import QIcon


class TrayIcon(QSystemTrayIcon):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIcon(QIcon.fromTheme("preferences-system"))
        self._setup_menu()
        self.activated.connect(self._on_activated)

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
