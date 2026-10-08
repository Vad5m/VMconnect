import os
import sys
import socket
import threading
import traceback
import time
from pathlib import Path

from flask import (
    Flask, request, redirect, url_for, send_file, send_from_directory,
    render_template, abort, jsonify, make_response
)

FTP_PORT_PC = 42004
FTP_PORT_PHONE = 42005
DEFAULT_HOST = "192.168.1.42"

_server_host = None
_server_port = FTP_PORT_PC

if sys.platform == "win32":
    ROOT = "C:\\"
elif os.path.exists("/storage/emulated/0"):
    ROOT = "/storage/emulated/0"
else:
    ROOT = "/"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BASE_DIR, "data", "media")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

SERVER_READY = False
ERRORS = []
ERROR_LOCK = threading.Lock()

_flask_app = None
_flask_thread = None
_httpd = None


def log(msg):
    print(f"[webftp] {msg}")


def log_error(msg):
    with ERROR_LOCK:
        ERRORS.append(msg)
        if len(ERRORS) > 50:
            ERRORS.pop(0)
    log(f"[ERROR] {msg}")


def get_errors():
    with ERROR_LOCK:
        return list(ERRORS)


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


def set_server(host, port=None):
    global _server_host, _server_port
    if host:
        _server_host = host
    if port:
        _server_port = port
    log(f"set_server: {_server_host}:{_server_port}")


def is_server_ready():
    return SERVER_READY


def get_url():
    return f"http://{get_local_ip()}:{_server_port}/"


def _safe_path(rel):
    try:
        p = (Path(ROOT) / rel.lstrip("/")).resolve()
        root = Path(ROOT).resolve()
        if root not in p.parents and p != root:
            abort(403)
        return p
    except Exception as e:
        abort(400, f"Некорректный путь: {e}")


def human_size(n):
    for unit in ("B", "K", "M", "G", "T"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}P"


IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "ico",
              "heic", "avif"}

ICON_MAP = [
    (IMAGE_EXTS, "image.png", "[img]"),
    ({"mp4", "mkv", "avi", "mov", "webm", "flv", "m4v", "3gp"},
     "video.png", "[vid]"),
    ({"mp3", "wav", "flac", "ogg", "m4a", "aac", "opus", "wma"},
     "audio.png", "[aud]"),
    ({"zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso"},
     "archive.png", "[arc]"),
    ({"pdf", "doc", "docx", "txt", "rtf", "odt", "md"},
     "doc.png", "[doc]"),
    ({"xls", "xlsx", "csv", "ods"}, "sheet.png", "[xls]"),
    ({"ppt", "pptx", "odp"}, "slide.png", "[ppt]"),
    ({"py", "js", "ts", "html", "css", "json", "xml", "yml", "yaml",
      "c", "cpp", "h", "java", "go", "rs", "sh", "php", "rb", "sql",
      "ini", "cfg", "toml"}, "code.png", "[src]"),
    ({"apk", "exe", "msi", "dmg", "deb", "rpm", "appimage"},
     "apk.png", "[bin]"),
]


def file_icon(path, is_dir):
    try:
        if is_dir:
            return "folder.png", "[dir]", False
        ext = path.suffix.lower().lstrip(".")
        is_img = ext in IMAGE_EXTS
        for exts, icon, emoji in ICON_MAP:
            if ext in exts:
                return icon, emoji, is_img
        return "file.png", "[file]", is_img
    except Exception:
        return "file.png", "[file]", False


def _get_lang():
    lang = request.cookies.get("lang")
    if lang in I18N:
        return lang
    lang = request.args.get("lang")
    if lang in I18N:
        return lang
    return "en"


I18N = {
    "en": {
        "root": "Root", "up": "Up", "upload": "Upload",
        "choose": "Choose files", "no_files": "No files selected",
        "empty": "Empty", "errors": "Errors", "clear": "Clear",
        "delete_confirm": "Delete?", "size": "Size",
        "back": "Back to files", "error": "Error",
        "lang_switch": "RU", "yes": "Yes", "no": "No",
    },
    "ru": {
        "root": "Корень", "up": "Вверх", "upload": "Загрузить",
        "choose": "Выбрать файлы", "no_files": "Файлы не выбраны",
        "empty": "Пусто", "errors": "Ошибки", "clear": "Очистить",
        "delete_confirm": "Удалить?", "size": "Размер",
        "back": "Вернуться к файлам", "error": "Ошибка",
        "lang_switch": "EN", "yes": "Да", "no": "Нет",
    },
}


