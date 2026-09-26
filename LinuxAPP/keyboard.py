import os
import time
import socket
import warnings
from threading import Thread, Lock
from collections import deque


warnings.filterwarnings('ignore')

try:
    import uinput
    UINPUT_AVAILABLE = True
except ImportError:
    UINPUT_AVAILABLE = False
    uinput = None

from flask import Flask, request, jsonify
from werkzeug.serving import WSGIRequestHandler

KEYBOARD_ENABLED = True

device = None
keyboard_lock = Lock()
event_queue = deque(maxlen=2000)
_worker_started = False
_current_layout = None  # 'en' | 'ru' | None


# ============================================================
#  Управление модулем
# ============================================================

def enable():
    global KEYBOARD_ENABLED
    KEYBOARD_ENABLED = True
    return KEYBOARD_ENABLED


def disable():
    global KEYBOARD_ENABLED
    KEYBOARD_ENABLED = False
    return KEYBOARD_ENABLED


# ============================================================
#  Инициализация uinput
# ============================================================

KEY_EVENTS = (
    uinput.KEY_A, uinput.KEY_B, uinput.KEY_C, uinput.KEY_D,
    uinput.KEY_E, uinput.KEY_F, uinput.KEY_G, uinput.KEY_H,
    uinput.KEY_I, uinput.KEY_J, uinput.KEY_K, uinput.KEY_L,
    uinput.KEY_M, uinput.KEY_N, uinput.KEY_O, uinput.KEY_P,
    uinput.KEY_Q, uinput.KEY_R, uinput.KEY_S, uinput.KEY_T,
    uinput.KEY_U, uinput.KEY_V, uinput.KEY_W, uinput.KEY_X,
    uinput.KEY_Y, uinput.KEY_Z,
    uinput.KEY_1, uinput.KEY_2, uinput.KEY_3, uinput.KEY_4,
    uinput.KEY_5, uinput.KEY_6, uinput.KEY_7, uinput.KEY_8,
    uinput.KEY_9, uinput.KEY_0,
    uinput.KEY_ENTER, uinput.KEY_BACKSPACE, uinput.KEY_TAB,
    uinput.KEY_LEFTMETA, uinput.KEY_RIGHTMETA,
    uinput.KEY_LEFTALT, uinput.KEY_RIGHTALT,
    uinput.KEY_LEFTCTRL, uinput.KEY_RIGHTCTRL,
    uinput.KEY_SPACE,
    uinput.KEY_LEFTSHIFT, uinput.KEY_RIGHTSHIFT,
    uinput.KEY_DOT, uinput.KEY_COMMA,
    uinput.KEY_MINUS, uinput.KEY_EQUAL, uinput.KEY_SLASH,
    uinput.KEY_SEMICOLON, uinput.KEY_APOSTROPHE,
    uinput.KEY_LEFTBRACE, uinput.KEY_RIGHTBRACE,
    uinput.KEY_GRAVE, uinput.KEY_BACKSLASH,
    uinput.KEY_ESC, uinput.KEY_DELETE, uinput.KEY_INSERT,
    uinput.KEY_HOME, uinput.KEY_END, uinput.KEY_PAGEUP, uinput.KEY_PAGEDOWN,
    uinput.KEY_UP, uinput.KEY_DOWN, uinput.KEY_LEFT, uinput.KEY_RIGHT,
    uinput.KEY_CAPSLOCK, uinput.KEY_F1, uinput.KEY_F2, uinput.KEY_F3,
    uinput.KEY_F4, uinput.KEY_F5, uinput.KEY_F6, uinput.KEY_F7,
    uinput.KEY_F8, uinput.KEY_F9, uinput.KEY_F10, uinput.KEY_F11, uinput.KEY_F12,
)


def init_uinput():
    global device
    if not UINPUT_AVAILABLE:
        return False
    try:
        if not os.path.exists('/dev/uinput'):
            return False
        if not os.access('/dev/uinput', os.W_OK):
            return False
        device = uinput.Device(KEY_EVENTS)
        time.sleep(1)  # даём ядру поднять устройство
        return True
    except Exception:
        return False


def is_available():
    return device is not None


# ============================================================
#  Очередь событий + воркер
# ============================================================

def _enqueue(kind, **kwargs):
    """kind: 'click' | 'combo' | 'press' | 'release'"""
    if not device:
        return
    with keyboard_lock:
        event_queue.append((kind, kwargs))


