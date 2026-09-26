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

MOUSE_ENABLED = True

device = None
mouse_lock = Lock()
move_queue = deque(maxlen=1000)
scroll_queue = deque(maxlen=100)
_worker_started = False


def enable():
    global MOUSE_ENABLED
    MOUSE_ENABLED = True
    return MOUSE_ENABLED


def disable():
    global MOUSE_ENABLED
    MOUSE_ENABLED = False
    return MOUSE_ENABLED


def init_uinput():
    global device
    if not UINPUT_AVAILABLE:
        return False
    try:
        if not os.path.exists('/dev/uinput'):
            return False
        if not os.access('/dev/uinput', os.W_OK):
            return False
        device = uinput.Device([
            uinput.REL_X,
            uinput.REL_Y,
            uinput.REL_WHEEL,
            uinput.BTN_LEFT,
            uinput.BTN_RIGHT,
            uinput.BTN_MIDDLE
        ])
        return True
    except Exception:
        return False


def is_available():
    return device is not None


def _move_worker():
    global device
    last_move = 0.0
    while True:
        try:
            if not device:
                time.sleep(0.1)
                continue
            now = time.time()
            if move_queue and (now - last_move) >= 0.004:
                with mouse_lock:
                    if move_queue:
                        dx, dy = move_queue.popleft()
                    else:
                        dx = dy = 0
                if dx:
                    device.emit(uinput.REL_X, int(dx))
                if dy:
                    device.emit(uinput.REL_Y, int(dy))
                last_move = now
                continue
            if scroll_queue:
                with mouse_lock:
                    if scroll_queue:
                        delta = scroll_queue.popleft()
                    else:
                        delta = 0
                if delta:
                    device.emit(uinput.REL_WHEEL, int(delta))
                continue
            time.sleep(0.001)
        except Exception:
            time.sleep(0.1)


def start_worker():
    global _worker_started
    if _worker_started:
        return
    worker_thread = Thread(target=_move_worker, daemon=True)
    worker_thread.start()
    _worker_started = True


def move(dx, dy):
    if device and (dx != 0 or dy != 0):
        with mouse_lock:
            move_queue.append((dx, dy))


def scroll(delta):
    if device and delta != 0:
        with mouse_lock:
            scroll_queue.append(delta)


def click_left():
    if device:
        device.emit(uinput.BTN_LEFT, 1)
        time.sleep(0.05)
        device.emit(uinput.BTN_LEFT, 0)


def click_right():
    if device:
        device.emit(uinput.BTN_RIGHT, 1)
        time.sleep(0.05)
        device.emit(uinput.BTN_RIGHT, 0)


def click_middle():
    if device:
        device.emit(uinput.BTN_MIDDLE, 1)
        time.sleep(0.05)
        device.emit(uinput.BTN_MIDDLE, 0)


def click(button='left'):
    if button == 'left':
        click_left()
    elif button == 'right':
        click_right()
    elif button == 'middle':
        click_middle()


def handle_move(payload):
    if not MOUSE_ENABLED:
        return {'status': 'disabled', 'message': 'Mouse module disabled'}, 200
    dx = (payload or {}).get('dx', 0)
    dy = (payload or {}).get('dy', 0)
    if not device:
        return {'status': 'error', 'message': 'Mouse device not available'}, 503
    move(dx, dy)
    return {'status': 'ok'}, 200


def handle_scroll(payload):
    if not MOUSE_ENABLED:
        return {'status': 'disabled', 'message': 'Mouse module disabled'}, 200
    delta = (payload or {}).get('delta', 0)
    if not device:
        return {'status': 'error', 'message': 'Mouse device not available'}, 503
    scroll(delta)
    return {'status': 'ok'}, 200


def handle_click(payload):
    if not MOUSE_ENABLED:
        return {'status': 'disabled', 'message': 'Mouse module disabled'}, 200
    button = (payload or {}).get('button', 'left')
    if not device:
        return {'status': 'error', 'message': 'Mouse device not available'}, 503
    click(button)
    return {'status': 'ok'}, 200


app = Flask(__name__)


class SilentHandler(WSGIRequestHandler):
    def log_request(self, code='-', size='-'):
        pass

    def log_message(self, format, *args):
        pass


@app.route('/')
def index():
    return (
        "<h1>Virtual Mouse Server</h1>"
        f"<p>MOUSE_ENABLED: {MOUSE_ENABLED}</p>"
        f"<p>Mouse device: {'OK' if is_available() else 'NOT AVAILABLE'}</p>"
    )


@app.route('/mouse/move', methods=['POST'])
def mouse_move():
    payload = request.get_json(silent=True) or {}
    result, status = handle_move(payload)
    return jsonify(result), status


@app.route('/mouse/scroll', methods=['POST'])
def mouse_scroll():
    payload = request.get_json(silent=True) or {}
    result, status = handle_scroll(payload)
    return jsonify(result), status


@app.route('/mouse/click', methods=['POST'])
def mouse_click():
    payload = request.get_json(silent=True) or {}
    result, status = handle_click(payload)
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
    PORT = 42000
    init_uinput()
    start_worker()
    ip = get_local_ip()
    print(f"{ip}:{PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False,
            threaded=True, request_handler=SilentHandler)


if __name__ == '__main__':
    main()
