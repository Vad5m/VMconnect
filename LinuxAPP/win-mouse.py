import socket
import warnings
import time

warnings.filterwarnings('ignore')

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    pyautogui = None

from flask import Flask, request, jsonify

MOUSE_ENABLED = True

app = Flask(__name__)


def enable():
    global MOUSE_ENABLED
    MOUSE_ENABLED = True
    return MOUSE_ENABLED


def disable():
    global MOUSE_ENABLED
    MOUSE_ENABLED = False
    return MOUSE_ENABLED


def is_available():
    return PYAUTOGUI_AVAILABLE and pyautogui is not None


def handle_move(payload):
    if not MOUSE_ENABLED:
        return {'status': 'disabled', 'message': 'Mouse module disabled'}, 200
    dx = (payload or {}).get('dx', 0)
    dy = (payload or {}).get('dy', 0)
    if not is_available():
        return {'status': 'error', 'message': 'Mouse device not available'}, 503
    if dx or dy:
        pyautogui.moveRel(int(dx), int(dy), duration=0)
        time.sleep(0.01)
    return {'status': 'ok'}, 200


def handle_scroll(payload):
    if not MOUSE_ENABLED:
        return {'status': 'disabled', 'message': 'Mouse module disabled'}, 200
    delta = (payload or {}).get('delta', 0)
    if not is_available():
        return {'status': 'error', 'message': 'Mouse device not available'}, 503
    if delta:
        pyautogui.scroll(int(delta))
    return {'status': 'ok'}, 200


def handle_click(payload):
    if not MOUSE_ENABLED:
        return {'status': 'disabled', 'message': 'Mouse module disabled'}, 200
    button = (payload or {}).get('button', 'left')
    if not is_available():
        return {'status': 'error', 'message': 'Mouse device not available'}, 503
    pyautogui.click(button=button)
    return {'status': 'ok'}, 200


@app.route('/')
def index():
    return (
        "<h1>Virtual Mouse Server (PyAutoGUI)</h1>"
        f"<p>MOUSE_ENABLED: {MOUSE_ENABLED}</p>"
        f"<p>Mouse device: {'OK' if is_available() else 'NOT AVAILABLE'}</p>"
    )


@app.route('/test_move')
def test_move():
    print("[LOG] GET /test_move")
    if not is_available():
        return "Mouse NOT AVAILABLE", 503
    pyautogui.moveRel(50, 50, duration=0.2)
    return "Moved 50px right and down"


@app.route('/move')
def move_get():
    dx = int(request.args.get('dx', 0))
    dy = int(request.args.get('dy', 0))
    print(f"[LOG] GET /move dx={dx} dy={dy}")
    if not is_available():
        return "Mouse NOT AVAILABLE", 503
    if dx or dy:
        pyautogui.moveRel(dx, dy, duration=0)
        time.sleep(0.01)
    return f"Moved dx={dx}, dy={dy}"


@app.route('/click_get')
def click_get():
    button = request.args.get('button', 'left')
    print(f"[LOG] GET /click_get button={button}")
    if not is_available():
        return "Mouse NOT AVAILABLE", 503
    pyautogui.click(button=button)
    return f"Clicked {button}"


@app.route('/scroll_get')
def scroll_get():
    delta = int(request.args.get('delta', 0))
    print(f"[LOG] GET /scroll_get delta={delta}")
    if not is_available():
        return "Mouse NOT AVAILABLE", 503
    if delta:
        pyautogui.scroll(delta)
    return f"Scrolled {delta}"


@app.route('/mouse/move', methods=['POST'])
def mouse_move():
    payload = request.get_json(silent=True) or {}
    print(f"[LOG] POST /mouse/move payload={payload}")
    result, status = handle_move(payload)
    return jsonify(result), status


@app.route('/mouse/scroll', methods=['POST'])
def mouse_scroll():
    payload = request.get_json(silent=True) or {}
    print(f"[LOG] POST /mouse/scroll payload={payload}")
    result, status = handle_scroll(payload)
    return jsonify(result), status


@app.route('/mouse/click', methods=['POST'])
def mouse_click():
    payload = request.get_json(silent=True) or {}
    print(f"[LOG] POST /mouse/click payload={payload}")
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
    ip = get_local_ip()
    print(f"[LOG] Server starting on {ip}:{PORT}")
    print(f"[LOG] Mouse available: {is_available()}")
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False,
            threaded=True)


if __name__ == '__main__':
    main()