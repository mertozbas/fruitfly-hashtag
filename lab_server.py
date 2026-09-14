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
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from lab_tasks import TASKS, compatible

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "models/odor_navigation"
RUNS = ROOT / "models/lab_runs"
PORT = int(os.environ.get("FRUITFLY_PORT", "8766"))

class Runtime:
    def __init__(self):
        self.process = self.commands = self.states = None
        self.latest = {}
        self.job = {"status": "idle"}
        self.job_process = None
        self.lock = threading.Lock()
        self.sim_lock = threading.RLock()
        self.workers = {}
        self.behavior = 'odor'
        self.last_heartbeat = 0
    def control(self, command):
        with self.sim_lock:
            if not self.process or not self.process.is_alive():
                raise HTTPException(503, "Simülasyon işlemi çalışmıyor; yerel sunucuyu yeniden başlat.")
            try:
                self.commands.put_nowait(command)
                if command['op'] == 'pause':
                    self.workers[self.behavior]['paused'] = command['paused']
            except queue.Full:
                raise HTTPException(429, "Komut kuyruğu dolu")
    def read(self):
        with self.sim_lock:
            while True:
                try:
                    self.latest = self.states.get_nowait()
                    self.latest['behavior'] = self.behavior
                except queue.Empty:
                    break
            return self.latest

    def switch(self, behavior):
        with self.sim_lock:
            if behavior == self.behavior:
                return
            if behavior not in self.workers:
                current = self.read()
                selected = resolve_model(current.get('model', 'trained'))
                if not compatible(behavior, selected.get('task', 'odor')):
                    available = [m for m in models() if compatible(behavior, m.get('task', 'odor')) and not m.get('before')]
                    if not available:
                        if behavior == 'so101':
                            raise HTTPException(503, 'Önce yerel SO-101 eğitimini tamamla: docs/so101-local.md')
                        from task_circuit import initialize
                        initialize(behavior)
                        available = [m for m in models() if m.get('task') == behavior]
                    def rank(m):
                        e=m.get('evaluation') or {}
                        visual_accepted=behavior=='so101' and e.get('sensor')=='camera' and e.get('acceptance_passed') is True
                        return (visual_accepted,e.get('success_count',-1)/max(1,e.get('episodes',1)))
                    selected = max(available, key=rank)
                if behavior == 'flight':
                    from lab_flight import FlightProcess
                    if not (ROOT / 'flight/.venv/bin/python').exists() or not (ROOT / 'data/flybody/trained-fly-policies/flight/saved_model.pb').exists():
                        raise HTTPException(503, 'Uçuş kurulumu eksik: flight/README.md')
                    commands, states = queue.Queue(32), queue.Queue(2)
                    process = FlightProcess(commands, states, selected['path'], selected['id'])
                elif behavior == 'so101':
                    from so101.worker import simulate as robot_simulate
                    ctx = mp.get_context('spawn')
                    commands, states = ctx.Queue(32), ctx.Queue(2)
                    process = ctx.Process(target=robot_simulate, args=(commands,states,str(selected['path']),selected['id']), daemon=True)
                    process.start()
                else:
                    from lab_worker import simulate
                    ctx = mp.get_context('spawn')
                    commands, states = ctx.Queue(32), ctx.Queue(2)
                    process = ctx.Process(target=simulate, args=(commands, states, behavior, str(selected['path']), selected['id']), daemon=True)
                    process.start()
                self.workers[behavior] = dict(process=process, commands=commands, states=states, paused=False)
            target = self.workers[behavior]
            if not target['process'].is_alive():
                raise HTTPException(503, 'Simülasyon işlemi durdu; yerel sunucuyu yeniden başlat.')
            # Keep the inactive physics state, model and camera intact.
            self.read()
            self.commands.put({'op': 'pause', 'paused': True}, timeout=1)
            self.behavior = behavior
            self.process, self.commands, self.states = (target[k] for k in ('process', 'commands', 'states'))
            while True:
                try:
                    self.states.get_nowait()
                except queue.Empty:
                    break
            self.latest = dict(behavior=behavior, starting=True)
            self.commands.put({'op': 'pause', 'paused': target['paused']}, timeout=1)
            self.commands.put({'op': 'heartbeat'}, timeout=1)
            self.last_heartbeat = time.monotonic()

    def stop(self):
        for worker in self.workers.values():
            process, commands, states = (worker[k] for k in ('process', 'commands', 'states'))
            if process.is_alive():
                try:
                    commands.put({'op': 'shutdown'}, timeout=1)
                except queue.Full:
                    process.terminate()
                process.join(5)
            if process.is_alive():
                process.terminate()
                process.join(5)
            for channel in (commands, states):
                if hasattr(channel, 'cancel_join_thread'):
                    channel.cancel_join_thread()
                    channel.close()

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
            owner=record.get('owner_pid')
            if isinstance(owner,int) and owner>0:
                try:
                    os.kill(owner,0)
                    continue # A CLI job or another local server still owns it.
                except ProcessLookupError:pass
                except PermissionError:continue
            record["status"] = "interrupted"
            path.write_text(json.dumps(record, indent=2))
    ctx = mp.get_context("spawn")
    runtime.commands, runtime.states = ctx.Queue(32), ctx.Queue(2)
    runtime.process = ctx.Process(target=simulate, args=(runtime.commands, runtime.states), daemon=True)
    runtime.process.start()
    runtime.workers['odor'] = dict(process=runtime.process, commands=runtime.commands, states=runtime.states, paused=False)
    robot_models=[m for m in models() if m.get('task')=='so101' and not m.get('before')]
    default_task=os.environ.get('FRUITFLY_DEFAULT_TASK','so101' if robot_models else 'odor')
    if default_task!='odor':
        runtime.switch(default_task)
    try:
        yield
    finally:
        if runtime.job_process and runtime.job_process.poll() is None:
            runtime.job_process.terminate()
            runtime.job_process.wait(timeout=10)
        runtime.stop()

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
    records = [dict(id="trained", name="Başlangıç / yerelde eğitilmiş", task="odor", path=BASE / "trained.npz", training=training,
                    evaluation=evaluation["summary"]["trained"] if evaluation else None),
               dict(id="untrained", name="Eğitim öncesi", task="odor", before=True, path=BASE / "untrained.npz", training=None,
                    evaluation=evaluation["summary"]["untrained"] if evaluation else None)]
    for p in sorted(RUNS.glob("*/run.json"), reverse=True):
        meta = read_json(p)
        if meta.get("status") == "complete":
            task = meta.get('task', 'odor')
            records.append(dict(id=p.parent.name, name=meta.get('name') or f"{TASKS[task]['title']} / {meta['created'][11:19]}", task=task, path=p.parent / "trained.npz",
                                training=read_json(p.parent / "training.json"), evaluation=read_json(p.parent / "evaluation.json")))
            if task in {'avoidance','vision','terrain','so101'} and (p.parent / 'untrained.npz').exists():
                evaluation = read_json(p.parent / 'evaluation.json')
                records.append(dict(id=p.parent.name+'~before', name=f"{TASKS[task]['title']} / eğitim öncesi", task=task,
                    before=True, path=p.parent / 'untrained.npz', training=None,
                    evaluation=evaluation.get('controls', {}).get('untrained') if evaluation else None))
    from task_circuit import circuit_directory
    for task in ('avoidance','vision','terrain'):
        path = circuit_directory(task) / 'untrained.npz'
        if path.exists():
            records.append(dict(id=task+'-baseline', name=TASKS[task]['title']+' / eğitilmemiş',
                task=task, before=True, path=path, training=None, evaluation=None))
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
                   *[dict(id=t, title=TASKS[t]['title'], status="experimental", detail=TASKS[t]['sensor']+' → '+TASKS[t]['motor']) for t in ('avoidance','vision','terrain')],
                   dict(id="flight", title="Beyin ile uçuş", status="connected", detail="MaleCNS koku kararı → yön hedefi → FlyBody kanat kontrolü. Canlı 7.075 nöron; yönelme eğitimi ve uçuş testleri."),
                   dict(id="so101",title=TASKS['so101']['title'],status="experimental",detail=TASKS['so101']['sensor'])])

