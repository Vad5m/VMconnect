import socket
import warnings
import time
from threading import Lock
from collections import deque

warnings.filterwarnings('ignore')

try:
    from pynput.mouse import Controller, Button
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    Controller = None
    Button = None

from flask import Flask, request, jsonify
from werkzeug.serving import WSGIRequestHandler

MOUSE_ENABLED = True

mouse = None
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


def init_pynput():
    global mouse
    if not PYNPUT_AVAILABLE:
        return False
    try:
        mouse = Controller()
        return True
    except Exception:
        return False


def is_available():
    return mouse is not None


def _move_worker():
    from threading import Thread
    last_move = 0.0
    while True:
        try:
            if not mouse:
                time.sleep(0.1)
                continue
            now = time.time()
            if move_queue and (now - last_move) >= 0.004:
                with mouse_lock:
                    if move_queue:
                        dx, dy = move_queue.popleft()
                    else:
                        dx = dy = 0
                if dx or dy:
                    mouse.move(int(dx), int(dy))
                last_move = now
                continue
            if scroll_queue:
                with mouse_lock:
                    if scroll_queue:
                        delta = scroll_queue.popleft()
                    else:
                        delta = 0
                if delta:
                    mouse.scroll(0, int(delta))
                continue
            time.sleep(0.001)
        except Exception:
            time.sleep(0.1)


def start_worker():
    global _worker_started
    if _worker_started:
        return
    from threading import Thread
    worker_thread = Thread(target=_move_worker, daemon=True)
    worker_thread.start()
    _worker_started = True


def move(dx, dy):
    if mouse and (dx != 0 or dy != 0):
        with mouse_lock:
            move_queue.append((dx, dy))


def scroll(delta):
    if mouse and delta != 0:
        with mouse_lock:
            scroll_queue.append(delta)


def click_left():
    if mouse:
        mouse.click(Button.left)


def click_right():
    if mouse:
        mouse.click(Button.right)


def click_middle():
    if mouse:
        mouse.click(Button.middle)


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
    if not mouse:
        return {'status': 'error', 'message': 'Mouse device not available'}, 503
    move(dx, dy)
    return {'status': 'ok'}, 200


def handle_scroll(payload):
    if not MOUSE_ENABLED:
        return {'status': 'disabled', 'message': 'Mouse module disabled'}, 200
    delta = (payload or {}).get('delta', 0)
    if not mouse:
        return {'status': 'error', 'message': 'Mouse device not available'}, 503
    scroll(delta)
    return {'status': 'ok'}, 200


def handle_click(payload):
    if not MOUSE_ENABLED:
        return {'status': 'disabled', 'message': 'Mouse module disabled'}, 200
    button = (payload or {}).get('button', 'left')
    if not mouse:
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
    init_pynput()
    start_worker()
    ip = get_local_ip()
    print(f"{ip}:{PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False,
            threaded=True, request_handler=SilentHandler)


if __name__ == '__main__':
    main()