def _worker():
    global device
    while True:
        try:
            if not device:
                time.sleep(0.1)
                continue

            with keyboard_lock:
                if event_queue:
                    kind, kw = event_queue.popleft()
                else:
                    kind, kw = None, None

            if kind is None:
                time.sleep(0.001)
                continue

            if kind == 'click':
                device.emit_click(kw['key'])
            elif kind == 'combo':
                device.emit_combo(kw['keys'])
            elif kind == 'press':
                device.emit(kw['key'], 1)
            elif kind == 'release':
                device.emit(kw['key'], 0)

            # небольшая пауза, чтобы ОС успевала обрабатывать
            time.sleep(0.008)
        except Exception:
            time.sleep(0.1)


def start_worker():
    global _worker_started
    if _worker_started:
        return
    t = Thread(target=_worker, daemon=True)
    t.start()
    _worker_started = True


# ============================================================
#  Публичные функции ввода
# ============================================================

KEYMAP = {
    'a': (uinput.KEY_A, False), 'b': (uinput.KEY_B, False),
    'c': (uinput.KEY_C, False), 'd': (uinput.KEY_D, False),
    'e': (uinput.KEY_E, False), 'f': (uinput.KEY_F, False),
    'g': (uinput.KEY_G, False), 'h': (uinput.KEY_H, False),
    'i': (uinput.KEY_I, False), 'j': (uinput.KEY_J, False),
    'k': (uinput.KEY_K, False), 'l': (uinput.KEY_L, False),
    'm': (uinput.KEY_M, False), 'n': (uinput.KEY_N, False),
    'o': (uinput.KEY_O, False), 'p': (uinput.KEY_P, False),
    'q': (uinput.KEY_Q, False), 'r': (uinput.KEY_R, False),
    's': (uinput.KEY_S, False), 't': (uinput.KEY_T, False),
    'u': (uinput.KEY_U, False), 'v': (uinput.KEY_V, False),
    'w': (uinput.KEY_W, False), 'x': (uinput.KEY_X, False),
    'y': (uinput.KEY_Y, False), 'z': (uinput.KEY_Z, False),
    'A': (uinput.KEY_A, True),  'B': (uinput.KEY_B, True),
    'C': (uinput.KEY_C, True),  'D': (uinput.KEY_D, True),
    'E': (uinput.KEY_E, True),  'F': (uinput.KEY_F, True),
    'G': (uinput.KEY_G, True),  'H': (uinput.KEY_H, True),
    'I': (uinput.KEY_I, True),  'J': (uinput.KEY_J, True),
    'K': (uinput.KEY_K, True),  'L': (uinput.KEY_L, True),
    'M': (uinput.KEY_M, True),  'N': (uinput.KEY_N, True),
    'O': (uinput.KEY_O, True),  'P': (uinput.KEY_P, True),
    'Q': (uinput.KEY_Q, True),  'R': (uinput.KEY_R, True),
    'S': (uinput.KEY_S, True),  'T': (uinput.KEY_T, True),
    'U': (uinput.KEY_U, True),  'V': (uinput.KEY_V, True),
    'W': (uinput.KEY_W, True),  'X': (uinput.KEY_X, True),
    'Y': (uinput.KEY_Y, True),  'Z': (uinput.KEY_Z, True),

    '0': (uinput.KEY_0, False), '1': (uinput.KEY_1, False),
    '2': (uinput.KEY_2, False), '3': (uinput.KEY_3, False),
    '4': (uinput.KEY_4, False), '5': (uinput.KEY_5, False),
    '6': (uinput.KEY_6, False), '7': (uinput.KEY_7, False),
    '8': (uinput.KEY_8, False), '9': (uinput.KEY_9, False),

    ' ': (uinput.KEY_SPACE, False),
    '.': (uinput.KEY_DOT, False),
    ',': (uinput.KEY_COMMA, False),
    '-': (uinput.KEY_MINUS, False),
    '=': (uinput.KEY_EQUAL, False),
    '/': (uinput.KEY_SLASH, False),
    ';': (uinput.KEY_SEMICOLON, False),
    "'": (uinput.KEY_APOSTROPHE, False),
    '[': (uinput.KEY_LEFTBRACE, False),
    ']': (uinput.KEY_RIGHTBRACE, False),
    '`': (uinput.KEY_GRAVE, False),
    '\\': (uinput.KEY_BACKSLASH, False),
    '\n': (uinput.KEY_ENTER, False),
    '\t': (uinput.KEY_TAB, False),

    '!': (uinput.KEY_1, True),
    '@': (uinput.KEY_2, True),
    '#': (uinput.KEY_3, True),
    '$': (uinput.KEY_4, True),
    '%': (uinput.KEY_5, True),
    '^': (uinput.KEY_6, True),
    '&': (uinput.KEY_7, True),
    '*': (uinput.KEY_8, True),
    '(': (uinput.KEY_9, True),
    ')': (uinput.KEY_0, True),
    '_': (uinput.KEY_MINUS, True),
    '+': (uinput.KEY_EQUAL, True),
    ':': (uinput.KEY_SEMICOLON, True),
    '"': (uinput.KEY_APOSTROPHE, True),
    '{': (uinput.KEY_LEFTBRACE, True),
    '}': (uinput.KEY_RIGHTBRACE, True),
    '~': (uinput.KEY_GRAVE, True),
    '|': (uinput.KEY_BACKSLASH, True),
    '<': (uinput.KEY_COMMA, True),
    '>': (uinput.KEY_DOT, True),
    '?': (uinput.KEY_SLASH, True),

    'й': (uinput.KEY_Q, False), 'ц': (uinput.KEY_W, False),
    'у': (uinput.KEY_E, False), 'к': (uinput.KEY_R, False),
    'е': (uinput.KEY_T, False), 'н': (uinput.KEY_Y, False),
    'г': (uinput.KEY_U, False), 'ш': (uinput.KEY_I, False),
    'щ': (uinput.KEY_O, False), 'з': (uinput.KEY_P, False),
    'х': (uinput.KEY_LEFTBRACE, False), 'ъ': (uinput.KEY_RIGHTBRACE, False),
    'ф': (uinput.KEY_A, False), 'ы': (uinput.KEY_S, False),
    'в': (uinput.KEY_D, False), 'а': (uinput.KEY_F, False),
    'п': (uinput.KEY_G, False), 'р': (uinput.KEY_H, False),
    'о': (uinput.KEY_J, False), 'л': (uinput.KEY_K, False),
    'д': (uinput.KEY_L, False), 'ж': (uinput.KEY_SEMICOLON, False),
    'э': (uinput.KEY_APOSTROPHE, False),
    'я': (uinput.KEY_Z, False), 'ч': (uinput.KEY_X, False),
    'с': (uinput.KEY_C, False), 'м': (uinput.KEY_V, False),
    'и': (uinput.KEY_B, False), 'т': (uinput.KEY_N, False),
    'ь': (uinput.KEY_M, False), 'б': (uinput.KEY_COMMA, False),
    'ю': (uinput.KEY_DOT, False), 'ё': (uinput.KEY_GRAVE, False),

    'Й': (uinput.KEY_Q, True), 'Ц': (uinput.KEY_W, True),
    'У': (uinput.KEY_E, True), 'К': (uinput.KEY_R, True),
    'Е': (uinput.KEY_T, True), 'Н': (uinput.KEY_Y, True),
    'Г': (uinput.KEY_U, True), 'Ш': (uinput.KEY_I, True),
    'Щ': (uinput.KEY_O, True), 'З': (uinput.KEY_P, True),
    'Х': (uinput.KEY_LEFTBRACE, True), 'Ъ': (uinput.KEY_RIGHTBRACE, True),
    'Ф': (uinput.KEY_A, True), 'Ы': (uinput.KEY_S, True),
    'В': (uinput.KEY_D, True), 'А': (uinput.KEY_F, True),
    'П': (uinput.KEY_G, True), 'Р': (uinput.KEY_H, True),
    'О': (uinput.KEY_J, True), 'Л': (uinput.KEY_K, True),
    'Д': (uinput.KEY_L, True), 'Ж': (uinput.KEY_SEMICOLON, True),
    'Э': (uinput.KEY_APOSTROPHE, True),
    'Я': (uinput.KEY_Z, True), 'Ч': (uinput.KEY_X, True),
    'С': (uinput.KEY_C, True), 'М': (uinput.KEY_V, True),
    'И': (uinput.KEY_B, True), 'Т': (uinput.KEY_N, True),
    'Ь': (uinput.KEY_M, True), 'Б': (uinput.KEY_COMMA, True),
    'Ю': (uinput.KEY_DOT, True), 'Ё': (uinput.KEY_GRAVE, True),
}


