import json
import socket
import threading
import time
import subprocess
import getpass
import webbrowser
import os

DISCOVERY_PORT = 42420
SERVICE_PORT = 42042
PORTS = [(DISCOVERY_PORT, 'udp'), (SERVICE_PORT, 'tcp')]

PORT_RANGE_START = 42000
PORT_RANGE_END = 42100

PASSWORD_FILE = os.path.expanduser('~/.app_connect_sudo_pass')

_SUDO_PASSWORD = None


def _load_password():
    global _SUDO_PASSWORD
    if _SUDO_PASSWORD is not None:
        return _SUDO_PASSWORD
    if os.path.exists(PASSWORD_FILE):
        try:
            with open(PASSWORD_FILE, 'r') as f:
                pwd = f.read().strip()
            if pwd:
                _SUDO_PASSWORD = pwd
                return _SUDO_PASSWORD
        except Exception:
            pass
    pwd = getpass.getpass("sudo пароль (для ufw): ")
    _SUDO_PASSWORD = pwd
    try:
        with open(PASSWORD_FILE, 'w') as f:
            f.write(pwd)
        os.chmod(PASSWORD_FILE, 0o600)
    except Exception as e:
        print(f"[warn] не удалось сохранить пароль: {e}")
    return _SUDO_PASSWORD


def _sudo_run(args, use_password=False):
    if use_password:
        password = _load_password()
        return subprocess.run(
            ['sudo', '-S'] + args,
            input=password + '\n', text=True, capture_output=True
        )
    return subprocess.run(
        ['sudo', '-n'] + args,
        text=True, capture_output=True
    )


def _ufw_status():
    r = _sudo_run(['ufw', 'status'], use_password=False)
    if r.returncode == 0:
        return r
    r = _sudo_run(['ufw', 'status'], use_password=True)
    return r


def ufw_rule_exists(port, proto):
    r = _ufw_status()
    if r.returncode != 0:
        return None
    return f'{port}/{proto}' in r.stdout


def _ufw_allow(rule):
    r = _sudo_run(['ufw', 'allow', rule], use_password=False)
    if r.returncode == 0:
        return r
    return _sudo_run(['ufw', 'allow', rule], use_password=True)


def ensure_ports(ports):
    unknown = []
    to_open = []
    for p, pr in ports:
        exists = ufw_rule_exists(p, pr)
        if exists is True:
            print(f"[ok] {p}/{pr} уже разрешён")
        elif exists is False:
            to_open.append((p, pr))
        else:
            unknown.append((p, pr))

    need = to_open + unknown
    if not need:
        return True

    for port, proto in need:
        r = _ufw_allow(f'{port}/{proto}')
        if r.returncode != 0:
            print(f"[err] {port}/{proto}: {r.stderr.strip()}")
            return False
        print(f"[ok] открыт {port}/{proto}")
    return True


def ensure_port_range(start, end, proto='tcp'):
    r = _ufw_status()
    if r.returncode == 0:
        all_open = True
        for p in range(start, end + 1):
            if f'{p}/{proto}' not in r.stdout:
                all_open = False
                break
        if all_open:
            print(f"[ok] {start}:{end}/{proto} уже разрешён")
            return True

    r = _ufw_allow(f'{start}:{end}/{proto}')
    if r.returncode != 0:
        print(f"[err] {start}:{end}/{proto}: {r.stderr.strip()}")
        return False
    print(f"[ok] открыт диапазон {start}:{end}/{proto}")
    return True


def start_discovery_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('', DISCOVERY_PORT))
    while True:
        data, addr = sock.recvfrom(1024)
        if data == b'DISCOVER_MY_SERVER':
            sock.sendto(f'MY_SERVER:{SERVICE_PORT}'.encode(), addr)


class SettingsBus:
    def __init__(self):
        self._lock = threading.Lock()
        self._settings = {}
        self._provider = None

    def set_provider(self, provider):
        with self._lock:
            self._provider = provider
            if provider is not None:
                try:
                    self._settings = dict(provider() or {})
                except Exception as e:
                    print(f"[app_connect] provider error: {e}")

    def get(self) -> dict:
        with self._lock:
            if self._provider is not None:
                try:
                    self._settings = dict(self._provider() or {})
                except Exception as e:
                    print(f"[app_connect] provider error: {e}")
            return dict(self._settings)

    def update(self, settings: dict):
        with self._lock:
            self._settings = dict(settings or {})


bus = SettingsBus()


def broadcast(settings: dict | None = None):
    if settings is not None:
        bus.update(settings)
    payload = bus.get()
    if _SettingsServer.instance is not None:
        _SettingsServer.instance.send_to_all(payload)


