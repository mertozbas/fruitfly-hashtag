"""Distribution contracts, download recovery and workspace isolation; no scientific dependencies."""
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fruitfly_lab.download import fetch
from fruitfly_lab.workspace import materialize, status, workspace_lock, bundle_files


@contextmanager
def server(handler):
    service = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{service.server_port}"
    finally:
        service.shutdown()
        service.server_close()
        thread.join(3)


class WorkspaceTests(unittest.TestCase):
    def test_empty_workspace_opens_without_brain_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            materialize(home)
            result = status(home)
            self.assertFalse(result["walking_ready"])
            self.assertFalse(result["flight_ready"])
            self.assertFalse((home / "data").exists())
            self.assertFalse((home / "models").exists())
            self.assertTrue((home / "docs/index.html").is_file())
            self.assertTrue((home / "ui/vendor/THREE-LICENSE.txt").is_file())
            for relative in ('ui/calibration.js','ui/calibration.css','ui/calibration-board.svg','ui/calibration-reference.json',
                             'so101/calibration_motor.py','so101/calibration_camera.py','so101/calibration_host.py','so101/calibration_contract.py'):
                self.assertTrue((home / relative).is_file(),relative)

    def test_upgrade_preserves_models_and_blocks_modified_code(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            materialize(home)
            checkpoint = home / "models/lab_runs/user/trained.npz"
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_bytes(b"personal checkpoint")
            materialize(home)
            self.assertEqual(checkpoint.read_bytes(), b"personal checkpoint")
            (home / "brain.py").write_text("# user change\n")
            with self.assertRaisesRegex(RuntimeError, "Yerel değişiklik"):
                materialize(home)
            self.assertEqual((home / "brain.py").read_text(), "# user change\n")

    def test_git_and_symlink_destinations_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".git").mkdir()
            with self.assertRaisesRegex(RuntimeError, "Git"):
                materialize(home)
            (home / ".git").rmdir()
            (home / "brain.py").symlink_to(ROOT / "brain.py")
            with self.assertRaisesRegex(RuntimeError, "sembolik"):
                materialize(home)

    def test_only_one_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            with workspace_lock(Path(directory)):
                with self.assertRaisesRegex(RuntimeError, "zaten açık"):
                    with workspace_lock(Path(directory)):
                        self.fail("Second lock acquired")

    def test_bundle_is_explicit_and_data_free(self):
        files = bundle_files()
        self.assertGreater(len(files), 40)
        for name, source in files.items():
            self.assertTrue(source.is_file(), name)
            self.assertFalse(set(Path(name).parts) & {"data", "models", "artifacts", ".venv", ".runtime", ".git"}, name)
            self.assertLess(source.stat().st_size, 4_000_000, name)


class DownloadTests(unittest.TestCase):
    data = b"verified scientific fixture" * 100

    def record(self, url):
        return {"file": "fixture.feather", "size": len(self.data), "sha256": hashlib.sha256(self.data).hexdigest(), "download_url": url}

    def test_resume_verified_partial_and_reuse(self):
        data = self.data
        received = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                received.append(self.headers.get("Range"))
                offset = int(self.headers["Range"].split("=")[1].split("-")[0])
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {offset}-{len(data)-1}/{len(data)}")
                self.end_headers()
                self.wfile.write(data[offset:])
        with server(Handler) as url, tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            (destination / "fixture.feather.part").write_bytes(data[:100])
            fetch(self.record(url), destination, emit=lambda _: None)
            fetch(self.record(url), destination, emit=lambda _: None)
            self.assertEqual(received, ["bytes=100-"])
            self.assertEqual((destination / "fixture.feather").read_bytes(), data)
            self.assertFalse((destination / "fixture.feather.part").exists())

    def test_server_ignoring_range_restarts_safely(self):
        data = self.data
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(data)
        with server(Handler) as url, tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            (destination / "fixture.feather.part").write_bytes(data[:100])
            fetch(self.record(url), destination, emit=lambda _: None)
            self.assertEqual((destination / "fixture.feather").read_bytes(), data)

    def test_corrupt_final_is_preserved_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "fixture.feather"
            target.write_bytes(b"bad")
            with self.assertRaisesRegex(ValueError, "doğrulanamadı"):
                fetch(self.record("http://invalid.example"), target.parent)
            self.assertEqual(target.read_bytes(), b"bad")


class PortalTests(unittest.TestCase):
    def test_fresh_http_guide_and_guards(self):
        import socket
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
            child = subprocess.Popen([sys.executable, "-m", "fruitfly_lab", "--home", directory,
                "ui", "--port", str(port), "--no-browser"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            base = f"http://127.0.0.1:{port}"
            try:
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(base + "/api/setup", timeout=1) as response:
                            result = json.load(response)
                        break
                    except OSError:
                        if child.poll() is not None:
                            self.fail(child.stderr.read().decode())
                        time.sleep(.05)
                else:
                    self.fail("Portal did not start")
                self.assertFalse(result["walking_ready"])
                for path, word in [("/", "Beyni indir ve kur"), ("/guide/index.html", "İlk yürüyüş eğitimi")]:
                    with urllib.request.urlopen(base + path) as response:
                        self.assertIn(word, response.read().decode())
                for headers, expected in [({"Origin": "https://evil.example"}, 403), ({"Host": "evil.example"}, 403)]:
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(urllib.request.Request(base + "/api/setup", headers=headers))
                    self.assertEqual(error.exception.code, expected)
                for path in ["/guide/../../pyproject.toml", "/guide/%2e%2e/pyproject.toml"]:
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(base + path)
                    self.assertEqual(error.exception.code, 404)
                request = urllib.request.Request(base + "/api/setup/launch", data=b"{}", headers={"Content-Type": "application/json"})
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request)
                self.assertEqual(error.exception.code, 409)
                self.assertFalse((Path(directory) / "data").exists())
            finally:
                child.send_signal(2)
                child.wait(timeout=10)
                child.stderr.close()


if __name__ == "__main__":
    unittest.main()
