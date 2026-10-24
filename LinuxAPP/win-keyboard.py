import socket
import warnings
from threading import Thread, Lock
from collections import deque

warnings.filterwarnings('ignore')

from pynput.keyboard import Controller, Key, KeyCode

from flask import Flask, request, jsonify
from werkzeug.serving import WSGIRequestHandler

KEYBOARD_ENABLED = True

device = None
keyboard_lock = Lock()
event_queue = deque(maxlen=2000)
_worker_started = False
_current_layout = None


def enable():
    global KEYBOARD_ENABLED
    KEYBOARD_ENABLED = True
    return KEYBOARD_ENABLED


def disable():
    global KEYBOARD_ENABLED
    KEYBOARD_ENABLED = False
    return KEYBOARD_ENABLED


def init_uinput():
    global device
    try:
        device = Controller()
        return True
    except Exception:
        device = None
        return False


def is_available():
    return device is not None


def _enqueue(kind, **kwargs):
    if not device:
        return
    with keyboard_lock:
        event_queue.append((kind, kwargs))


def _worker():
    global device
    while True:
        try:
            if not device:
                device = Controller()
                continue

            with keyboard_lock:
                if event_queue:
                    kind, kw = event_queue.popleft()
                else:
                    kind, kw = None, None

            if kind is None:
                import time
                time.sleep(0.001)
                continue

            if kind == 'click':
                device.press(kw['key'])
                device.release(kw['key'])
            elif kind == 'combo':
                keys = kw['keys']
                for k in keys:
                    device.press(k)
                for k in reversed(keys):
                    device.release(k)
            elif kind == 'press':
                device.press(kw['key'])
            elif kind == 'release':
                device.release(kw['key'])

            import time
            time.sleep(0.008)
        except Exception:
            import time
            time.sleep(0.1)


def start_worker():
    global _worker_started
    if _worker_started:
        return
    t = Thread(target=_worker, daemon=True)
    t.start()
    _worker_started = True