def _create_app():
    app = Flask(
        __name__,
        template_folder=TEMPLATES_DIR,
        static_folder=None,
    )

    def _err_page(code, message, details=None):
        try:
            lang = _get_lang()
            return render_template(
                "error.html", code=code, message=message, details=details,
                t=I18N[lang]), code
        except Exception:
            return f"<h1>Error {code}</h1><pre>{message}\n{details or ''}</pre>", code

    @app.errorhandler(400)
    def err_400(e):
        return _err_page(400, getattr(e, "description", str(e)))

    @app.errorhandler(403)
    def err_403(e):
        return _err_page(403, "Forbidden / Доступ запрещён",
                         getattr(e, "description", None))

    @app.errorhandler(404)
    def err_404(e):
        return _err_page(404, "Not found / Не найдено")

    @app.errorhandler(500)
    def err_500(e):
        tb = traceback.format_exc()
        log_error(f"500: {e}\n{tb}")
        return _err_page(500, "Internal error", tb)

    @app.errorhandler(Exception)
    def err_any(e):
        tb = traceback.format_exc()
        log_error(f"{type(e).__name__}: {e}\n{tb}")
        return _err_page(500, f"{type(e).__name__}: {e}", tb)

    @app.route("/media/<path:fname>")
    def media(fname):
        try:
            safe = os.path.normpath(fname).lstrip("/\\")
            if ".." in safe.split(os.sep):
                abort(403)
            full = os.path.join(MEDIA_DIR, safe)
            if not os.path.isfile(full):
                abort(404)
            resp = make_response(send_from_directory(MEDIA_DIR, safe))
            resp.headers["Cache-Control"] = "public, max-age=86400"
            return resp
        except Exception as e:
            log_error(f"media({fname}): {e}")
            abort(404)

    @app.route("/lang/<code>")
    def set_lang(code):
        back = request.args.get("back", "/")
        if code not in I18N:
            code = "en"
        resp = make_response(redirect(back))
        resp.set_cookie("lang", code, max_age=60 * 60 * 24 * 365)
        return resp

    @app.route("/errors/clear")
    def clear_err():
        try:
            with ERROR_LOCK:
                ERRORS.clear()
            return redirect("/")
        except Exception as e:
            log_error(f"clear_err: {e}")
            return _err_page(500, str(e))

    @app.route("/errors")
    def show_errors():
        return jsonify(errors=get_errors())

    @app.route("/")
    def index_root():
        return _index("")

    @app.route("/browse/")
    def index_browse_empty():
        return _index("")

    @app.route("/browse/<path:path>")
    def index_browse(path):
        return _index(path)

    def _index(path=""):
        try:
            lang = _get_lang()
            t = I18N[lang]
            other = "ru" if lang == "en" else "en"

            target = _safe_path(path)
            if not target.is_dir():
                return redirect(url_for("download", path=path))

            entries = []
            try:
                for child in sorted(target.iterdir(),
                                    key=lambda c: (not c.is_dir(),
                                                   c.name.lower())):
                    try:
                        rel = str(child.relative_to(Path(ROOT).resolve())
                                  ).replace(os.sep, "/")
                        is_dir = child.is_dir()
                        try:
                            size = child.stat().st_size if child.is_file() else 0
                        except OSError:
                            size = None
                        icon_name, emoji, is_img = file_icon(child, is_dir)
                        entries.append({
                            "name": child.name,
                            "is_dir": is_dir,
                            "icon": icon_name,
                            "fallback": emoji,
                            "is_img": is_img,
                            "size": human_size(size) if size else "",
                            "url": url_for("index_browse", path=rel) if is_dir
                                   else url_for("download", path=rel),
                            "delete_url": url_for("delete", path=rel),
                        })
                    except Exception as e:
                        log_error(f"обработка {child}: {e}")
            except PermissionError as e:
                log_error(f"нет доступа к {target}: {e}")
                abort(403, f"Нет доступа: {target}")

            parts = [p for p in path.strip("/").split("/") if p]
            crumbs = []
            acc = ""
            for p in parts:
                acc = f"{acc}/{p}" if acc else p
                crumbs.append({"name": p, "rel": acc})

            parent = "/".join(parts[:-1]) if parts else ""

            return render_template(
                "files.html",
                path="/" + path.strip("/") if path.strip("/") else "/",
                parent=parent,
                crumbs=crumbs,
                entries=entries,
                errors=get_errors(),
                t=t,
                other_lang=other,
            )
        except Exception as e:
            tb = traceback.format_exc()
            log_error(f"_index({path}): {e}\n{tb}")
            return _err_page(500, f"{type(e).__name__}: {e}", tb)

    @app.route("/download/<path:path>")
    def download(path):
        try:
            target = _safe_path(path)
            if not target.is_file() or not os.access(str(target), os.R_OK):
                abort(404, f"Файл не найден: {target}")
            try:
                if target.stat().st_size == 0:
                    abort(404, f"Файл пуст или недоступен: {target}")
            except OSError as e:
                abort(404, f"Файл недоступен: {target} ({e})")
            return send_file(str(target), as_attachment=False,
                             download_name=target.name)
        except Exception as e:
            tb = traceback.format_exc()
            log_error(f"download({path}): {e}\n{tb}")
            return _err_page(500, f"{type(e).__name__}: {e}", tb)

    @app.route("/upload/", methods=["POST"])
    @app.route("/upload/<path:path>", methods=["POST"])
    def upload(path=""):
        try:
            target_dir = _safe_path(path)
            if not target_dir.is_dir():
                abort(400, f"Не папка: {target_dir}")
            for f in request.files.getlist("file"):
                if not f.filename:
                    continue
                name = os.path.basename(f.filename)
                try:
                    f.save(target_dir / name)
                except Exception as e:
                    log_error(f"сохранить {name}: {e}")
            return redirect(f"/browse/{path}" if path else "/")
        except Exception as e:
            tb = traceback.format_exc()
            log_error(f"upload({path}): {e}\n{tb}")
            return _err_page(500, f"{type(e).__name__}: {e}", tb)

    @app.route("/delete/<path:path>", methods=["GET", "POST"])
    def delete(path):
        try:
            target = _safe_path(path)
            if target.is_dir():
                try:
                    target.rmdir()
                except OSError as e:
                    log_error(f"папка не пустая: {target} — {e}")
                    abort(400, "Папка не пустая")
            else:
                target.unlink(missing_ok=True)
            parent = "/".join(path.rstrip("/").split("/")[:-1])
            return redirect(f"/browse/{parent}" if parent else "/")
        except Exception as e:
            tb = traceback.format_exc()
            log_error(f"delete({path}): {e}\n{tb}")
            return _err_page(500, f"{type(e).__name__}: {e}", tb)

    return app


