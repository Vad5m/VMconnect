import sys, threading

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon

from gui import SettingsWindow
import mouse
import keyboard
import app_connect


class ports:
    """Без этого класса я забуду на каком порте что."""
    MAIN_PORT = 42042  # на нем основное приложение
    MOUSE_PORT = 42000  # на нем мышь
    KEYBOARD_PORT = 42001  # на нем клавиатура
    GAMEPAD_PORT = 42002  # на нем геймпад
    SSH_PORT = 42003  # на нем ssh
    FTP_PORT = 42004  # на нем ftp


class Application:
    def __init__(self, app):
        self.app = app
        self.mouse_thread = None
        self.keyboard_thread = None
        self.window = SettingsWindow(on_quit=self.quit)

    def start_mouse(self):
        self.mouse_thread = threading.Thread(target=mouse.main, daemon=True)
        self.mouse_thread.start()

    def start_keyboard(self):
        self.keyboard_thread = threading.Thread(target=keyboard.main, daemon=True)
        self.keyboard_thread.start()

    def start_settings_server(self):
        app_connect.start_all()

    def stop_server(self):
        app_connect.stop_all(timeout=3)

    def run(self):
        self.start_settings_server()
        self.start_mouse()
        self.start_keyboard()
        self.window.show()
        exit_code = self.app.exec_()
        self.stop_server()
        sys.exit(exit_code)

    def quit(self):
        self.window.save_settings()
        self.stop_server()
        self.app.quit()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon.fromTheme("preferences-system"))
    app.setStyle("Fusion")

    Application(app).run()


if __name__ == "__main__":
    ascii = "ascii"
    print(ascii)
    main()
