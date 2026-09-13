"""Loopback-only laboratory: one live simulation and one bounded training job."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import asyncio
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "models/odor_navigation"
RUNS = ROOT / "models/lab_runs"
PORT = 8766

class Runtime:
    def __init__(self):
        self.process = self.commands = self.states = None
        self.latest = {}
        self.job = {"status": "idle"}
        self.job_process = None
        self.lock = threading.Lock()
        self.last_heartbeat = 0
    def control(self, command):
        if not self.process or not self.process.is_alive():
            raise HTTPException(503, "Simülasyon işlemi çalışmıyor; yerel sunucuyu yeniden başlat.")
        try:
            self.commands.put_nowait(command)
        except queue.Full:
            raise HTTPException(429, "Komut kuyruğu dolu")
    def read(self):
        while True:
            try:
                self.latest = self.states.get_nowait()
            except queue.Empty:
                break
        return self.latest

runtime = Runtime()

@asynccontextmanager
async def lifespan(app):
    from lab_graph import prepare
    from lab_worker import simulate
    prepare()
    RUNS.mkdir(parents=True, exist_ok=True)
    for path in RUNS.glob("*/run.json"):
        record = read_json(path)
        if record.get("status") in {"training", "evaluating", "cancelling"}:
            record["status"] = "interrupted"
            path.write_text(json.dumps(record, indent=2))
    ctx = mp.get_context("spawn")
    runtime.commands, runtime.states = ctx.Queue(32), ctx.Queue(2)
    runtime.process = ctx.Process(target=simulate, args=(runtime.commands, runtime.states), daemon=True)
    runtime.process.start()
    try:
        yield
    finally:
        if runtime.job_process and runtime.job_process.poll() is None:
            runtime.job_process.terminate()
            runtime.job_process.wait(timeout=10)
        if runtime.process.is_alive():
            runtime.commands.put({"op": "shutdown"})
            runtime.process.join(5)
        if runtime.process.is_alive():
            runtime.process.terminate()
            runtime.process.join(5)
        for channel in (runtime.commands, runtime.states):
            channel.cancel_join_thread()
            channel.close()

app = FastAPI(title="Hashtag Neural Lab", lifespan=lifespan)

@app.middleware("http")
async def local_only(request: Request, call_next):
    if request.headers.get("host") not in {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}:
        return JSONResponse({"detail": "Local host required"}, status_code=403)
    origin = request.headers.get("origin")
    if origin and origin not in {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}:
        return JSONResponse({"detail": "Same-origin access required"}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

def read_json(path):
    return json.loads(path.read_text()) if path.exists() else None

def models():
    training = read_json(BASE / "training.json")
    evaluation = read_json(ROOT / "artifacts/simulation/evaluation.json")
    records = [dict(id="trained", name="Koku / doğrulanmış", path=BASE / "trained.npz", training=training,
                    evaluation=evaluation["summary"]["trained"] if evaluation else None),
               dict(id="untrained", name="Eğitim öncesi", path=BASE / "untrained.npz", training=None,
                    evaluation=evaluation["summary"]["untrained"] if evaluation else None)]
    for p in sorted(RUNS.glob("*/run.json"), reverse=True):
        meta = read_json(p)
        if meta.get("status") == "complete":
            records.append(dict(id=p.parent.name, name=f"Koku / {meta['created'][11:19]}", path=p.parent / "trained.npz",
                                training=read_json(p.parent / "training.json"), evaluation=read_json(p.parent / "evaluation.json")))
    return records

def resolve_model(model_id):
    match = next((m for m in models() if m["id"] == model_id), None)
    if match is None:
        raise HTTPException(404, "Model bulunamadı")
    return match

@app.get("/api/health")
def health():
    return dict(status="ok", simulation_alive=bool(runtime.process and runtime.process.is_alive()), local=True)

@app.get("/api/catalog")
def catalog():
    return dict(models=[{k:v for k,v in m.items() if k != "path"} for m in models()], job=runtime.job,
      experiments=[dict(id="odor", title="Kokuya yönelme", status="validated", detail="Taklit öğrenmesi · 6 fizik koşulu"),
                   dict(id="avoidance", title="Kokudan kaçınma", status="planned", detail="Ters yönlendirme hedefi ve kaçınma değerlendirmesi hazırlanacak."),
                   dict(id="vision", title="Görsel yönelme", status="planned", detail="Görsel duyusal kodlama ve yeni devre bağlantısı gerekli."),
                   dict(id="terrain", title="Engel / arazi", status="planned", detail="Dokunma gözlemleri, arazi görevleri ve ödül tasarımı gerekli."),
                   dict(id="flight", title="Uçuş", status="research", detail="FlyBody uçuş görevleri var; ayrı uçuş kontrolcüsü, aerodinamik ve beyin–motor eşlemesi henüz bağlanmadı.")])

@app.get("/api/state")
def state():
    now = time.monotonic()
    if now - runtime.last_heartbeat > 5 and runtime.process.is_alive():
        runtime.control({"op": "heartbeat"})
        runtime.last_heartbeat = now
    return dict(simulation=runtime.read(), job=runtime.job, alive=runtime.process.is_alive())

@app.get("/api/graph")
def graph():
    return FileResponse(ROOT / "artifacts/lab/graph.json")

@app.get("/api/anatomy")
def anatomy():
    return FileResponse(ROOT / "artifacts/lab/anatomy.json")

@app.get("/api/anatomy/segments")
def anatomy_segments():
    return FileResponse(ROOT / "artifacts/lab/anatomy.f32", media_type="application/octet-stream")

@app.get("/api/neuron/{body_id}")
def neuron_details(body_id: int):
    from lab_details import neuron
    try:
        return neuron(body_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc))

@app.get("/api/neuron/{body_id}/connections")
def neuron_connections(body_id: int, direction: Literal["in", "out"] = "out",
                       page: int = Query(0, ge=0, le=100000), limit: int = Query(12, ge=1, le=50)):
    from lab_details import connections
    try:
        return connections(body_id, direction, page, limit)
    except KeyError as exc:
        raise HTTPException(404, str(exc))

@app.get("/api/connection/{source}/{target}")
def connection_details(source: int, target: int, model: str = "trained"):
    from lab_details import connection
    record = resolve_model(model)
    try:
        return connection(source, target, record["path"])
    except KeyError as exc:
        raise HTTPException(404, str(exc))

@app.get("/api/model/{model_id}")
def model_details(model_id: str):
    import numpy as np
    record = resolve_model(model_id)
    graph = read_json(ROOT / "artifacts/lab/graph.json")
    with np.load(record["path"], allow_pickle=False) as weights:
        w = weights["weight"]
        gains = [float(w[e["row"],e["col"]] / e["weight"]) if e["layer"] == 2 else 1. for e in graph["edges"]]
    return dict(id=model_id, graph_version=graph["version"], circuit_identity=graph["circuit_identity"],
                gains=gains, sha256=hashlib.sha256(record["path"].read_bytes()).hexdigest(),
                training=record["training"], evaluation=record["evaluation"])

class Control(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    op: Literal["pause", "reset", "model", "camera"]
    paused: bool = False
    goal: tuple[float, float] = (12, 4)
    seed: int = Field(10, ge=0, le=1000000)
    model: str = "trained"
    camera: Literal["body", "arena"] = "body"
    orbit: float = Field(0, ge=-45, le=45)
    zoom: float = Field(0, ge=-4, le=4)
    gesture: Literal["rotate", "pan", "zoom"] | None = None
    dx: float = Field(0, ge=-1, le=1)
    dy: float = Field(0, ge=-1, le=1)
    reset_view: bool = False

@app.post("/api/control")
def control(body: Control):
    if body.op == "model":
        m = resolve_model(body.model)
        command = dict(op="model", path=str(m["path"]), id=body.model)
    elif body.op == "reset":
        if not all(-30 <= x <= 30 for x in body.goal):
            raise HTTPException(422, "Hedef koordinatları -30 ile 30 mm arasında olmalı")
        command = dict(op="reset", goal=list(body.goal), seed=body.seed)
    elif body.op == "pause":
        command = dict(op="pause", paused=body.paused)
    else:
        command = dict(op="camera", camera=body.camera, orbit=body.orbit, zoom=body.zoom,
                       gesture=body.gesture, dx=body.dx, dy=body.dy, reset_view=body.reset_view)
    runtime.control(command)
    return {"accepted": True}

class TrainingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    steps: int = Field(3000, ge=200, le=10000)
    seed: int = Field(42, ge=0, le=1000000)

def training_job(directory, steps, seed):
    meta = dict(id=directory.name, status="training", created=datetime.now(timezone.utc).isoformat(), steps=steps, seed=seed)
    env = dict(os.environ, FRUITFLY_MODEL_DIR=str(directory), PYTHONUNBUFFERED="1")
    watchdog = None
    message = ""
    try:
        for filename in ("circuit.json", "body_ids.npz", "layer0.npz", "layer1.npz", "layer2.npz"):
            shutil.copy2(BASE / filename, directory / filename)
        (directory / "run.json").write_text(json.dumps(meta))
        with (directory / "training.log").open("w") as log:
            process = subprocess.Popen([sys.executable, "-u", str(ROOT / "lab_train.py"), "--steps", str(steps), "--seed", str(seed)],
                                       cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            runtime.job_process = process
            # Bound a stalled backend even when stdout stops producing events.
            watchdog = threading.Timer(600, lambda: process.terminate() if process.poll() is None else None)
            watchdog.daemon = True
            watchdog.start()
            if runtime.job.get("status") == "cancelling":
                process.terminate()
            for line in process.stdout:
                log.write(line)
                log.flush()
                if runtime.job.get("status") == "cancelling":
                    continue
                if line.startswith("LAB_EVENT "):
                    event = json.loads(line[len("LAB_EVENT "):])
                    runtime.job = {**runtime.job, **event}
                match = re.search(r"step (\d+)/(\d+): validation MSE=([\d.]+)", line)
                if match:
                    history = list(runtime.job.get("history", []))
                    history.append([int(match[1]), float(match[3])])
                    runtime.job = {**runtime.job, "step": int(match[1]), "loss":float(match[3]), "history":history}
            code = process.wait()
        cancelled = runtime.job.get("status") == "cancelling"
        status = "cancelled" if cancelled else "complete" if code == 0 else "failed"
        meta["status"] = status
        message = "Model kaydedildi ve altı fizik testinde değerlendirildi." if status == "complete" else "İşlem durduruldu." if cancelled else "Deney tamamlanamadı; training.log kaydını incele."
    except Exception as exc:
        meta["status"] = "failed"
        message = str(exc)
    finally:
        if watchdog:
            watchdog.cancel()
        (directory / "run.json").write_text(json.dumps(meta, indent=2))
        runtime.job_process = None
        runtime.job = {**runtime.job, "status": meta["status"], "message":message}

@app.post("/api/train")
def train(body: TrainingRequest):
    with runtime.lock:
        if runtime.job.get("status") in {"training", "evaluating", "cancelling"}:
            raise HTTPException(409, "Bir deney zaten çalışıyor")
        run_id = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%f")
        directory = RUNS / run_id
        directory.mkdir()
        runtime.job = dict(id=run_id, status="training", steps=body.steps, step=0, seed=body.seed, history=[], started=time.time())
        threading.Thread(target=training_job, args=(directory,body.steps,body.seed), daemon=True).start()
    return runtime.job

@app.post("/api/train/cancel")
def cancel():
    with runtime.lock:
        if runtime.job.get("status") in {"training", "evaluating"}:
            runtime.job = {**runtime.job, "status":"cancelling"}
            if runtime.job_process and runtime.job_process.poll() is None:
                runtime.job_process.terminate()
    return runtime.job

app.mount("/assets", StaticFiles(directory=ROOT / "ui"), name="assets")

@app.get("/")
def index():
    return FileResponse(ROOT / "ui/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, access_log=False)
