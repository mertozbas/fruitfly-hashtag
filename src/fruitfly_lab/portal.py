"""Dependency-free local setup UI. Hands the same port to the scientific UI."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import unquote, urlsplit
import webbrowser

from .workspace import status


class SetupJob:
    def __init__(self, home):
        self.home, self.process = home, None
        self.state = "idle"
        self.lock = threading.Lock()
        self.log = home / ".runtime/setup.log"

    def snapshot(self):
        with self.lock:
            if self.process is not None and self.process.poll() is not None and self.state == "running":
                self.state = "complete" if self.process.returncode == 0 else "failed"
            tail = ""
            if self.log.exists():
                with self.log.open("rb") as stream:
                    stream.seek(max(0, self.log.stat().st_size - 16000))
                    tail = stream.read().decode("utf-8", errors="replace")
            return {**status(self.home), "job": self.state, "log": tail}

    def start(self, component):
        if component not in {"walking", "flight", "all"}:
            raise ValueError("Bilinmeyen kurulum bileşeni")
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                raise RuntimeError("Bir kurulum zaten çalışıyor")
            with self.log.open("w") as log:
                self.process = subprocess.Popen(
                    [sys.executable, "-u", "-m", "fruitfly_lab.setup", str(self.home), component],
                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            self.state = "running"
            threading.Thread(target=self._watch, args=(self.process,), daemon=True).start()

    def _watch(self, process):
        try:
            process.wait(timeout=7200)
        except subprocess.TimeoutExpired:
            with self.lock:
                if self.process is process:
                    self._stop("timed_out")

    def _stop(self, state):
        if self.process is not None and self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=5)
        self.state = state

    def stop(self):
        with self.lock:
            self._stop("cancelled")


def serve(home, port, *, open_browser=True):
    job = SetupJob(home)
    launch = threading.Event()
    origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, code, data, content_type="application/json; charset=utf-8"):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def allowed(self):
            if self.headers.get("Host") not in hosts or self.headers.get("Origin", "") not in origins | {""}:
                self.send(403, {"detail": "Yalnızca yerel, aynı kaynaktan erişim"})
                return False
            return True

        def do_GET(self):
            if not self.allowed():
                return
            path = unquote(urlsplit(self.path).path)
            if path == "/api/setup":
                self.send(200, job.snapshot())
                return
            if path == "/":
                target = Path(__file__).parent / "setup.html"
            elif path in {"/LICENSE", "/ui/vendor/THREE-LICENSE.txt"}:
                target = home / path.lstrip("/")
            elif path.startswith("/guide/"):
                base = (home / "docs").resolve()
                target = (base / (path[len("/guide/"):] or "index.html")).resolve()
                if not target.is_relative_to(base):
                    self.send(404, {"detail": "Bulunamadı"})
                    return
            else:
                self.send(404, {"detail": "Bulunamadı"})
                return
            if not target.is_file():
                self.send(404, {"detail": "Bulunamadı"})
                return
            self.send(200, target.read_bytes(), (mimetypes.guess_type(target)[0] or "text/plain") + "; charset=utf-8")

        def do_POST(self):
            if not self.allowed():
                return
            if self.headers.get("Content-Type") != "application/json":
                self.send(415, {"detail": "application/json gerekli"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024:
                    raise ValueError("Geçersiz istek boyutu")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("JSON nesnesi gerekli")
                if self.path == "/api/setup/start":
                    job.start(body.get("component"))
                elif self.path == "/api/setup/cancel":
                    job.stop()
                elif self.path == "/api/setup/launch":
                    current = job.snapshot()
                    if current["job"] == "running" or not current["walking_ready"]:
                        raise RuntimeError("Önce beyin/yürüyüş kurulumunu tamamlayın")
                    launch.set()
                else:
                    self.send(404, {"detail": "Bulunamadı"})
                    return
                self.send(200, job.snapshot())
                if launch.is_set():
                    threading.Thread(target=server.shutdown, daemon=True).start()
            except (ValueError, TypeError) as exc:
                self.send(400, {"detail": str(exc)})
            except RuntimeError as exc:
                self.send(409, {"detail": str(exc)})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Kurulum ve rehber: {url}\nVeriler: {home}\nDurdurmak için Ctrl+C.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=.25)
    finally:
        job.stop()
        server.server_close()
    return launch.is_set()