@app.get("/api/state")
def state():
    with runtime.sim_lock:
        now = time.monotonic()
        if now - runtime.last_heartbeat > 5 and runtime.process.is_alive():
            runtime.control({"op": "heartbeat"})
            runtime.last_heartbeat = now
        return dict(simulation=runtime.read(), job=runtime.job, alive=runtime.process.is_alive())

@app.get("/api/graph")
def graph(model: str = "trained"):
    from lab_graph import prepare
    return FileResponse(prepare(directory=resolve_model(model)['path'].parent))

@app.get("/api/anatomy")
def anatomy():
    return FileResponse(ROOT / "artifacts/lab/anatomy.json")

@app.get("/api/anatomy/segments")
def anatomy_segments():
    return FileResponse(ROOT / "artifacts/lab/anatomy.f32", media_type="application/octet-stream")

@app.get("/api/neuron/{body_id}")
def neuron_details(body_id: int, model: str = "trained"):
    from lab_details import neuron
    try:
        return neuron(body_id, resolve_model(model)['path'].parent)
    except KeyError as exc:
        raise HTTPException(404, str(exc))

@app.get("/api/neuron/{body_id}/connections")
def neuron_connections(body_id: int, direction: Literal["in", "out"] = "out",
                       page: int = Query(0, ge=0, le=100000), limit: int = Query(12, ge=1, le=50), model: str = "trained"):
    from lab_details import connections
    try:
        return connections(body_id, direction, page, limit, resolve_model(model)['path'].parent)
    except KeyError as exc:
        raise HTTPException(404, str(exc))

