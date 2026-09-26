import json
import os

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QFrame, QPushButton)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QBrush, QColor

from tray import TrayIcon

import mouse
import keyboard
import app_connect

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")


class ToggleSwitch(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(50, 24)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QPushButton {
                background-color: #555;
                border-radius: 12px;
                border: none;
            }
            QPushButton:checked {
                background-color: #4CAF50;
            }
            QPushButton:hover {
                background-color: #666;
            }
            QPushButton:checked:hover {
                background-color: #5cb860;
            }
        """)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self.isChecked():
            x = self.width() - self.height() + 3
            bg_color = QColor(255, 255, 255, 230)
        else:
            x = 2
            bg_color = QColor(255, 255, 255, 200)

        y = 2
        size = self.height() - 4
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(x, y, size, size)


class SettingsWindow(QMainWindow):
    def __init__(self, on_quit=None):
        super().__init__()

        self.on_quit = on_quit
        self.settings = self.load_settings()

        app_connect.bus.set_provider(lambda: self.settings)

        self.setWindowTitle("Управление системой")
        self.setGeometry(100, 100, 300, 460)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowMaximizeButtonHint)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(15, 10, 15, 10)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        main_layout.addWidget(line)

        self.toggles = {}
        toggles_list = [
            ("Мышка", "mouse"),
            ("Клавиатура", "keyboard"),
            ("Геймпад", "gamepad"),
            ("Голосовое управление", "voice_control"),
            ("ИИ помощник", "ai_assistant"),
            ("SSH", "ssh"),
            ("FTP сервер", "ftp_server"),
            ("Уведомления", "notifications"),
            ("Звук", "sound"),
            ("Микрофон", "microphone"),
        ]

        for label_text, key in toggles_list:
            toggle_frame = QFrame()
            toggle_layout = QHBoxLayout(toggle_frame)
            toggle_layout.setContentsMargins(10, 4, 10, 4)

            label = QLabel(label_text)
            label.setMinimumWidth(130)

            toggle = ToggleSwitch()
            toggle.blockSignals(True)
            toggle.setChecked(bool(self.settings.get(key, False)))
            toggle.blockSignals(False)
            toggle.key = key
            toggle.toggled.connect(self.on_toggle_changed)

            toggle_layout.addWidget(label)
            toggle_layout.addStretch()
            toggle_layout.addWidget(toggle)

            main_layout.addWidget(toggle_frame)
            self.toggles[key] = toggle

        main_layout.addStretch()

        self.apply_mouse_state(self.toggles["mouse"].isChecked())
        self.apply_keyboard_state(self.toggles["keyboard"].isChecked())

        self.tray_icon = TrayIcon(self)
        self.tray_icon.on_show = self.show_window
        self.tray_icon.on_quit = self._quit_from_tray
        self.tray_icon.show()
        self.tray_icon.notify("Приложение запущено",
                              "Управление системой работает в фоне")

    def _quit_from_tray(self):
        if self.on_quit:
            self.on_quit()
        else:
            self.close()

    def show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray_icon.notify("Свёрнуто",
                              "Приложение продолжает работу в трее",
                              1000)

    def quit_app(self):
        self.tray_icon.hide()
        if self.on_quit:
            self.on_quit()

    def apply_mouse_state(self, enabled: bool):
        try:
            if enabled:
                if hasattr(mouse, "enable"):
                    mouse.enable()
                else:
                    mouse.MOUSE_ENABLED = True
            else:
                if hasattr(mouse, "disable"):
                    mouse.disable()
                else:
                    mouse.MOUSE_ENABLED = False
        except Exception as e:
            print(f"[mouse] не удалось применить состояние ({enabled}): {e}")

    def apply_keyboard_state(self, enabled: bool):
        try:
            if enabled:
                if hasattr(keyboard, "enable"):
                    keyboard.enable()
                else:
                    keyboard.KEYBOARD_ENABLED = True
            else:
                if hasattr(keyboard, "disable"):
                    keyboard.disable()
                else:
                    keyboard.KEYBOARD_ENABLED = False
        except Exception as e:
            print(f"[keyboard] не удалось применить состояние ({enabled}): {e}")

    def load_settings(self):
        default_settings = {
            "mouse": False,
            "keyboard": False,
            "gamepad": False,
            "voice_control": False,
            "ai_assistant": False,
            "ssh": False,
            "ftp_server": False,
            "notifications": False,
            "sound": False,
            "microphone": False,
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                default_settings.update(saved)
                print(f"[settings] загружено из {CONFIG_FILE}: "
                      f"mouse={default_settings.get('mouse')}, "
                      f"keyboard={default_settings.get('keyboard')}")
            except Exception as e:
                print(f"[settings] ошибка загрузки: {e}")
        else:
            print(f"[settings] файл {CONFIG_FILE} не найден, используются значения по умолчанию")
        return default_settings

    def save_settings(self):
        try:
            for key, toggle in self.toggles.items():
                self.settings[key] = toggle.isChecked()
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
            print(f"[settings] сохранено в {CONFIG_FILE}: "
                  f"mouse={self.settings.get('mouse')}, "
                  f"keyboard={self.settings.get('keyboard')}")
        except Exception as e:
            print(f"[settings] ошибка сохранения: {e}")

    def on_toggle_changed(self, checked):
        toggle = self.sender()
        key = getattr(toggle, "key", None)

        if key == "mouse":
            self.apply_mouse_state(checked)
        elif key == "keyboard":
            self.apply_keyboard_state(checked)

        self.save_settings()

        app_connect.broadcast(self.settings)
