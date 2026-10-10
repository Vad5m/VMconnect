import json
import queue
import threading
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
from kivy.uix.widget import Widget
from kivy.core.window import Window


DEFAULT_HOST = "192.168.1.42"
DEFAULT_PORT = 42001
API_PREFIX = '/keyboard'

CURRENT_HOST = DEFAULT_HOST
CURRENT_PORT = DEFAULT_PORT


def set_server(host, port=DEFAULT_PORT):
    global CURRENT_HOST, CURRENT_PORT
    CURRENT_HOST = host or DEFAULT_HOST
    CURRENT_PORT = port
    Logger.info(f'keyboard: server set to {CURRENT_HOST}:{CURRENT_PORT}')


def _base_url():
    return f'http://{CURRENT_HOST}:{CURRENT_PORT}{API_PREFIX}'


def show_error(message, title='Error', duration=3.0):
    def _show(dt):
        try:
            popup = Popup(
                title=title,
                content=Label(text=str(message)[:500], halign='center',
                              valign='middle'),
                size_hint=(0.85, 0.4),
                auto_dismiss=True,
            )
            popup.content.bind(size=lambda w, s: setattr(w, 'text_size', s))
            popup.open()
            if duration:
                Clock.schedule_once(lambda _dt: popup.dismiss(), duration)
        except Exception as e:
            Logger.error(f'show_error failed: {e}')

    Clock.schedule_once(_show, 0)


class HttpSender:
    def __init__(self, base_url_provider=None, on_error=None,
                 on_layout=None):
        self._base_url_provider = base_url_provider or _base_url
        self._on_error = on_error
        self._on_layout = on_layout
        self._queue = queue.Queue(maxsize=256)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def send(self, endpoint, payload):
        try:
            self._queue.put_nowait((endpoint, payload))
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait((endpoint, payload))
            except (queue.Empty, queue.Full):
                pass

    def fetch_layout(self):
        try:
            url = self._base_url_provider() + '/layout'
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=1.5) as r:
                data = json.loads(r.read().decode('utf-8'))
            layout = data.get('layout')
            if self._on_layout:
                Clock.schedule_once(
                    lambda dt: self._on_layout(layout), 0)
        except Exception as e:
            Logger.warning(f'fetch_layout: {e}')
            self._report(f'{type(e).__name__}: {e}')

    def stop(self):
        self._stop.set()
        try:
            self._queue.put_nowait((None, None))
        except queue.Full:
            pass

    def _worker(self):
        while not self._stop.is_set():
            try:
                endpoint, payload = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            except Exception as e:
                Logger.error(f'HttpSender worker: {e}')
                continue

            if endpoint is None:
                break

            if endpoint == '/type':
                text = payload.get('text', '')
                while True:
                    try:
                        nxt_ep, nxt_pl = self._queue.get_nowait()
                    except queue.Empty:
                        break
                    if nxt_ep == '/type':
                        text += nxt_pl.get('text', '')
                    else:
                        try:
                            self._queue.put_nowait((nxt_ep, nxt_pl))
                        except queue.Full:
                            pass
                        break
                payload = {'text': text}

            elif endpoint == '/backspace':
                count = int(payload.get('count', 1))
                while True:
                    try:
                        nxt_ep, nxt_pl = self._queue.get_nowait()
                    except queue.Empty:
                        break
                    if nxt_ep == '/backspace':
                        count += int(nxt_pl.get('count', 1))
                    else:
                        try:
                            self._queue.put_nowait((nxt_ep, nxt_pl))
                        except queue.Full:
                            pass
                        break
                payload = {'count': count}

            try:
                url = self._base_url_provider() + endpoint
            except Exception as e:
                self._report(f'bad base url: {e}')
                continue

            self._post(url, payload)

    def _post(self, url, payload):
        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                url, data=data,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            urllib.request.urlopen(req, timeout=1.5)
        except Exception as e:
            Logger.warning(f'HttpSender: {url} -> {e}')
            self._report(f'{type(e).__name__}: {e}')

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
            source='data/icons/back.png',
            size_hint=(1, 1),
            pos_hint={'center_x': 0.5, 'center_y': 0.5},
            allow_stretch=True,
            keep_ratio=True,
        )
        self.add_widget(img)

    def on_state(self, *args):
        pass


class RoundedButton(Widget):
    bg_color = (0.23, 0.23, 0.24, 1)
    pressed_color = (0.36, 0.36, 0.38, 1)
    radius = dp(20)
    state = StringProperty('normal')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._on_press_cb = None
        self.bind(state=self._on_state)

    def _on_state(self, *args):
        pass

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            touch.grab(self)
            self.state = 'down'
            return True
        return False

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            self.state = 'normal'
            if self.collide_point(*touch.pos) and self._on_press_cb:
                try:
                    self._on_press_cb()
                except Exception as e:
                    Logger.error(f'button press: {e}')
                    show_error(str(e), title='Button error')
            return True
        return False


class RoundedTextInput(AnchorLayout):
    text = StringProperty('')
    hint_text = StringProperty('')
    input_filter = None
    bg_color = (0.23, 0.23, 0.24, 1)
    fg_color = (0.95, 0.95, 0.95, 1)
    cursor_color = (0.95, 0.95, 0.95, 1)
    radius = dp(20)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_once(self._bind_input, 0)

    def _bind_input(self, dt):
        inp = self.ids.get('input')
        if inp is None:
            return
        if inp.text != self.text:
            inp.text = self.text
        inp.bind(text=self._on_input_text)

    def _on_input_text(self, instance, value):
        if self.text != value:
            self.text = value