KEYMAP = {
    'a': KeyCode.from_char('a'), 'b': KeyCode.from_char('b'),
    'c': KeyCode.from_char('c'), 'd': KeyCode.from_char('d'),
    'e': KeyCode.from_char('e'), 'f': KeyCode.from_char('f'),
    'g': KeyCode.from_char('g'), 'h': KeyCode.from_char('h'),
    'i': KeyCode.from_char('i'), 'j': KeyCode.from_char('j'),
    'k': KeyCode.from_char('k'), 'l': KeyCode.from_char('l'),
    'm': KeyCode.from_char('m'), 'n': KeyCode.from_char('n'),
    'o': KeyCode.from_char('o'), 'p': KeyCode.from_char('p'),
    'q': KeyCode.from_char('q'), 'r': KeyCode.from_char('r'),
    's': KeyCode.from_char('s'), 't': KeyCode.from_char('t'),
    'u': KeyCode.from_char('u'), 'v': KeyCode.from_char('v'),
    'w': KeyCode.from_char('w'), 'x': KeyCode.from_char('x'),
    'y': KeyCode.from_char('y'), 'z': KeyCode.from_char('z'),
    'A': KeyCode.from_char('a'), 'B': KeyCode.from_char('b'),
    'C': KeyCode.from_char('c'), 'D': KeyCode.from_char('d'),
    'E': KeyCode.from_char('e'), 'F': KeyCode.from_char('f'),
    'G': KeyCode.from_char('g'), 'H': KeyCode.from_char('h'),
    'I': KeyCode.from_char('i'), 'J': KeyCode.from_char('j'),
    'K': KeyCode.from_char('k'), 'L': KeyCode.from_char('l'),
    'M': KeyCode.from_char('m'), 'N': KeyCode.from_char('n'),
    'O': KeyCode.from_char('o'), 'P': KeyCode.from_char('p'),
    'Q': KeyCode.from_char('q'), 'R': KeyCode.from_char('r'),
    'S': KeyCode.from_char('s'), 'T': KeyCode.from_char('t'),
    'U': KeyCode.from_char('u'), 'V': KeyCode.from_char('v'),
    'W': KeyCode.from_char('w'), 'X': KeyCode.from_char('x'),
    'Y': KeyCode.from_char('y'), 'Z': KeyCode.from_char('z'),

    '0': KeyCode.from_char('0'), '1': KeyCode.from_char('1'),
    '2': KeyCode.from_char('2'), '3': KeyCode.from_char('3'),
    '4': KeyCode.from_char('4'), '5': KeyCode.from_char('5'),
    '6': KeyCode.from_char('6'), '7': KeyCode.from_char('7'),
    '8': KeyCode.from_char('8'), '9': KeyCode.from_char('9'),

    ' ': KeyCode.from_char(' '),
    '.': KeyCode.from_char('.'),
    ',': KeyCode.from_char(','),
    '-': KeyCode.from_char('-'),
    '=': KeyCode.from_char('='),
    '/': KeyCode.from_char('/'),
    ';': KeyCode.from_char(';'),
    "'": KeyCode.from_char("'"),
    '[': KeyCode.from_char('['),
    ']': KeyCode.from_char(']'),
    '`': KeyCode.from_char('`'),
    '\\': KeyCode.from_char('\\'),
    '\n': Key.enter,
    '\t': Key.tab,

    '!': KeyCode.from_char('!'),
    '@': KeyCode.from_char('@'),
    '#': KeyCode.from_char('#'),
    '$': KeyCode.from_char('$'),
    '%': KeyCode.from_char('%'),
    '^': KeyCode.from_char('^'),
    '&': KeyCode.from_char('&'),
    '*': KeyCode.from_char('*'),
    '(': KeyCode.from_char('('),
    ')': KeyCode.from_char(')'),
    '_': KeyCode.from_char('_'),
    '+': KeyCode.from_char('+'),
    ':': KeyCode.from_char(':'),
    '"': KeyCode.from_char('"'),
    '{': KeyCode.from_char('{'),
    '}': KeyCode.from_char('}'),
    '~': KeyCode.from_char('~'),
    '|': KeyCode.from_char('|'),
    '<': KeyCode.from_char('<'),
    '>': KeyCode.from_char('>'),
    '?': KeyCode.from_char('?'),

    'й': KeyCode.from_char('й'), 'ц': KeyCode.from_char('ц'),
    'у': KeyCode.from_char('у'), 'к': KeyCode.from_char('к'),
    'е': KeyCode.from_char('е'), 'н': KeyCode.from_char('н'),
    'г': KeyCode.from_char('г'), 'ш': KeyCode.from_char('ш'),
    'щ': KeyCode.from_char('щ'), 'з': KeyCode.from_char('з'),
    'х': KeyCode.from_char('х'), 'ъ': KeyCode.from_char('ъ'),
    'ф': KeyCode.from_char('ф'), 'ы': KeyCode.from_char('ы'),
    'в': KeyCode.from_char('в'), 'а': KeyCode.from_char('а'),
    'п': KeyCode.from_char('п'), 'р': KeyCode.from_char('р'),
    'о': KeyCode.from_char('о'), 'л': KeyCode.from_char('л'),
    'д': KeyCode.from_char('д'), 'ж': KeyCode.from_char('ж'),
    'э': KeyCode.from_char('э'),
    'я': KeyCode.from_char('я'), 'ч': KeyCode.from_char('ч'),
    'с': KeyCode.from_char('с'), 'м': KeyCode.from_char('м'),
    'и': KeyCode.from_char('и'), 'т': KeyCode.from_char('т'),
    'ь': KeyCode.from_char('ь'), 'б': KeyCode.from_char('б'),
    'ю': KeyCode.from_char('ю'), 'ё': KeyCode.from_char('ё'),

    'Й': KeyCode.from_char('Й'), 'Ц': KeyCode.from_char('Ц'),
    'У': KeyCode.from_char('У'), 'К': KeyCode.from_char('К'),
    'Е': KeyCode.from_char('Е'), 'Н': KeyCode.from_char('Н'),
    'Г': KeyCode.from_char('Г'), 'Ш': KeyCode.from_char('Ш'),
    'Щ': KeyCode.from_char('Щ'), 'З': KeyCode.from_char('З'),
    'Х': KeyCode.from_char('Х'), 'Ъ': KeyCode.from_char('Ъ'),
    'Ф': KeyCode.from_char('Ф'), 'Ы': KeyCode.from_char('Ы'),
    'В': KeyCode.from_char('В'), 'А': KeyCode.from_char('А'),
    'П': KeyCode.from_char('П'), 'Р': KeyCode.from_char('Р'),
    'О': KeyCode.from_char('О'), 'Л': KeyCode.from_char('Л'),
    'Д': KeyCode.from_char('Д'), 'Ж': KeyCode.from_char('Ж'),
    'Э': KeyCode.from_char('Э'),
    'Я': KeyCode.from_char('Я'), 'Ч': KeyCode.from_char('Ч'),
    'С': KeyCode.from_char('С'), 'М': KeyCode.from_char('М'),
    'И': KeyCode.from_char('И'), 'Т': KeyCode.from_char('Т'),
    'Ь': KeyCode.from_char('Ь'), 'Б': KeyCode.from_char('Б'),
    'Ю': KeyCode.from_char('Ю'), 'Ё': KeyCode.from_char('Ё'),
}