def _start_flask():
    global _flask_app, SERVER_READY, _httpd
    try:
        log(f"[HTTP] ROOT={ROOT} PORT={_server_port} "
            f"TPL={TEMPLATES_DIR} MEDIA={MEDIA_DIR}")
        log(f"[TPL] exists={os.path.isdir(TEMPLATES_DIR)} "
            f"files.html={os.path.isfile(os.path.join(TEMPLATES_DIR, 'files.html'))} "
            f"error.html={os.path.isfile(os.path.join(TEMPLATES_DIR, 'error.html'))}")

        try:
            if not Path(ROOT).exists():
                log_error(f"ROOT не существует: {ROOT}")
            else:
                list(Path(ROOT).iterdir())
                log("[ROOT] OK, доступен")
        except PermissionError as e:
            log_error(f"Нет доступа к ROOT {ROOT}: {e}")
            return
        except Exception as e:
            log_error(f"Ошибка проверки ROOT: {e}\n{traceback.format_exc()}")

        if not os.path.isdir(MEDIA_DIR):
            log(f"[MEDIA] папка не найдена: {MEDIA_DIR}")

        from werkzeug.serving import make_server

        _flask_app = _create_app()
        _httpd = make_server("0.0.0.0", _server_port, _flask_app,
                             threaded=True)
        SERVER_READY = True
        log(f"[HTTP] слушаю 0.0.0.0:{_server_port}")
        _httpd.serve_forever()
    except Exception as e:
        tb = traceback.format_exc()
        log_error(f"server: {e}\n{tb}")
        SERVER_READY = False


def start_server(port=None):
    global _flask_thread, _server_port, SERVER_READY
    if port:
        _server_port = port
    if _flask_thread and _flask_thread.is_alive():
        return
    SERVER_READY = False
    _flask_thread = threading.Thread(target=_start_flask, daemon=True,
                                     name="webftp")
    _flask_thread.start()


def stop_server(timeout=3.0):
    global _flask_thread, SERVER_READY, _httpd
    try:
        if _httpd is not None:
            _httpd.shutdown()
    except Exception as e:
        log_error(f"shutdown: {e}")
    if _flask_thread is not None:
        _flask_thread.join(timeout=timeout)
    _flask_thread = None
    _httpd = None
    SERVER_READY = False
    log("остановлен")
