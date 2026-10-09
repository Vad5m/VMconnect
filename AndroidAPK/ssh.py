import json
import queue
import threading
import time
import urllib.request
from os.path import exists

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.logger import Logger
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.core.window import Window
from kivy.utils import get_color_from_hex

DEFAULT_HOST = "192.168.1.42"
DEFAULT_PORT = 42003
API_PREFIX = "/term"

CURRENT_HOST = DEFAULT_HOST
CURRENT_PORT = DEFAULT_PORT

CHAR_W = 8.4
CHAR_H = 18.0


def set_server(host, port=DEFAULT_PORT):
    global CURRENT_HOST, CURRENT_PORT
    CURRENT_HOST = host or DEFAULT_HOST
    CURRENT_PORT = port
    Logger.info(f"ssh: server set to {CURRENT_HOST}:{CURRENT_PORT}")


def _base_url():
    return f"http://{CURRENT_HOST}:{CURRENT_PORT}{API_PREFIX}"


def show_error(message, title="Error", duration=3.0):
    def _show(dt):
        try:
            popup = Popup(
                title=title,
                content=Label(text=str(message)[:500], halign="center",
                              valign="middle"),
                size_hint=(0.85, 0.4),
                auto_dismiss=True,
            )
            popup.content.bind(size=lambda w, s: setattr(w, "text_size", s))
            popup.open()
            if duration:
                Clock.schedule_once(lambda _dt: popup.dismiss(), duration)
        except Exception as e:
            Logger.error(f"show_error failed: {e}")

    Clock.schedule_once(_show, 0)


class HttpSender:
    def __init__(self, base_url_provider=None, on_error=None):
        self._base_url_provider = base_url_provider or _base_url
        self._on_error = on_error
        self._queue = queue.Queue(maxsize=512)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def send(self, endpoint, payload, method="POST"):
        try:
            self._queue.put_nowait((endpoint, payload, method))
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait((endpoint, payload, method))
            except (queue.Empty, queue.Full):
                pass

    def stop(self):
        self._stop.set()
        try:
            self._queue.put_nowait((None, None, None))
        except queue.Full:
            pass

    def _worker(self):
        while not self._stop.is_set():
            try:
                endpoint, payload, method = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            except Exception as e:
                Logger.error(f"HttpSender worker: {e}")
                continue

            if endpoint is None:
                break

            if endpoint.endswith("/cmd"):
                data = str(payload.get("data", ""))
                while True:
                    try:
                        nxt_ep, nxt_pl, nxt_m = self._queue.get_nowait()
                    except queue.Empty:
                        break
                    if nxt_ep.endswith("/cmd"):
                        data += "\n" + str(nxt_pl.get("data", ""))
                    else:
                        try:
                            self._queue.put_nowait((nxt_ep, nxt_pl, nxt_m))
                        except queue.Full:
                            pass
                        break
                payload = {"data": data}

            try:
                url = self._base_url_provider() + endpoint
            except Exception as e:
                self._report(f"bad base url: {e}")
                continue

            self._request(url, payload, method)

    def _request(self, url, payload, method):
        try:
            data = None
            if method == "POST":
                data = json.dumps(payload or {}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method=method,
            )
            with urllib.request.urlopen(req, timeout=2.0) as r:
                body = r.read().decode("utf-8", "replace")
            return json.loads(body) if body else {}
        except Exception as e:
            Logger.warning(f"HttpSender: {url} -> {e}")
            self._report(f"{type(e).__name__}: {e}")
            return None

    def _report(self, msg):
        if not self._on_error:
            return
        try:
            Clock.schedule_once(lambda dt: self._on_error(msg), 0)
        except Exception:
            pass


