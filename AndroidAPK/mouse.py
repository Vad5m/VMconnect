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
from kivy.uix.widget import Widget
from kivy.core.window import Window

DEFAULT_HOST = "192.168.1.42"
DEFAULT_PORT = 42000
API_PREFIX = '/mouse'

TAP_MAX_DURATION = 0.25
DOUBLE_TAP_WINDOW = 0.30
SCROLL_DIV = 12.0

CURRENT_HOST = DEFAULT_HOST
CURRENT_PORT = DEFAULT_PORT


def set_server(host, port=DEFAULT_PORT):
    global CURRENT_HOST, CURRENT_PORT
    CURRENT_HOST = host or DEFAULT_HOST
    CURRENT_PORT = port
    Logger.info(f'mouse: server set to {CURRENT_HOST}:{CURRENT_PORT}')


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
    def __init__(self, base_url_provider=None, on_error=None):
        self._base_url_provider = base_url_provider or _base_url
        self._on_error = on_error
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

            if endpoint == '/move':
                dx = float(payload.get('dx', 0.0))
                dy = float(payload.get('dy', 0.0))
                while True:
                    try:
                        nxt_ep, nxt_pl = self._queue.get_nowait()
                    except queue.Empty:
                        break
                    if nxt_ep == '/move':
                        dx += float(nxt_pl.get('dx', 0.0))
                        dy += float(nxt_pl.get('dy', 0.0))
                    else:
                        try:
                            self._queue.put_nowait((nxt_ep, nxt_pl))
                        except queue.Full:
                            pass
                        break
                payload = {'dx': dx, 'dy': dy}

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


class Touchpad(Widget):
    tap_max_distance = dp(15)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.on_send = None
        self.on_long_tap = None
        self._touches = {}
        self._two_finger = False
        self._last_scroll_avg_y = None
        self._scroll_accum = 0.0
        self._last_tap_time = None
        self._long_tap_event = None

    def _safe_send(self, endpoint, payload):
        try:
            if self.on_send:
                self.on_send(endpoint, payload)
        except Exception as e:
            Logger.error(f'send {endpoint}: {e}')
            show_error(f'{endpoint}: {e}', title='Send error')

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        touch.grab(self)
        self._touches[touch.uid] = {
            'start': touch.pos, 'last': touch.pos,
            'time': time.time(), 'moved': False,
        }
        if len(self._touches) == 1:
            if self.on_long_tap:
                self._long_tap_event = Clock.schedule_once(
                    lambda dt: self._fire_long_tap(touch.uid), 0.7)
        if len(self._touches) == 2:
            self._cancel_long_tap()
            for info in self._touches.values():
                info['moved'] = True
            self._two_finger = True
            ys = [i['last'][1] for i in self._touches.values()]
            self._last_scroll_avg_y = sum(ys) / len(ys)
            self._scroll_accum = 0.0
        return True

    def _fire_long_tap(self, uid):
        self._long_tap_event = None
        if uid in self._touches and not self._touches[uid]['moved']:
            if self.on_long_tap:
                try:
                    self.on_long_tap()
                except Exception as e:
                    Logger.error(f'long tap: {e}')
                    show_error(str(e), title='Settings error')

    def _cancel_long_tap(self):
        if self._long_tap_event is not None:
            self._long_tap_event.cancel()
            self._long_tap_event = None

    def on_touch_move(self, touch):
        if touch.uid not in self._touches:
            return False
        info = self._touches[touch.uid]
        prev_x, prev_y = info['last']

        if self._two_finger and len(self._touches) >= 2:
            info['last'] = touch.pos
            ys = [i['last'][1] for i in self._touches.values()]
            avg_y = sum(ys) / len(ys)
            if self._last_scroll_avg_y is not None:
                delta = -(avg_y - self._last_scroll_avg_y) / SCROLL_DIV
                self._scroll_accum += delta
                whole = int(self._scroll_accum)
                if whole != 0:
                    self._scroll_accum -= whole
                    self._safe_send('/scroll', {'delta': whole})
                self._last_scroll_avg_y = avg_y
            return True

        if len(self._touches) == 1:
            sx, sy = info['start']
            if (abs(touch.x - sx) > self.tap_max_distance or
                    abs(touch.y - sy) > self.tap_max_distance):
                info['moved'] = True
                self._cancel_long_tap()

            dx = touch.x - prev_x
            dy = touch.y - prev_y
            info['last'] = touch.pos
            if dx != 0 or dy != 0:
                self._safe_send('/move', {'dx': dx, 'dy': -dy})
        else:
            info['last'] = touch.pos
        return True

    def on_touch_up(self, touch):
        if touch.uid not in self._touches:
            return False
        touch.ungrab(self)
        info = self._touches.pop(touch.uid)
        self._cancel_long_tap()

        duration = time.time() - info['time']
        was_two_finger = self._two_finger

        if len(self._touches) < 2:
            self._two_finger = False
            self._last_scroll_avg_y = None
            self._scroll_accum = 0.0

        if (not was_two_finger and not info['moved']
                and duration < TAP_MAX_DURATION):
            now = time.time()
            if (self._last_tap_time is not None
                    and now - self._last_tap_time < DOUBLE_TAP_WINDOW):
                self._last_tap_time = None
                self._safe_send('/click', {'button': 'right'})
            else:
                self._last_tap_time = now
                Clock.schedule_once(
                    lambda dt, t=now: self._maybe_left_click(t),
                    DOUBLE_TAP_WINDOW,
                )
        return True

    def _maybe_left_click(self, tap_time):
        if self._last_tap_time == tap_time:
            self._last_tap_time = None
            self._safe_send('/click', {'button': 'left'})


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