class SettingsPopup(Popup):
    current_host = ''
    current_port = DEFAULT_PORT

    def __init__(self, current_host, current_port, on_save=None, **kwargs):
        super().__init__(**kwargs)
        self.current_host = current_host
        self.current_port = current_port
        self._on_save = on_save
        try:
            self.ids.host_input.text = current_host
            self.ids.port_input.text = str(current_port)
        except Exception as e:
            Logger.error(f'SettingsPopup init: {e}')

    def save(self):
        try:
            host = self.ids.host_input.text.strip() or CURRENT_HOST
            try:
                port = int(self.ids.port_input.text.strip() or CURRENT_PORT)
            except ValueError:
                port = CURRENT_PORT
            set_server(host, port)
            if self._on_save:
                self._on_save(host, port)
            self.dismiss()
        except Exception as e:
            Logger.error(f'save settings: {e}')
            show_error(str(e), title='Settings error')


class KeyboardRoot(BoxLayout):
    sender = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._last_text = ''
        self._layout_state = None
        Clock.schedule_once(self._bind_all, 0)

    def _bind_all(self, dt):
        ti = self.ids.get('live_input')
        if ti is not None:
            ti.bind(text=self._on_live_text_changed)

        btn_en = self.ids.get('btn_en')
        if btn_en is not None:
            btn_en._on_press_cb = lambda: self.set_layout('en')

        btn_ru = self.ids.get('btn_ru')
        if btn_ru is not None:
            btn_ru._on_press_cb = lambda: self.set_layout('ru')

        btn_settings = self.ids.get('btn_settings')
        if btn_settings is not None:
            btn_settings._on_press_cb = self.open_settings

        for name, key in (
            ('btn_enter', 'KEY_ENTER'),
            ('btn_backspace', 'KEY_BACKSPACE'),
            ('btn_tab', 'KEY_TAB'),
            ('btn_esc', 'KEY_ESC'),
        ):
            btn = self.ids.get(name)
            if btn is not None:
                btn._on_press_cb = (lambda k=key: self.send_key(k))

        btn_back = self.ids.get('btn_back')
        if btn_back is not None:
            btn_back.bind(on_release=lambda *_: self.go_back())

        if self.sender is not None:
            self.sender.fetch_layout()

    def _on_live_text_changed(self, instance, value):
        cur = value or ''
        prev = self._last_text or ''

        if len(cur) < len(prev):
            n = len(prev) - len(cur)
            self.send('/backspace', {'count': n})
        else:
            added = cur[len(prev):]
            if added:
                self.send('/type', {'text': added})

        self._last_text = cur

    def send(self, endpoint, payload):
        if self.sender is not None:
            self.sender.send(endpoint, payload)

    def send_key(self, combo):
        self.send('/key', {'combo': combo})

    def set_layout(self, layout):
        self.send('/layout', {'layout': layout})

    def on_layout_update(self, layout, switched=False):
        self._layout_state = layout
        self._refresh_layout_buttons()

    def on_layout_from_server(self, layout):
        self._layout_state = layout
        self._refresh_layout_buttons()

    def _refresh_layout_buttons(self):
        for name, state in (('btn_en', 'en'), ('btn_ru', 'ru')):
            btn = self.ids.get(name)
            if btn is None:
                continue
            btn.state = 'down' if self._layout_state == state else 'normal'

    def go_back(self):
        try:
            app = App.get_running_app()
            if app is not None and hasattr(app, 'root'):
                sm = app.root
                if sm is not None and sm.has_screen('main'):
                    sm.current = 'main'
        except Exception as e:
            Logger.error(f'go_back: {e}')

    def open_settings(self):
        try:
            SettingsPopup(
                current_host=CURRENT_HOST,
                current_port=CURRENT_PORT,
                on_save=lambda h, p: set_server(h, p),
            ).open()
        except Exception as e:
            Logger.error(f'open settings: {e}')
            show_error(str(e), title='Settings error')


def _load_keyboard_kv():
    for path in ("keyboard.kv", "kv/keyboard.kv", "screens/keyboard.kv"):
        if exists(path):
            try:
                Builder.load_file(path)
                Logger.info(f'keyboard: loaded kv {path}')
            except Exception as e:
                Logger.error(f'keyboard.kv load error {path}: {e}')
            return


def create_keyboard_screen(name="keyboard"):
    _load_keyboard_kv()

    sender = HttpSender(
        base_url_provider=_base_url,
        on_error=_keyboard_http_error,
    )

    scr = Screen(name=name)
    scr.sender = sender

    root = KeyboardRoot()
    root.sender = sender

    sender._on_layout = root.on_layout_from_server

    scr.add_widget(root)
    return scr


def _keyboard_http_error(err):
    Logger.warning(f'Keyboard HTTP error: {err}')
    show_error(err, title='Connection error', duration=2.5)


def stop_keyboard_screen(scr):
    try:
        sender = getattr(scr, 'sender', None)
        if sender:
            sender.stop()
    except Exception as e:
        Logger.error(f'stop_keyboard_screen: {e}')