def open_url(url: str) -> bool:
    if not isinstance(url, str):
        return False
    url = url.strip()
    if not url:
        return False
    if not (url.startswith('http://') or url.startswith('https://')):
        url = 'http://' + url
    try:
        webbrowser.open(url)
        print(f"[app_connect] открываю ссылку: {url}")
        return True
    except Exception as e:
        print(f"[app_connect] ошибка открытия ссылки: {e}")
        return False


class _SettingsServer:
    instance = None

    def __init__(self, host: str = "0.0.0.0", port: int = SERVICE_PORT):
        _SettingsServer.instance = self
        self.host = host
        self.port = port

        self._stop_event = threading.Event()
        self._server_sock = None
        self._clients = set()
        self._clients_lock = threading.Lock()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._serve, name="app_connect", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0):
        self._stop_event.set()

        if self._server_sock is not None:
            try:
                self._server_sock.close()
            except OSError:
                pass

        with self._clients_lock:
            for c in list(self._clients):
                try:
                    c.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    c.close()
                except OSError:
                    pass
            self._clients.clear()

        if self._thread:
            self._thread.join(timeout=timeout)

    def send_to_all(self, settings: dict):
        if not settings:
            return
        try:
            payload = (json.dumps(settings, ensure_ascii=False) + "\n").encode("utf-8")
        except Exception as e:
            print(f"[app_connect] json error: {e}")
            return

        dead = []
        with self._clients_lock:
            clients = list(self._clients)
        for c in clients:
            try:
                c.sendall(payload)
            except OSError:
                dead.append(c)

        if dead:
            with self._clients_lock:
                for c in dead:
                    self._clients.discard(c)
                    try:
                        c.close()
                    except OSError:
                        pass

    def _serve(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind((self.host, self.port))
            srv.listen(8)
        except OSError as e:
            print(f"[app_connect] bind error on {self.host}:{self.port}: {e}")
            return

        self._server_sock = srv
        srv.settimeout(1.0)

        while not self._stop_event.is_set():
            try:
                client, addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            print(f"[app_connect] клиент подключился: {addr}")
            client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            with self._clients_lock:
                self._clients.add(client)

            try:
                snapshot = bus.get()
                payload = (json.dumps(snapshot, ensure_ascii=False) + "\n").encode("utf-8")
                client.sendall(payload)
            except OSError:
                with self._clients_lock:
                    self._clients.discard(client)
                try:
                    client.close()
                except OSError:
                    pass
                continue

            threading.Thread(
                target=self._client_reader,
                args=(client, addr),
                daemon=True,
                name=f"app_connect-client-{addr[1]}",
            ).start()

        try:
            srv.close()
        except OSError:
            pass
        self._server_sock = None
        print("[app_connect] остановлен")

    def _client_reader(self, client: socket.socket, addr):
        buffer = b""
        try:
            client.settimeout(1.0)
            while not self._stop_event.is_set():
                try:
                    data = client.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not data:
                    break

                buffer += data
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except Exception:
                        continue
                    self._handle_client_message(msg)
        finally:
            with self._clients_lock:
                self._clients.discard(client)
            try:
                client.close()
            except OSError:
                pass
            print(f"[app_connect] клиент отключился: {addr}")

    def _handle_client_message(self, msg):
        if not isinstance(msg, dict):
            return
        action = msg.get("action")
        if action == "open_url":
            url = msg.get("url", "")
            open_url(url)


_server = None
_discovery_thread = None
_started = False


def start_server(host: str = "0.0.0.0", port: int = SERVICE_PORT) -> _SettingsServer:
    global _server
    if _server is None:
        _server = _SettingsServer(host, port)
    _server.start()
    return _server


def stop_server(timeout: float = 3.0):
    global _server
    if _server is not None:
        _server.stop(timeout=timeout)
        _server = None
        _SettingsServer.instance = None


def start_all():
    global _discovery_thread, _started

    if _started:
        return

    if not ensure_port_range(PORT_RANGE_START, PORT_RANGE_END, 'tcp'):
        raise SystemExit("Не удалось открыть диапазон TCP портов")

    if not ensure_port_range(PORT_RANGE_START, PORT_RANGE_END, 'udp'):
        raise SystemExit("Не удалось открыть диапазон UDP портов")

    if not ensure_ports(PORTS):
        raise SystemExit("Не удалось открыть порты")

    _discovery_thread = threading.Thread(
        target=start_discovery_server,
        name="discovery",
        daemon=True,
    )
    _discovery_thread.start()

    time.sleep(0.3)
    start_server()

    _started = True


def stop_all(timeout: float = 3.0):
    global _started
    stop_server(timeout=timeout)
    _started = False


if __name__ == '__main__':
    start_all()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[shutdown] остановка...")
        stop_all()