class BackButton(ButtonBehavior, BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (dp(48), dp(48))
        self._build()

    def _build(self):
        self.clear_widgets()
        img = Image(
            source="data/icons/back.png",
            size_hint=(1, 1),
            pos_hint={"center_x": 0.5, "center_y": 0.5},
            allow_stretch=True,
            keep_ratio=True,
        )
        self.add_widget(img)

    def on_state(self, *args):
        pass


class SshButton(ButtonBehavior, BoxLayout):
    text = StringProperty("")
    bg_color = (0.23, 0.23, 0.24, 1)
    pressed_color = (0.36, 0.36, 0.38, 1)
    radius = dp(12)

    def __init__(self, on_press=None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self._on_press_cb = on_press
        self._lbl = Label(
            text=self.text,
            halign="center",
            valign="middle",
            font_size=dp(14),
            color=(0.95, 0.95, 0.95, 1),
        )
        self._lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(self._lbl)
        self.bind(text=self._on_text_changed,
                  pos=self._sync, size=self._sync)

    def _on_text_changed(self, *args):
        self._lbl.text = self.text

    def _sync(self, *args):
        self._lbl.pos = self.pos
        self._lbl.size = self.size

    def on_release(self):
        if self._on_press_cb:
            try:
                self._on_press_cb()
            except Exception as e:
                Logger.error(f"button press: {e}")
                show_error(str(e), title="Button error")


class RoundedTextInput(AnchorLayout):
    text = StringProperty("")
    hint_text = StringProperty("")
    input_filter = None
    bg_color = (0.23, 0.23, 0.24, 1)
    fg_color = (0.95, 0.95, 0.95, 1)
    cursor_color = (0.95, 0.95, 0.95, 1)
    radius = dp(20)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_once(self._bind_input, 0)

    def _bind_input(self, dt):
        inp = self.ids.get("input")
        if inp is None:
            return
        if inp.text != self.text:
            inp.text = self.text
        inp.bind(text=self._on_input_text)

    def _on_input_text(self, instance, value):
        if self.text != value:
            self.text = value


class TermView(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.session = None
        self.history = []
        self.hist_idx = 0
        self._last_text = ""
        self._poll_ev = None
        self.sender = None
        self._build()

    def _build(self):
        self.orientation = "vertical"
        self.spacing = dp(8)
        self.padding = dp(8)

        self.scroll = ScrollView(
            size_hint=(1, 1),
            bar_width=dp(6),
            bar_color=(0.3, 0.35, 0.45, 1),
            bar_inactive_color=(0.2, 0.22, 0.28, 1),
            do_scroll_x=False,
        )
        self.out = Label(
            text="[color=#8b949e]connecting to server...[/color]",
            markup=True,
            halign="left",
            valign="top",
            font_size=dp(13),
            color=get_color_from_hex("#c9d1d9"),
            size_hint=(None, None),
            size=(Window.width, dp(20)),
            padding=(dp(10), dp(10)),
            line_height=1.05,
        )
        self.scroll.bind(width=self._resize_label)
        self.out.bind(texture_size=self._update_height)
        self.scroll.add_widget(self.out)
        self.add_widget(self.scroll)

        ctrl_row = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(36),
            spacing=dp(6),
        )
        ctrl_row.add_widget(self._mk_btn("Ctrl+C", lambda: self._ctrl("INT")))
        ctrl_row.add_widget(self._mk_btn("Ctrl+D", lambda: self._ctrl("EOF")))
        ctrl_row.add_widget(self._mk_btn("Ctrl+Z", lambda: self._ctrl("TSTP")))
        ctrl_row.add_widget(Widget(size_hint=(1, 1)))
        ctrl_row.add_widget(self._mk_btn("↑", self._history_prev, width=dp(44)))
        ctrl_row.add_widget(self._mk_btn("↓", self._history_next, width=dp(44)))
        self.add_widget(ctrl_row)

        input_row = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(46),
            spacing=dp(8),
        )
        input_row.add_widget(Label(
            text="[b][color=#58a6ff]$[/color][/b]",
            markup=True,
            font_size=dp(16),
            size_hint=(None, 1),
            width=dp(20),
            halign="center",
            valign="middle",
        ))

        self.input = RoundedTextInput(
            size_hint=(1, 1),
            hint_text="type command...",
        )
        input_row.add_widget(self.input)
        input_row.add_widget(self._mk_btn("Enter", self._submit_from_input,
                                          width=dp(80)))
        self.add_widget(input_row)

        Clock.schedule_once(self._bind_enter, 0)

    def _bind_enter(self, *_):
        inner = self.input.ids.get("input")
        if inner is not None:
            inner.bind(on_text_validate=self._on_enter)
            Clock.schedule_once(lambda dt: setattr(inner, "focus", True), 0.2)

    def _mk_btn(self, text, cb, width=dp(76)):
        b = SshButton(
            text=text,
            on_press=cb,
            size_hint=(None, 1),
            width=width,
        )
        return b

    def _resize_label(self, scroll, width):
        self.out.width = width
        self.out.text_size = (width, None)

    def _update_height(self, label, size):
        label.height = max(size[1], dp(20))

    def start(self):
        r = self.sender_call("POST", "/new", {})
        if r and r.get("status") == "ok":
            self.session = r.get("session")
            self._send_resize()
            self._poll_ev = Clock.schedule_interval(self._poll_screen, 0.5)
        else:
            msg = (r or {}).get("message", "no response")
            self._last_text = f"[color=#ff7b72]cannot connect: {msg}[/color]"
            self.out.text = self._last_text

    def stop(self):
        try:
            if self._poll_ev:
                Clock.unschedule(self._poll_ev)
                self._poll_ev = None
        except Exception:
            pass
        if self.session:
            self.sender_call("POST", f"/{self.session}/close", {})
            self.session = None

    def _sender_call_async(self, endpoint, payload, method="POST"):
        if self.sender is not None:
            self.sender.send(endpoint, payload, method)

    def sender_call(self, method, endpoint, payload):
        try:
            url = _base_url() + endpoint
        except Exception as e:
            return {"status": "error", "message": str(e)}
        try:
            data = None
            if method == "POST":
                data = json.dumps(payload or {}).encode("utf-8")
            req = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json"},
                method=method,
            )
            with urllib.request.urlopen(req, timeout=2.0) as r:
                body = r.read().decode("utf-8", "replace")
            return json.loads(body) if body else {}
        except Exception as e:
            return {"status": "error",
                    "message": f"{type(e).__name__}: {e}"}

    def _poll_screen(self, *_):
        if not self.session:
            return
        r = self.sender_call("GET", f"/{self.session}/screen", {})
        if r and r.get("status") == "ok":
            text = r.get("text", "")
            if text != self._last_text:
                self._last_text = text
                self.out.text = text
                Clock.schedule_once(self._scroll_bottom, 0.01)

    def _scroll_bottom(self, *_):
        self.scroll.scroll_y = 0.0

    def _send_resize(self, *_):
        if not self.session:
            return
        w = self.scroll.width or Window.width
        h = self.scroll.height or Window.height
        cols = max(20, int((w - dp(28)) / CHAR_W))
        rows = max(5, int((h - dp(28)) / CHAR_H))
        self._sender_call_async(
            f"/{self.session}/resize", {"rows": rows, "cols": cols})

    def _ctrl(self, name):
        if self.session:
            self._sender_call_async(f"/{self.session}/ctrl", {"data": name})
        self._refocus()

    def _refocus(self):
        inner = self.input.ids.get("input")
        if inner is not None:
            Clock.schedule_once(lambda dt: setattr(inner, "focus", True), 0)

    def _submit_cmd(self, cmd):
        if not cmd.strip() or not self.session:
            return
        self.history.append(cmd)
        self.hist_idx = len(self.history)
        self._sender_call_async(f"/{self.session}/cmd", {"data": cmd})

    def _on_enter(self, instance):
        cmd = instance.text
        instance.text = ""
        self._submit_cmd(cmd)
        self._refocus()

    def _submit_from_input(self):
        cmd = self.input.text or ""
        self.input.text = ""
        self._submit_cmd(cmd)
        self._refocus()

    def _history_prev(self):
        if not self.history:
            return
        self.hist_idx = max(0, self.hist_idx - 1)
        self.input.text = self.history[self.hist_idx]

    def _history_next(self):
        if not self.history:
            return
        self.hist_idx = min(len(self.history), self.hist_idx + 1)
        self.input.text = (
            self.history[self.hist_idx]
            if self.hist_idx < len(self.history) else ""
        )


