import os
import time
import json
import socket
import shutil
import signal
import struct
import fcntl
import termios
import select
import pty
import threading
import warnings
import uuid
from collections import deque

warnings.filterwarnings('ignore')

import pyte

from flask import Flask, request, jsonify
from werkzeug.serving import WSGIRequestHandler, make_server


SSH_PORT = 42003
COLS = 120
ROWS = 40
FG_DEFAULT = "#c9d1d9"

PYTE_COLORS = {
    "black":         "#484f58",
    "red":           "#ff7b72",
    "green":         "#7ee787",
    "brown":         "#d29922",
    "yellow":        "#d29922",
    "blue":          "#58a6ff",
    "magenta":       "#d2a8ff",
    "cyan":          "#79c0ff",
    "white":         "#c9d1d9",
    "brightblack":   "#6e7681",
    "brightred":     "#ffa198",
    "brightgreen":   "#aff5b4",
    "brightyellow":  "#e3b341",
    "brightblue":    "#79c0ff",
    "brightmagenta": "#d2a8ff",
    "brightcyan":    "#a5d6ff",
    "brightwhite":   "#f0f6fc",
}


def detect_shell():
    for name in ("fish", "bash", "sh"):
        path = shutil.which(name)
        if path:
            return path, name
    return "/bin/sh", "sh"


SHELL_PATH, SHELL_NAME = detect_shell()


def color_to_hex(c):
    if not c:
        return FG_DEFAULT
    if isinstance(c, str) and c.startswith("#"):
        return c
    if isinstance(c, str):
        return PYTE_COLORS.get(c.lower(), FG_DEFAULT)
    return FG_DEFAULT


class TerminalSession:
    def __init__(self):
        self.master_fd = None
        self.pid = None
        self.screen = pyte.Screen(COLS, ROWS)
        self.stream = pyte.Stream(self.screen)
        self.lock = threading.Lock()
        self.dirty = True
        self._last_rendered = ""
        self.created = time.time()

    def start(self):
        pid, fd = pty.fork()
        if pid == 0:
            env = {
                **os.environ,
                "TERM": "xterm-256color",
                "COLORTERM": "truecolor",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
            }
            try:
                os.execvpe(SHELL_PATH, [SHELL_PATH, "-i"], env)
            except Exception as e:
                os.write(2, f"exec failed: {e}\n".encode())
                os._exit(1)
        else:
            self.pid = pid
            self.master_fd = fd
            self._set_winsize(self.master_fd, ROWS, COLS)
            threading.Thread(target=self._read_loop, daemon=True).start()

    @staticmethod
    def _set_winsize(fd, rows, cols):
        try:
            fcntl.ioctl(fd, termios.TIOCSWINSZ,
                        struct.pack("HHHH", rows, cols, 0, 0))
        except Exception:
            pass

    def _read_loop(self):
        while True:
            try:
                r, _, _ = select.select([self.master_fd], [], [], 0.1)
                if not r:
                    continue
                data = os.read(self.master_fd, 8192)
                if not data:
                    break
                text = data.decode("utf-8", errors="replace")
                with self.lock:
                    try:
                        self.stream.feed(text)
                    except Exception:
                        pass
                    self.dirty = True
            except OSError:
                break

    def write(self, data: bytes):
        if self.master_fd is None:
            return
        try:
            os.write(self.master_fd, data)
        except OSError:
            pass

    def send_command(self, cmd: str):
        self.write((cmd + "\n").encode())

    def send_control(self, name: str):
        table = {"INT": b"\x03", "EOF": b"\x04",
                 "TSTP": b"\x1a", "QUIT": b"\x1c"}
        if name in table:
            self.write(table[name])

    def resize(self, rows, cols):
        rows = max(5, min(rows, 200))
        cols = max(20, min(cols, 400))
        if rows == self.screen.lines and cols == self.screen.columns:
            return
        with self.lock:
            self.screen.resize(lines=rows, columns=cols)
            try:
                self.stream = pyte.Stream(self.screen)
            except Exception:
                pass
            self.dirty = True
        if self.master_fd is not None:
            self._set_winsize(self.master_fd, rows, cols)
            try:
                os.kill(self.pid, signal.SIGWINCH)
            except Exception:
                pass

    def stop(self):
        try:
            if self.pid:
                os.kill(self.pid, signal.SIGTERM)
        except Exception:
            pass

    def render_markup(self) -> str:
        with self.lock:
            if not self.dirty:
                return self._last_rendered
            lines_out = []
            for y in range(self.screen.lines):
                row = self.screen.buffer[y]
                parts = []
                cur_fg = None
                cur_bold = False
                for x in range(self.screen.columns):
                    ch = row[x]
                    fg = color_to_hex(ch.fg) if ch.fg != "default" else FG_DEFAULT
                    bold = ch.bold
                    if fg != cur_fg or bold != cur_bold:
                        if cur_fg is not None or cur_bold:
                            if cur_fg:
                                parts.append("[/color]")
                            if cur_bold:
                                parts.append("[/b]")
                        if bold:
                            parts.append("[b]")
                        if fg != FG_DEFAULT:
                            parts.append(f"[color={fg}]")
                            cur_fg = fg
                        else:
                            cur_fg = None
                        cur_bold = bold
                    c = ch.data
                    if c == "[":
                        c = "[["
                    elif c == "]":
                        c = "]]"
                    parts.append(c)
                if cur_bold:
                    parts.append("[/b]")
                if cur_fg:
                    parts.append("[/color]")
                lines_out.append("".join(parts).rstrip())
            text = "\n".join(lines_out).rstrip("\n")
            self._last_rendered = text
            self.dirty = False
            return text