class MouseRoot(BoxLayout):
    sender = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_once(self._bind_all, 0)

    def _bind_all(self, dt):
        touchpad = self.ids.get('touchpad')
        if touchpad is not None:
            touchpad.on_send = self.send
            touchpad.on_long_tap = self.open_settings

        btn_left = self.ids.get('btn_left')
        if btn_left is not None:
            btn_left._on_press_cb = lambda: self.send_click('left')

        btn_right = self.ids.get('btn_right')
        if btn_right is not None:
            btn_right._on_press_cb = lambda: self.send_click('right')

        btn_back = self.ids.get('btn_back')
        if btn_back is not None:
            btn_back.bind(on_release=lambda *_: self.go_back())

    def go_back(self):
        try:
            app = App.get_running_app()
            if app is not None and hasattr(app, 'root'):
                sm = app.root
                if sm is not None and sm.has_screen('main'):
                    sm.current = 'main'
        except Exception as e:
            Logger.error(f'go_back: {e}')

    def send(self, endpoint, payload):
        if self.sender is not None:
            self.sender.send(endpoint, payload)

    def send_click(self, button):
        self.send('/click', {'button': button})

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


def _load_mouse_kv():
    for path in ("mouse.kv", "kv/mouse.kv", "screens/mouse.kv"):
        if exists(path):
            try:
                Builder.load_file(path)
                Logger.info(f'mouse: loaded kv {path}')
            except Exception as e:
                Logger.error(f'mouse.kv load error {path}: {e}')
            return


def create_mouse_screen(name="mouse"):
    _load_mouse_kv()

    sender = HttpSender(base_url_provider=_base_url,
                        on_error=_mouse_http_error)

    scr = Screen(name=name)
    scr.sender = sender

    root = MouseRoot()
    root.sender = sender
    scr.add_widget(root)
    return scr


def _mouse_http_error(err):
    Logger.warning(f'HTTP error: {err}')
    show_error(err, title='Connection error', duration=2.5)


def stop_mouse_screen(scr):
    try:
        sender = getattr(scr, 'sender', None)
        if sender:
            sender.stop()
    except Exception as e:
        Logger.error(f'stop_mouse_screen: {e}')