class SSHRoot(BoxLayout):
    sender = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_once(self._bind_all, 0)

    def _bind_all(self, dt):
        term = self.ids.get("term")
        if term is None:
            return
        term.sender = self.sender
        term.start()

        btn_back = self.ids.get("btn_back")
        if btn_back is not None:
            btn_back.bind(on_release=lambda *_: self.go_back())

    def go_back(self):
        try:
            term = self.ids.get("term")
            if term is not None:
                term.stop()
        except Exception as e:
            Logger.error(f"stop on back: {e}")
        try:
            app = App.get_running_app()
            if app is not None and hasattr(app, "root"):
                sm = app.root
                if sm is not None and sm.has_screen("main"):
                    sm.current = "main"
        except Exception as e:
            Logger.error(f"go_back: {e}")


def _load_ssh_kv():
    for path in ("ssh.kv", "kv/ssh.kv", "screens/ssh.kv"):
        if exists(path):
            try:
                Builder.load_file(path)
                Logger.info(f"ssh: loaded kv {path}")
            except Exception as e:
                Logger.error(f"ssh.kv load error {path}: {e}")
            return


def create_ssh_screen(name="ssh"):
    _load_ssh_kv()

    sender = HttpSender(base_url_provider=_base_url,
                        on_error=_ssh_http_error)

    scr = Screen(name=name)
    scr.sender = sender

    root = SSHRoot()
    root.sender = sender
    scr.add_widget(root)

    def _on_leave(*_):
        term = root.ids.get("term")
        if term is not None:
            term.stop()

    scr.bind(on_leave=_on_leave)
    return scr


def _ssh_http_error(err):
    Logger.warning(f"HTTP error: {err}")
    show_error(err, title="Connection error", duration=2.5)


def stop_ssh_screen(scr):
    try:
        term = getattr(scr, "term", None)
        if term:
            term.stop()
        sender = getattr(scr, "sender", None)
        if sender:
            sender.stop()
    except Exception as e:
        Logger.error(f"stop_ssh_screen: {e}")