_sessions = {}
_sessions_lock = threading.Lock()


def _new_session_id():
    return uuid.uuid4().hex[:12]


def create_session():
    sid = _new_session_id()
    s = TerminalSession()
    s.start()
    with _sessions_lock:
        _sessions[sid] = s
    return sid


def get_session(sid):
    with _sessions_lock:
        return _sessions.get(sid)


def drop_session(sid):
    with _sessions_lock:
        s = _sessions.pop(sid, None)
    if s:
        s.stop()


def cleanup_stale(max_age_sec=3600):
    now = time.time()
    dead = []
    with _sessions_lock:
        for sid, s in _sessions.items():
            if now - s.created > max_age_sec:
                dead.append(sid)
    for sid in dead:
        drop_session(sid)


app = Flask(__name__)


class SilentHandler(WSGIRequestHandler):
    def log_request(self, code='-', size='-'):
        pass

    def log_message(self, format, *args):
        pass


@app.route('/')
def index():
    with _sessions_lock:
        n = len(_sessions)
    return (
        "<h1>Virtual Terminal Server</h1>"
        f"<p>shell: {SHELL_NAME} ({SHELL_PATH})</p>"
        f"<p>sessions: {n}</p>"
        f"<p>running: {SERVER_READY}</p>"
    )


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'running': SERVER_READY}), 200


@app.route('/term/new', methods=['POST'])
def term_new():
    sid = create_session()
    return jsonify({'status': 'ok', 'session': sid}), 200


@app.route('/term/<sid>/screen', methods=['GET'])
def term_screen(sid):
    s = get_session(sid)
    if not s:
        return jsonify({'status': 'error', 'message': 'no such session'}), 404
    return jsonify({'status': 'ok', 'text': s.render_markup()}), 200


@app.route('/term/<sid>/cmd', methods=['POST'])
def term_cmd(sid):
    s = get_session(sid)
    if not s:
        return jsonify({'status': 'error', 'message': 'no such session'}), 404
    payload = request.get_json(silent=True) or {}
    data = payload.get('data', '')
    if data:
        s.send_command(data)
    return jsonify({'status': 'ok'}), 200


@app.route('/term/<sid>/ctrl', methods=['POST'])
def term_ctrl(sid):
    s = get_session(sid)
    if not s:
        return jsonify({'status': 'error', 'message': 'no such session'}), 404
    payload = request.get_json(silent=True) or {}
    name = payload.get('data', '')
    s.send_control(name)
    return jsonify({'status': 'ok'}), 200


@app.route('/term/<sid>/resize', methods=['POST'])
def term_resize(sid):
    s = get_session(sid)
    if not s:
        return jsonify({'status': 'error', 'message': 'no such session'}), 404
    payload = request.get_json(silent=True) or {}
    s.resize(int(payload.get('rows', ROWS)), int(payload.get('cols', COLS)))
    return jsonify({'status': 'ok'}), 200


@app.route('/term/<sid>/close', methods=['POST'])
def term_close(sid):
    drop_session(sid)
    return jsonify({'status': 'ok'}), 200


_httpd = None
_server_thread = None
_server_lock = threading.Lock()
SERVER_READY = False


def _serve():
    global _httpd, SERVER_READY
    try:
        _httpd = make_server("0.0.0.0", SSH_PORT, app, threaded=True)
        SERVER_READY = True
        print(f"[ssh] слушаю 0.0.0.0:{SSH_PORT}")
        _httpd.serve_forever()
    except Exception as e:
        print(f"[ssh] server error: {e}")
        SERVER_READY = False
    finally:
        SERVER_READY = False
        _httpd = None
        print("[ssh] остановлен")


def start_server():
    global _server_thread
    with _server_lock:
        if _server_thread and _server_thread.is_alive():
            return True
        _server_thread = threading.Thread(
            target=_serve, name="ssh-server", daemon=True)
        _server_thread.start()
    return True


def stop_server(timeout=3.0):
    global _server_thread, _httpd
    with _sessions_lock:
        sids = list(_sessions.keys())
    for sid in sids:
        drop_session(sid)

    try:
        if _httpd is not None:
            _httpd.shutdown()
    except Exception as e:
        print(f"[ssh] shutdown: {e}")

    if _server_thread is not None:
        _server_thread.join(timeout=timeout)
    _server_thread = None
    _httpd = None
    print("[ssh] stop_server done")


def is_running():
    return SERVER_READY


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
    ip = get_local_ip()
    print(f"{ip}:{SSH_PORT}")
    print(f"shell: {SHELL_NAME} ({SHELL_PATH})")
    start_server()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[ssh] shutdown by user")
        stop_server()


if __name__ == '__main__':
    main()