def type_text(text):
    if not device or not isinstance(text, str):
        return 0
    sent = 0
    for ch in text:
        if ch not in KEYMAP:
            continue
        key = KEYMAP[ch]
        if ch.isupper() or ch in '!@#$%^&*()_+:"{}~|<>?':
            _enqueue('combo', keys=[Key.shift, key])
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
        _enqueue('click', key=Key.backspace)
    return n


def resolve_key(name):
    if not isinstance(name, str):
        return None
    name = name.strip()
    if not name:
        return None

    aliases = {
        'KEY_SHIFT': 'shift',
        'KEY_RSHIFT': 'shift_r',
        'KEY_CTRL': 'ctrl',
        'KEY_CONTROL': 'ctrl',
        'KEY_ALT': 'alt',
        'KEY_META': 'cmd',
        'KEY_WIN': 'cmd',
        'KEY_SUPER': 'cmd',
        'KEY_RETURN': 'enter',
        'KEY_ENTER': 'enter',
        'KEY_ESCAPE': 'esc',
        'KEY_ESC': 'esc',
        'KEY_DEL': 'delete',
        'KEY_DELETE': 'delete',
        'KEY_INS': 'insert',
        'KEY_INSERT': 'insert',
        'KEY_PGUP': 'page_up',
        'KEY_PGDN': 'page_down',
        'KEY_PAGEUP': 'page_up',
        'KEY_PAGEDOWN': 'page_down',
        'KEY_SPACE': 'space',
        'KEY_TAB': 'tab',
        'KEY_BACKSPACE': 'backspace',
        'KEY_UP': 'up',
        'KEY_DOWN': 'down',
        'KEY_LEFT': 'left',
        'KEY_RIGHT': 'right',
        'KEY_HOME': 'home',
        'KEY_END': 'end',
        'KEY_CAPSLOCK': 'caps_lock',
        'KEY_F1': 'f1',
        'KEY_F2': 'f2',
        'KEY_F3': 'f3',
        'KEY_F4': 'f4',
        'KEY_F5': 'f5',
        'KEY_F6': 'f6',
        'KEY_F7': 'f7',
        'KEY_F8': 'f8',
        'KEY_F9': 'f9',
        'KEY_F10': 'f10',
        'KEY_F11': 'f11',
        'KEY_F12': 'f12',
        'KEY_LEFTSHIFT': 'shift',
        'KEY_RIGHTSHIFT': 'shift_r',
        'KEY_LEFTCTRL': 'ctrl',
        'KEY_RIGHTCTRL': 'ctrl_r',
        'KEY_LEFTALT': 'alt',
        'KEY_RIGHTALT': 'alt_r',
        'KEY_LEFTMETA': 'cmd',
        'KEY_RIGHTMETA': 'cmd_r',
    }

    if name in aliases:
        key_name = aliases[name]
        return getattr(Key, key_name, None)

    if name.startswith('KEY_'):
        key_name = name[4:].lower()
        return getattr(Key, key_name, None)

    if len(name) == 1:
        return KeyCode.from_char(name)

    key_name = name.lower()
    if hasattr(Key, key_name):
        return getattr(Key, key_name)

    return None


def _switch_layout():
    global _current_layout
    combo([Key.cmd, Key.space])
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
