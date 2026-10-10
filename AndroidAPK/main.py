import json
import socket
from os.path import exists
from threading import Thread

from kivy.app import App
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty, StringProperty, NumericProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from kivy.animation import Animation

from server_search import find_server
from permissions import request_android_permissions
import mouse as mouse_module
from mouse import DEFAULT_HOST, DEFAULT_PORT
import keyboard as keyboard_module
from keyboard import DEFAULT_HOST as KB_DEFAULT_HOST, DEFAULT_PORT as KB_DEFAULT_PORT
import gamepad as gamepad_module
from gamepad import DEFAULT_HOST as GP_DEFAULT_HOST, DEFAULT_PORT as GP_DEFAULT_PORT
import ssh as ssh_module
from ssh import DEFAULT_HOST as SSH_DEFAULT_HOST, DEFAULT_PORT as SSH_DEFAULT_PORT
import ftp_server as ftp_server_module


def load_kv_file(name: str):
    for path in (f"{name}.kv", f"kv/{name}.kv", f"screens/{name}.kv"):
        if exists(path):
            try:
                return Builder.load_file(path)
            except Exception as e:
                print(f"kv load error {path}:", e)
    return None


class FeatureButton(ButtonBehavior, BoxLayout):
    text = StringProperty("")
    active = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._build_content()

    def on_text(self, *args):
        if self.canvas is not None:
            self._build_content()

    def _build_content(self):
        self.clear_widgets()

        path = f"data/icons/{self.text}.png"
        has_icon = exists(path)

        if has_icon:
            img = Image(
                source=path,
                size_hint=(1, 1),
                allow_stretch=True,
                keep_ratio=True,
            )
            lbl = Label(
                text=self.text,
                size_hint=(1, None),
                height=dp(18),
                halign="center",
                valign="middle",
                font_size="13sp",
                color=(1, 1, 1, 1),
            )
            lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
            self.add_widget(img)
            self.add_widget(lbl)
        else:
            lbl = Label(
                text=self.text,
                halign="center",
                valign="middle",
                font_size="14sp",
                color=(1, 1, 1, 1),
            )
            lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
            self.add_widget(lbl)

    def on_press(self):
        Animation(opacity=0.6, d=0.06).start(self)

    def on_release(self):
        Animation(opacity=1.0, d=0.08).start(self)
        if not self.active:
            return

        app = App.get_running_app()
        print(f"[click] {self.text}")

        if self.text == "mouse":
            app.open_mouse()
            return

        if self.text == "keyboard":
            app.open_keyboard()
            return

        if self.text == "gamepad":
            app.open_gamepad()
            return

        if self.text == "ssh":
            app.open_ssh()
            return

        if self.text == "ftp_server":
            app.open_ftp_server()
            return

        if app.sock:
            try:
                app.sock.sendall(
                    (json.dumps({"cmd": self.text}) + "\n").encode("utf-8")
                )
            except Exception as e:
                print("send error:", e)

        app.open_screen(self.text)


class EmptyScreen(Screen):
    pass


class MainScreen(Screen):
    pass


