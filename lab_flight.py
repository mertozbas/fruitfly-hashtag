"""Private pipe adapter for the isolated FlyBody Python runtime."""
import json
from pathlib import Path
import queue
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parent

class FlightProcess:
    def __init__(self, commands, states, model_path=None, model_id='trained'):
        self.commands, self.states = commands, states
        log_path = ROOT / '.runtime/flight-worker.log'
        log_path.parent.mkdir(exist_ok=True)
        args = [str(ROOT / 'flight/.venv/bin/python'), '-u', str(ROOT / 'flight/worker.py')]
        if model_path is not None:
            args += ['--model', str(model_path), '--model-id', model_id]
        with log_path.open('a') as log:
            self.process = subprocess.Popen(
                args,
                cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                text=True, bufsize=1)
        self.threads = [threading.Thread(target=fn, daemon=True) for fn in (self._write, self._read)]
        for thread in self.threads:
            thread.start()

    def _write(self):
        try:
            while self.is_alive():
                try:
                    command = self.commands.get(timeout=.25)
                except queue.Empty:
                    continue
                self.process.stdin.write(json.dumps(command) + '\n')
                self.process.stdin.flush()
                if command['op'] == 'shutdown':
                    break
        except (BrokenPipeError, OSError, ValueError):
            pass

    def _send(self, packet):
        try:
            self.states.put_nowait(packet)
        except queue.Full:
            try:
                self.states.get_nowait()
            except queue.Empty:
                pass
            try:
                self.states.put_nowait(packet)
            except queue.Full:
                pass

    def _read(self):
        for line in self.process.stdout:
            try:
                packet = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(packet, dict):
                self._send(packet)
        code = self.process.wait()
        if code:
            self._send(dict(error='Uçuş işlemi durdu. .runtime/flight-worker.log kaydını kontrol et.',
                            behavior='flight', wall_time=time.time()))

    def is_alive(self):
        return self.process.poll() is None

    def join(self, timeout):
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return
        for thread in self.threads:
            thread.join(timeout=1)
        try:
            self.process.stdin.close()
        except OSError:
            pass
        self.process.stdout.close()

    def terminate(self):
        self.process.terminate()

def metadata():
    import hashlib
    files = sorted((ROOT / 'data/flybody/trained-fly-policies/flight').rglob('*'))
    digest = hashlib.sha256()
    for path in files:
        if path.is_file():
            digest.update(path.relative_to(ROOT / 'data/flybody').as_posix().encode())
            digest.update(path.read_bytes())
    report_path = ROOT / 'artifacts/lab/flight/validation.json'
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    records = report.get('records', [])
    return dict(id='flight-pretrained', name='FlyBody / hazır uçuş', graph_version=None,
                circuit_identity=None, gains=[], sha256=digest.hexdigest(), training=None,
                evaluation=dict(success_count=sum(r['success'] for r in records), episodes=len(records)) if records else None,
                source='https://github.com/TuragaLab/flybody', neural_connected=False)