@app.get("/api/connection/{source}/{target}")
def connection_details(source: int, target: int, model: str = "trained"):
    from lab_details import connection
    record = None if model == 'flight-pretrained' else resolve_model(model)
    try:
        return connection(source, target, record["path"] if record else None)
    except KeyError as exc:
        raise HTTPException(404, str(exc))

@app.get("/api/model/{model_id}")
def model_details(model_id: str):
    if model_id == 'flight-pretrained':
        from lab_flight import metadata
        return metadata()
    import numpy as np
    record = resolve_model(model_id)
    from lab_graph import prepare
    graph = read_json(prepare(directory=record['path'].parent))
    with np.load(record["path"], allow_pickle=False) as weights:
        w = weights["weight"]
        learned_weights={2:w,**{i:weights[f'weight{i}'] for i in range(2) if f'weight{i}' in weights}}
        gains = [float(learned_weights[e['layer']][e["row"],e["col"]] / e["weight"]) if e["layer"] in learned_weights else 1. for e in graph["edges"]]
        input_sums=None
        robot_adapter=None
        if record.get('task')=='so101':
            from odor_policy import Circuit
            circuit=Circuit(record['path'].parent)
            input_sums=[np.asarray(learned_weights.get(i,layer).sum(axis=0)).ravel().tolist() for i,layer in enumerate(circuit.layers)]
            robot_adapter=dict(external_observations=30,learned_memory=8 if 'memory_weight' in weights else 0,
                learned_motor_heads=int(weights['motor_heads']) if 'motor_heads' in weights else 1,
                progress_supervision=bool(weights['progress_supervision']) if 'progress_supervision' in weights else False,
                motor_phase_feedback=bool(weights['motor_phase_feedback']) if 'motor_phase_feedback' in weights else False,
                trainable_anatomical_layers=sorted(learned_weights),
                learned_transition_support=bool(np.any(weights['transition_counts'])) if 'transition_counts' in weights else False,
                active_external_features=np.flatnonzero(weights['input_mask'][:30]).tolist() if 'input_mask' in weights else list(range(30)),
                action_mode=str(weights['action_mode']) if 'action_mode' in weights else 'delta',
                outputs=['x','y','z','gripper'],teacher_in_rollout=False)
    sha = hashlib.sha256(record['path'].read_bytes()).hexdigest()
    evaluation_task = record.get('task', 'odor')
    flight_evaluation = record['evaluation'] if evaluation_task=='flight' else read_json(ROOT / 'artifacts/lab/flight/checkpoints' / f'{sha}.json')
    return dict(id=model_id, graph_version=graph["version"], circuit_identity=graph["circuit_identity"],
                task=evaluation_task, groups=graph['groups'], before=record.get('before', False), input_sums=input_sums,robot_adapter=robot_adapter,
                gains=gains, sha256=sha, training=record["training"], evaluation=record["evaluation"],
                evaluation_task=evaluation_task, flight_evaluation=flight_evaluation,
                walk_evaluation=record['evaluation'] if evaluation_task!='flight' else None)

@app.get("/api/model/{model_id}/export")
def export_model(model_id: str):
    from brain_export import archive
    record = resolve_model(model_id)
    if record.get('task')=='so101':
        from so101.export import archive
    return Response(archive(record['path']), media_type='application/zip',
                    headers={'Content-Disposition':f'attachment; filename="{model_id}-inference.zip"'})