class mykivy(App):
    host = StringProperty(DEFAULT_HOST)
    port = NumericProperty(DEFAULT_PORT)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.server_ip = None
        self.sock = None
        self.buttons = {}
        self._loaded_kv = set()
        self._discovering = False

    def build(self):
        self.title = "Поиск устройства"
        sm = ScreenManager(transition=NoTransition())
        sm.add_widget(MainScreen(name="main"))
        return sm

    def on_start(self):
        request_android_permissions()
        Window.bind(on_keyboard=self._on_keyboard)
        self._start_discovery()

    def on_stop(self):
        self._discovering = False
        try:
            sm = self.root
            if sm is not None:
                if sm.has_screen("mouse"):
                    mouse_module.stop_mouse_screen(sm.get_screen("mouse"))
                if sm.has_screen("keyboard"):
                    keyboard_module.stop_keyboard_screen(
                        sm.get_screen("keyboard"))
                if sm.has_screen("gamepad"):
                    gamepad_module.stop_gamepad_screen(
                        sm.get_screen("gamepad"))
                if sm.has_screen("ssh"):
                    ssh_module.stop_ssh_screen(sm.get_screen("ssh"))
                if sm.has_screen("ftp_server"):
                    ftp_server_module.stop_ftp_server_screen(
                        sm.get_screen("ftp_server"))
        except Exception as e:
            print(f"on_stop: {e}")

    def _on_keyboard(self, window, key, *args):
        if key in (27, 1073742094):
            sm = self.root
            if sm is not None and sm.current != 'main':
                sm.current = 'main'
                return True
        return False

    def open_screen(self, name: str):
        sm: ScreenManager = self.root
        if not sm.has_screen(name):
            loaded = None
            if name not in self._loaded_kv:
                loaded = load_kv_file(name)
                self._loaded_kv.add(name)

            if loaded is not None and isinstance(loaded, Screen):
                loaded.name = name
                sm.add_widget(loaded)
            elif loaded is not None and isinstance(loaded, type) and issubclass(loaded, Screen):
                sm.add_widget(loaded(name=name))
            else:
                root_widget = None
                if loaded is not None and hasattr(loaded, "children") and loaded.children:
                    root_widget = loaded

                if root_widget is not None:
                    scr = Screen(name=name)
                    parent = root_widget
                    while parent.parent is not None:
                        parent = parent.parent
                    if parent.parent is None and parent is not scr:
                        try:
                            parent.parent = scr
                        except Exception:
                            pass
                    if root_widget.parent is None:
                        scr.add_widget(root_widget)
                    sm.add_widget(scr)
                else:
                    sm.add_widget(EmptyScreen(name=name))

        sm.current = name

    def open_mouse(self):
        if not self.server_ip:
            print("mouse: server_ip ещё не найден")
            return

        mouse_module.set_server(self.server_ip, DEFAULT_PORT)

        sm: ScreenManager = self.root
        if not sm.has_screen("mouse"):
            scr = mouse_module.create_mouse_screen("mouse")
            sm.add_widget(scr)

        sm.current = "mouse"

    def open_keyboard(self):
        if not self.server_ip:
            print("keyboard: server_ip ещё не найден")
            return

        keyboard_module.set_server(self.server_ip, KB_DEFAULT_PORT)

        sm: ScreenManager = self.root
        if not sm.has_screen("keyboard"):
            scr = keyboard_module.create_keyboard_screen("keyboard")
            sm.add_widget(scr)

        sm.current = "keyboard"

    def open_gamepad(self):
        if not self.server_ip:
            print("gamepad: server_ip ещё не найден")
            return

        gamepad_module.set_server(self.server_ip, GP_DEFAULT_PORT)

        sm: ScreenManager = self.root
        if not sm.has_screen("gamepad"):
            scr = gamepad_module.create_gamepad_screen("gamepad")
            sm.add_widget(scr)

        sm.current = "gamepad"

    def open_ssh(self):
        if not self.server_ip:
            print("ssh: server_ip ещё не найден")
            return

        ssh_module.set_server(self.server_ip, SSH_DEFAULT_PORT)

        sm: ScreenManager = self.root
        if not sm.has_screen("ssh"):
            scr = ssh_module.create_ssh_screen("ssh")
            sm.add_widget(scr)

        sm.current = "ssh"

    def open_ftp_server(self):
        sm: ScreenManager = self.root
        if not sm.has_screen("ftp_server"):
            scr = ftp_server_module.create_ftp_server_screen("ftp_server")
            sm.add_widget(scr)
        sm.current = "ftp_server"

    def _start_discovery(self):
        self._discovering = True
        Thread(target=self._discover, daemon=True).start()

    def _discover(self):
        while self._discovering:
            ip = find_server()
            Clock.schedule_once(lambda dt, ip=ip: self._on_found(ip))
            if ip:
                break
            else:
                Clock.schedule_once(
                    lambda dt: setattr(
                        self.root.get_screen("main").ids.status,
                        "text",
                        "Поиск сервера..."
                    )
                )

    def _on_found(self, ip):
        main = self.root.get_screen("main")
        if ip:
            self._discovering = False
            self.server_ip = ip
            mouse_module.set_server(ip, DEFAULT_PORT)
            keyboard_module.set_server(ip, KB_DEFAULT_PORT)
            gamepad_module.set_server(ip, GP_DEFAULT_PORT)
            ssh_module.set_server(ip, SSH_DEFAULT_PORT)
            ftp_server_module.set_server(ip)
            self.host = ip
            main.ids.status.text = f"Найден сервер: {ip}"
            print(f"IP сервера сохранён: {self.server_ip}")
            Thread(target=self._listen_server, daemon=True).start()
        else:
            main.ids.status.text = "Поиск сервера..."

    def _listen_server(self):
        try:
            self.sock = socket.create_connection((self.server_ip, 42042))
            f = self.sock.makefile("r", encoding="utf-8")

            def hide_status():
                main = self.root.get_screen("main")
                main.ids.status.height = 0
                main.ids.status.opacity = 0
                main.ids.status.text = ""

            first = True
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if first:
                    first = False
                    Clock.schedule_once(lambda dt: hide_status())

                Clock.schedule_once(lambda dt, d=data: self._update_buttons(d))
        except Exception as e:
            print("Ошибка соединения:", e)

            def show_err(dt, err=e):
                main = self.root.get_screen("main")
                main.ids.status.text = f"Ошибка соединения: {err}"

            Clock.schedule_once(show_err)

    def _update_buttons(self, data: dict):
        main = self.root.get_screen("main")
        grid = main.ids.grid

        for name, value in data.items():
            btn = self.buttons.get(name)
            if btn is None:
                btn = FeatureButton(text=name)
                self.buttons[name] = btn
                grid.add_widget(btn)
            btn.active = bool(value)

    def _ip_filter(self, substring, from_undo):
        return ''.join(c for c in substring if c.isdigit() or c == '.')

    def _on_ip_changed(self, value):
        try:
            host = value.strip()
            if not host:
                return
            self.host = host
            mouse_module.set_server(host, self.port)
            keyboard_module.set_server(host, KB_DEFAULT_HOST and KB_DEFAULT_PORT)
            gamepad_module.set_server(host, GP_DEFAULT_PORT)
            ssh_module.set_server(host, SSH_DEFAULT_PORT)
            ftp_server_module.set_server(host)
        except Exception as e:
            print(f"on_ip_changed: {e}")


if __name__ == "__main__":
    mykivy().run()