def type_text(text):
    """Ставит в очередь печать строки (без переключения раскладки)."""
    if not device or not isinstance(text, str):
        return 0
    sent = 0
    for ch in text:
        if ch not in KEYMAP:
            continue
        key, need_shift = KEYMAP[ch]
        if need_shift:
            _enqueue('combo', keys=[uinput.KEY_LEFTSHIFT, key])
        else:
            _enqueue('click', key=key)
        sent += 1
    return sent


def press_key(key):
    if device:
        _enqueue('press', key=key)


def release_key(key):
    if device:
        _enqueue('release', key=key)


def click_key(key):
    if device:
        _enqueue('click', key=key)


def combo(keys):
    if device and keys:
        _enqueue('combo', keys=keys)


def backspace(n=1):
    if not device:
        return 0
    n = max(0, min(int(n), 200))
    for _ in range(n):
        _enqueue('click', key=uinput.KEY_BACKSPACE)
    return n


def resolve_key(name):
    """'KEY_ENTER' -> uinput.KEY_ENTER, или None."""
    return getattr(uinput, name, None) if uinput else None


# ============================================================
#  Раскладка
# ============================================================

def _switch_layout():
    global _current_layout
    combo([uinput.KEY_LEFTMETA, uinput.KEY_SPACE])
    if _current_layout == 'en':
        _current_layout = 'ru'
    elif _current_layout == 'ru':
        _current_layout = 'en'
    else:
        _current_layout = 'en'