class Control(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    op: Literal["pause", "reset", "model", "camera", "behavior", "next", "sensor", "loop"]
    behavior: Literal['odor', 'flight', 'avoidance', 'vision', 'terrain', 'so101'] = 'odor'
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
    sensor: Literal['state','camera'] = 'state'
    enabled: bool = True

@app.post("/api/control")
def control(body: Control):
    # Serialize mode selection with commands; none can reach the wrong worker.
    with runtime.sim_lock:
        return apply_control(body)

def apply_control(body):
    if body.op == 'behavior':
        runtime.switch(body.behavior)
        return {'accepted': True, 'behavior': runtime.behavior}
    if body.op == 'next':
        if runtime.behavior not in {'flight','so101'}:
            raise HTTPException(409, 'Sonraki bölüm bu davranışta kullanılamaz.')
        runtime.control({'op': 'next'})
        return {'accepted': True}
    if body.op=='sensor':
        if runtime.behavior!='so101':raise HTTPException(409,'Sensör seçimi SO-101 için kullanılabilir.')
        runtime.control(dict(op='sensor',sensor=body.sensor))
        return {'accepted': True}
    if body.op=='loop':
        if runtime.behavior!='so101':raise HTTPException(409,'Görev döngüsü SO-101 için kullanılabilir.')
        runtime.control(dict(op='loop',enabled=body.enabled))
        return {'accepted': True}
    if body.op == "model":
        m = resolve_model(body.model)
        if not compatible(runtime.behavior, m.get('task', 'odor')):
            raise HTTPException(409, 'Model başka bir göreve ait. Önce ilgili davranışı seç.')
        command = dict(op="model", path=str(m["path"]), id=body.model)
    elif body.op == "reset":
        if runtime.behavior=='so101':
            if not (125<=body.goal[0]<=160 and -180<=body.goal[1]<=-135):
                raise HTTPException(422,'SO-101 kutu merkezi: X 125–160 mm, Y −180…−135 mm')
        elif not all(-30 <= x <= 30 for x in body.goal):
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
    task: Literal['odor', 'flight', 'avoidance', 'vision', 'terrain', 'so101'] = 'odor'

def training_job(directory, steps, seed, task, initial_model=None, sensor='state'):
    meta = dict(id=directory.name, status="training", created=datetime.now(timezone.utc).isoformat(), steps=steps, seed=seed, task=task,owner_pid=os.getpid())
    env = dict(os.environ, FRUITFLY_MODEL_DIR=str(directory), PYTHONUNBUFFERED="1")
    watchdog = None
    message = ""
    try:
        if task=='so101':
            from so101.policy import prepare
            prepare(directory)
        else:
            from task_circuit import build
            source = build(task)
            for filename in ("circuit.json", "body_ids.npz", "layer0.npz", "layer1.npz", "layer2.npz"):
                shutil.copy2(source / filename, directory / filename)
        (directory / "run.json").write_text(json.dumps(meta))
        with (directory / "training.log").open("w") as log:
            command=([sys.executable,'-u','-m','so101.train_job','--output',str(directory),'--steps',str(steps),'--seed',str(seed)]
                     if task=='so101' else [sys.executable, "-u", str(ROOT / "lab_train.py"), "--steps", str(steps), "--seed", str(seed), '--task', task])
            if task=='so101' and initial_model is not None:command.extend(['--resume',str(initial_model)])
            if task=='so101':command.extend(['--sensor',sensor])
            process = subprocess.Popen(command,
                                       cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            runtime.job_process = process
            # Bound a stalled backend even when stdout stops producing events.
            watchdog = threading.Timer((3600 if sensor=='camera' else 1800) if task=='so101' else 600, lambda: process.terminate() if process.poll() is None else None)
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
        message = "Model kaydedildi; fizik sonuçları ve varsa çıkış kapatma kontrolü raporda." if status == "complete" else "İşlem durduruldu." if cancelled else "Deney tamamlanamadı; training.log kaydını incele."
        if status=='complete' and task=='so101':
            result=read_json(directory/'evaluation.json') or {}
            meta['acceptance_passed']=result.get('acceptance_passed',False)
            message=f"Fizik testi: {result.get('success_count',0)} / {result.get('episodes',100)}. "+('Kabul ölçütü geçti. ' if meta['acceptance_passed'] else 'Kabul ölçütü henüz geçmedi. ')
            if result.get('recovery_evaluation'):
                r=result['recovery_evaluation'];message+=f"Küp düşürme: {r['success_count']} / {r['episodes']}. "
            if result.get('selected_model_changed') is False:message+='Yeni adaylar iyileştirmedi; önceki model korundu.'
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
        if body.task=='flight' and not (ROOT / 'flight/.venv/bin/python').exists():
            raise HTTPException(503, 'Önce uçuş ortamını kur.')
        run_id = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%f")
        directory = RUNS / run_id
        directory.mkdir()
        runtime.job = dict(id=run_id, status="training", steps=body.steps, step=0, seed=body.seed, task=body.task, history=[], started=time.time())
        initial_model=None;sensor='state'
        if body.task=='so101':
            current=runtime.read()
            if current.get('behavior')=='so101' and current.get('model'):
                sensor=current.get('robot',{}).get('sensor_mode','state')
                candidate=resolve_model(current['model'])
                from so101.policy import Policy
                if Policy(candidate['path']).action_mode=='target':initial_model=candidate['path']
        threading.Thread(target=training_job, args=(directory,body.steps,body.seed,body.task,initial_model,sensor), daemon=True).start()
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
app.mount("/guide", StaticFiles(directory=ROOT / "docs", html=True), name="guide")

@app.get("/LICENSE")
def license_text():
    return FileResponse(ROOT / "LICENSE", media_type="text/plain")

@app.get("/ui/vendor/THREE-LICENSE.txt")
def vendor_license():
    return FileResponse(ROOT / "ui/vendor/THREE-LICENSE.txt", media_type="text/plain")

@app.get("/")
def index():
    return FileResponse(ROOT / "ui/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, access_log=False)