def set_layout(target):
    global _current_layout
    if target not in ('en', 'ru'):
        return _current_layout

    if _current_layout is None:
        _current_layout = 'en'

    if _current_layout != target:
        _switch_layout()

    return _current_layout


def get_layout():
    return _current_layout


# ============================================================
#  HTTP-обработчики (по стилю mouse.py)
# ============================================================

def handle_type(payload):
    if not KEYBOARD_ENABLED:
        return {'status': 'disabled', 'message': 'Keyboard module disabled'}, 200
    if not device:
        return {'status': 'error', 'message': 'Keyboard device not available'}, 503
    text = (payload or {}).get('text', '')
    if not isinstance(text, str):
        return {'status': 'error', 'message': 'text must be string'}, 400
    sent = type_text(text)
    return {'status': 'ok', 'sent': sent}, 200


def handle_key(payload):
    if not KEYBOARD_ENABLED:
        return {'status': 'disabled', 'message': 'Keyboard module disabled'}, 200
    if not device:
        return {'status': 'error', 'message': 'Keyboard device not available'}, 503

    combo_str = (payload or {}).get('combo', '')
    if not isinstance(combo_str, str) or not combo_str:
        return {'status': 'error', 'message': 'combo required'}, 400

    keys = []
    for name in combo_str.split('+'):
        name = name.strip()
        if not name:
            continue
        code = resolve_key(name)
        if code is None:
            return {'status': 'error', 'message': f'unknown key: {name}'}, 400
        keys.append(code)

    if keys:
        combo(keys)
    return {'status': 'ok', 'sent': combo_str}, 200


def handle_backspace(payload):
    if not KEYBOARD_ENABLED:
        return {'status': 'disabled', 'message': 'Keyboard module disabled'}, 200
    if not device:
        return {'status': 'error', 'message': 'Keyboard device not available'}, 503
    try:
        n = int((payload or {}).get('count', 1))
    except (TypeError, ValueError):
        n = 1
    sent = backspace(n)
    return {'status': 'ok', 'sent': sent}, 200


def handle_layout(payload, method):
    if not KEYBOARD_ENABLED:
        return {'status': 'disabled', 'message': 'Keyboard module disabled'}, 200
    if not device:
        return {'status': 'error', 'message': 'Keyboard device not available'}, 503

    if method == 'GET':
        return {'layout': get_layout()}, 200

    target = (payload or {}).get('layout', '')
    if target not in ('en', 'ru'):
        return {'status': 'error', 'message': 'layout must be en or ru'}, 400
    before = get_layout()
    set_layout(target)
    after = get_layout()
    return {'layout': after, 'switched': before != after}, 200


# ============================================================
#  Flask
# ============================================================

app = Flask(__name__)


class SilentHandler(WSGIRequestHandler):
    def log_request(self, code='-', size='-'):
        pass

    def log_message(self, format, *args):
        pass


@app.route('/')
def index():
    return (
        "<h1>Virtual Keyboard Server</h1>"
        f"<p>KEYBOARD_ENABLED: {KEYBOARD_ENABLED}</p>"
        f"<p>Keyboard device: {'OK' if is_available() else 'NOT AVAILABLE'}</p>"
        f"<p>Layout (server view): {_current_layout or '?'}</p>"
    )


@app.route('/keyboard/type', methods=['POST'])
def keyboard_type():
    payload = request.get_json(silent=True) or {}
    result, status = handle_type(payload)
    return jsonify(result), status


@app.route('/keyboard/key', methods=['POST'])
def keyboard_key():
    payload = request.get_json(silent=True) or {}
    result, status = handle_key(payload)
    return jsonify(result), status


@app.route('/keyboard/backspace', methods=['POST'])
def keyboard_backspace():
    payload = request.get_json(silent=True) or {}
    result, status = handle_backspace(payload)
    return jsonify(result), status


@app.route('/keyboard/layout', methods=['GET', 'POST'])
def keyboard_layout():
    payload = request.get_json(silent=True) or {}
    result, status = handle_layout(payload, request.method)
    return jsonify(result), status


# ============================================================
#  main — как в mouse.py
# ============================================================

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def main():
    PORT = 42001
    init_uinput()
    start_worker()
    ip = get_local_ip()
    print(f"{ip}:{PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False,
            threaded=True, request_handler=SilentHandler)


if __name__ == '__main__':
    main()
