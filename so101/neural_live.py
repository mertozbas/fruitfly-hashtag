"""Local, finite physical neural-control sessions and their live display.

Run with the hardware venv. The existing Neural Lab supplies USB camera frames.
Starting this process only reads motors. Holding and motion are separate actions.
"""
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import queue
import signal
import threading
import time
import urllib.request
import uuid

import cv2
import numpy as np

from odor_policy import Policy
from .alignment_probe import ProbeBus
from .calibration_contract import atomic_json
from .hardware_contract import calibration
from .neural_control import NeuralMotion, NeuralPanBus, telemetry, read_telemetry, recording_telemetry, visual_command
from .pose_hold import HoldBus, hold_current
from .physical_driver import PhysicalBus
from .physical_contract import limits,MAX_RECORD_SECONDS,MAX_SAMPLES
from .teaching import TeachingRecorder,latest_teaching
from .body_control import BodyBus,BodyMotion,MAX_TRACKING_LEAD
from .gripper_control import GripperBus,GripperOpening

ROOT = Path(__file__).resolve().parents[1]


class NeuralLab:
    def __init__(self, args):
        self.args=args;self.lock=threading.Lock();self.commands=queue.Queue(4)
        self.shutdown=threading.Event();self.stop_requested=threading.Event()
        self.last_view=0.;self.motion=None;self.bus=None;self.used=set()
        self.recorder=None
        self.teach_thread=None;self.teach_done=threading.Event();self.teach_fault=None
        self.session=uuid.uuid4().hex
        self.directory=ROOT/'.runtime/hardware/neural'/self.session
        self.directory.mkdir(parents=True)
        self.model_sha=hashlib.sha256(Path(args.model).read_bytes()).hexdigest()
        self.policy=Policy(args.model)
        if self.policy.task!='vision':raise ValueError('Görsel devre modeli gerekli')
        self.saved=calibration(args.calibration)
        if not self.saved['valid']:raise ValueError('Geçersiz follower kalibrasyonu')
        self.state=dict(stage='connecting',session=self.session,brain_connected=False,
                        model_sha256=self.model_sha,circuit_sha256=self.policy.circuit.identity,
                        group_order=list(self.policy.circuit.groups),span_counts=170,
                        message='Kamera ve motorlar okunuyor.',run_commands=0)
        previous=latest_teaching(self.directory.parent,args.serial,self.saved['sha256'])
        if previous:self.state['teaching']=previous
        self.cameras={};self.last_report=None;self.sequence=0;self.last_verify=0.
        self.camera_retries=0;self.next_camera_retry=0.;self.camera_healthy_since=None

    def api(self, path, data=None):
        request=urllib.request.Request(self.args.source+path,
            data=None if data is None else json.dumps(data).encode(),
            headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=.25 if data is None else 5) as response:
            return json.load(response)

    def start_cameras(self):
        state=self.api('/api/hardware/state')
        for role,index in (('top',self.args.top),('wrist',self.args.wrist)):
            camera=state['cameras'].get(role,{})
            if camera.get('running') and camera.get('index')!=index:
                raise ValueError(f'{role}: başka kamera oturumu açık')
            if not camera.get('running'):
                self.api('/api/hardware/camera',dict(role=role,index=index))

    def frames(self):
        state=self.api('/api/hardware/state')
        cameras=state['cameras']
        for role in ('top','wrist'):
            c=cameras.get(role,{})
            if (not c.get('fresh') or not c.get('image') or c.get('age_ms',9999)>.4*1000
                    or not 0<=time.time()-c.get('wall_time',0)<=.4):
                raise ValueError(f'{role}: güncel kamera görüntüsü yok')
            if (c.get('width'),c.get('height'))!=(1280,720):
                raise ValueError('1280×720 kamera görüntüsü gerekli')
        self.cameras=cameras
        return cameras

    def recover_cameras(self, now=None):
        """Renew expired read-only previews while viewed; never resume motion."""
        now=time.monotonic() if now is None else now
        self.camera_healthy_since=None
        if (self.motion is not None or now-self.last_view>1.
                or now<self.next_camera_retry or self.camera_retries>=3):
            return False
        self.camera_retries+=1
        self.next_camera_retry=now+(3,6,12)[self.camera_retries-1]
        self.publish(camera_retries=self.camera_retries,
                     message=f'Kamera yeniden bağlanıyor ({self.camera_retries}/3). Hareket duruyor.')
        self.start_cameras()
        return True

    def identity(self):
        from serial.tools import list_ports
        item=next((p for p in list_ports.comports() if p.device==self.args.port),None)
        if item is None or item.serial_number!=self.args.serial:
            raise ValueError('USB follower kimliği değişti')
        current=calibration(self.args.calibration)
        if not current['valid'] or current['sha256']!=self.saved['sha256']:
            raise ValueError('Kalibrasyon dosyası değişti')
        if hashlib.sha256(Path(self.args.model).read_bytes()).hexdigest()!=self.model_sha:
            raise ValueError('Beyin modeli değişti')

    def publish(self, **changes):
        with self.lock:self.state.update(changes)

    def snapshot(self, heartbeat=False):
        with self.lock:
            if heartbeat:self.last_view=time.monotonic()
            return dict(self.state)

    def submit(self, body):
        if body.get('op')=='stop':
            self.stop_requested.set()
            while True:
                try:self.commands.get_nowait()
                except queue.Empty:break
            return
        if body.get('op') not in ('hold','run','cameras','teach_start','teach_stop','joints','gripper_open'):
            raise ValueError('Geçersiz işlem')
        if body.get('op') in ('hold','run','teach_start','teach_stop','joints','gripper_open'):
            state=self.snapshot()
            if body.get('session')!=self.session or body.get('preview')!=state.get('preview'):
                raise ValueError('Önizleme değişti; ekranı yenile')
            if body.get('confirmed') is not True:raise ValueError('Fiziksel hazırlığı doğrula')
            body=dict(body,expected=state.get('q'),created=time.monotonic(),
                      cameras={k:v['session'] for k,v in self.cameras.items()})
        self.commands.put_nowait(body)

    def reopen(self):
        self.bus=ProbeBus(self.args.port);self.bus.open();self.bus.verify(self.saved['motors'])

    def check_live(self, expected_cameras):
        if self.stop_requested.is_set() or self.shutdown.is_set():raise ValueError('Durduruldu')
        if time.monotonic()-self.last_view>1.:raise ValueError('Kontrol ekranı bağlantısı kesildi')
        for role,c in self.cameras.items():
            if c['session']!=expected_cameras.get(role) or not 0<=time.time()-c['wall_time']<=.4:
                raise ValueError('Kamera değişti veya gecikti')

    def finish(self, note):
        errors=[]
        if self.recorder:
            self.end_teaching(note);return
        if self.motion:
            try:self.motion.stop()
            except Exception as exc:errors.append(str(exc))
            self.motion=None;self.bus=None
        elif not any(row.get('torque') for row in self.state.get('motors',[])):
            note='Durduruldu. Motorlar serbest; kolu desteklemeye devam et.'
        self.publish(stage='stopped',message=note,brain_connected=False,preview=uuid.uuid4().hex,
                     stop_errors=errors,torque_note='Gövde torku tutulur. Serbest bırakmadan önce kolu destekle.')
        atomic_json(self.directory/'result.json',self.snapshot())

    def end_teaching(self, reason=None):
        if self.recorder is None:raise ValueError('Etkin gösterim kaydı yok')
        self.teach_done.set()
        if self.teach_thread:
            self.teach_thread.join(timeout=2)
            if self.teach_thread.is_alive():raise ValueError('Enkoder kaydının kapanması bekleniyor; kol serbest')
        reason=reason or self.teach_fault
        result=self.recorder.finish(reason);self.recorder=None
        self.publish(teaching=result,stage='taught' if result['valid'] else 'teaching_interrupted',
                     message=('Gösterim kaydedildi. Kol hâlâ serbest; desteklemeye devam et. Destekli pozu tut düğmesine bas.'
                              if result['valid'] else 'Gösterim kesildi. Kol serbest; desteklemeye devam et.'),
                     brain_connected=False,preview=uuid.uuid4().hex)

    def record_joints(self):
        """Own the read-only serial bus while teaching, independent of camera HTTP."""
        try:
            while not self.teach_done.is_set() and not self.shutdown.is_set():
                start=time.monotonic()
                if start-self.recorder.started>=MAX_RECORD_SECONDS or len(self.recorder.points)>=MAX_SAMPLES:
                    self.teach_done.set();break
                q,rows,warnings=recording_telemetry(self.bus,self.saved['motors'])
                state=self.snapshot()
                status=self.recorder.append(q,self.cameras,state.get('decision',{'sensor_values':[0.,0.]}),rows,warnings)
                self.publish(q=q,motors=rows,teaching=status,wall_time=time.time(),motor_wall_time=time.time())
                self.teach_done.wait(max(0,.05-(time.monotonic()-start)))
        except Exception as exc:
            self.teach_fault=str(exc);self.teach_done.set()

    def action(self, command):
        op=command['op']
        if op=='teach_stop':
            self.end_teaching();return
        if getattr(self,'recorder',None):raise ValueError('Önce gösterim kaydını bitir; kolu desteklemeye devam et')
        if op=='cameras':
            if self.motion:raise ValueError('Önce hareketi durdur')
            self.camera_retries=0;self.next_camera_retry=0.;self.camera_healthy_since=None
            self.start_cameras();return
        if self.motion:raise ValueError('Oturum zaten çalışıyor')
        token=command['preview']
        if token in self.used or time.monotonic()-command['created']>20:
            raise ValueError('Önizleme süresi doldu veya kullanıldı')
        self.used.add(token);self.publish(preview=uuid.uuid4().hex,action_error=None)
        self.stop_requested.clear();self.identity()
        self.check_live(command['cameras'])
        if op=='teach_start':q,_,_=read_telemetry(self.bus,self.saved['motors'])
        else:q,_=telemetry(self.bus,self.saved['motors'])
        if op!='teach_start' and any(abs(a-b)>3 for a,b in zip(q,command['expected'])):
            raise ValueError('Kol önizlemeden sonra değişti')
        self.bus.close();self.bus=None
        self.publish(preview=uuid.uuid4().hex)
        if op=='teach_start':
            self.publish(stage='teaching_preparing',message='Kolu desteklemeye devam et; motorlar serbest bırakılıyor.')
            bus=PhysicalBus(self.args.port)
            try:
                bus.open();bus.verify(self.saved['motors']);self.check_live(command['cameras'])
                bus.release()
                q,rows,_=recording_telemetry(bus,self.saved['motors'])
                if any(row['torque'] for row in rows):raise ValueError('Motorların tamamı serbest bırakılamadı')
            except Exception:
                self.publish(stage='teaching_interrupted',message='Serbest bırakma tamamlanamadı. Kolu desteklemeye devam et.')
                raise
            finally:bus.close()
            self.reopen()
            self.recorder=TeachingRecorder(self.directory/f'teaching-{token}',limits(self.saved['motors']),
                dict(calibration_sha256=self.saved['sha256'],serial_number=self.args.serial,
                     vision_model_sha256=self.model_sha,cameras=command['cameras']))
            self.publish(stage='teaching',message='KAYIT · Kol serbest. Kolu sürekli destekleyerek küpe uzan, kıskacı elle kapat ve küpü kaldır.',
                         teaching=dict(active=True,samples=0,seconds=0,seconds_left=90),brain_connected=False)
            self.teach_fault=None;self.teach_done.clear()
            self.teach_thread=threading.Thread(target=self.record_joints,daemon=True)
            self.teach_thread.start()
        elif op=='hold':
            self.publish(stage='preparing',message='Yalnız okunan mevcut poz tutuluyor.')
            def check():
                self.frames();self.check_live(command['cameras'])
            report=hold_current(HoldBus(self.args.port),self.saved['motors'],q,check,
                lambda r:atomic_json(self.directory/f'hold-{token}.json',r))
            if report['status']!='holding_at_measured_pose':
                raise ValueError(report.get('error','Tutma doğrulanamadı'))
            self.publish(stage='holding',message='Mevcut poz tutuluyor. Desteği yavaşça çek; alan boşken beyni başlat.')
            self.reopen()
        elif op=='gripper_open':
            motion=GripperOpening(GripperBus(self.args.port),self.saved['motors'],q,command.get('target'),
                empty_gripper=command.get('empty_gripper'),check_live=lambda:self.check_live(command['cameras']))
            self.motion=motion;self.run_cameras=command['cameras']
            atomic_json(self.directory/f'gripper-opening-{token}.json',dict(initial=q,target=command.get('target'),
                calibration_sha256=self.saved['sha256'],serial_number=self.args.serial,cameras=command['cameras'],
                empty_gripper=True,max_seconds=15,max_delta_counts=128,max_tracking_lead=8,torque_cap=100,
                controller='empty_gripper_opening',brain_connected=False))
            motion.start()
            self.publish(stage='running',controller='empty_gripper_opening',
                message='Boş kıskaç düşük torkla açılıyor. Gövde mevcut pozu koruyor.',
                run_commands=0,run_started=time.time(),brain_connected=False)
        elif op=='joints':
            motion=BodyMotion(BodyBus(self.args.port),self.saved['motors'],q,command.get('target'),
                              thermal_pause_review=command.get('thermal_pause_review'))
            self.motion=motion;self.run_cameras=command['cameras']
            atomic_json(self.directory/f'positioning-{token}.json',dict(initial=q,target=command.get('target'),
                calibration_sha256=self.saved['sha256'],serial_number=self.args.serial,
                cameras=command['cameras'],max_seconds=30,max_delta_counts=170,
                max_tracking_lead=MAX_TRACKING_LEAD,
                thermal_pause_review=command.get('thermal_pause_review'),
                controller='bounded_joint_positioning',brain_connected=False))
            motion.start()
            self.publish(stage='running',controller='bounded_joint_positioning',
                         message='Omuz, dirsek ve bilek: sınırlı konumlandırma. Kıskaç serbest kalır.',
                         run_commands=0,run_started=time.time(),brain_connected=False)
        else:
            motion=NeuralMotion(NeuralPanBus(self.args.port),self.saved['motors'],q)
            self.motion=motion;self.run_cameras=command['cameras']
            atomic_json(self.directory/f'plan-{token}.json',dict(q=q,cameras=command['cameras'],
                model_sha256=self.model_sha,calibration_sha256=self.saved['sha256'],
                serial_number=self.args.serial,max_seconds=30,span_counts=170,
                controller='anatomical_visual_base_steering',operator_workspace_confirmed=True))
            motion.start()
            self.publish(stage='running',controller='anatomical_visual_base_steering',message='Beyin kameradan tabana komut veriyor; en fazla 30 saniye.',
                         run_commands=0,run_started=time.time(),brain_connected=False)

    def observe_motors(self):
        """Idle motor observation must remain available during camera outages."""
        if self.motion is not None or self.recorder is not None:return
        if self.bus is None:self.reopen()
        q,rows,elapsed=read_telemetry(self.bus,self.saved['motors'])
        stamp=time.time()
        self.publish(q=q,motors=rows,motor_wall_time=stamp,motor_read_seconds=elapsed)
        hot=[row for row in rows if row['temperature_c']>=50]
        if hot:self.publish(last_motor_warning=dict(wall_time=stamp,motors=hot))

    def loop(self):
        try:
            self.identity();self.reopen();self.start_cameras()
            self.publish(stage='observing',preview=uuid.uuid4().hex)
            with (self.directory/'decisions.jsonl').open('a') as log:
                while not self.shutdown.is_set():
                    start=time.monotonic()
                    try:
                        if self.recorder and self.teach_done.is_set():self.end_teaching(self.teach_fault)
                        if self.stop_requested.is_set():
                            self.finish('Durduruldu. Mevcut poz tutuluyor.');self.stop_requested.clear()
                        command=self.commands.get_nowait() if not self.commands.empty() else None
                        if command and command['op'] in ('cameras','teach_stop'):
                            self.action(command);command=None
                        self.observe_motors()
                        try:cameras=self.frames()
                        except (OSError,ValueError):
                            # A camera outage first ends any motion. Reopening a
                            # preview does not recreate the single-use run plan.
                            if self.motion:self.finish('Kamera kesildi; hareket durdu.')
                            self.recover_cameras()
                            raise
                        if self.camera_healthy_since is None:self.camera_healthy_since=start
                        if start-self.camera_healthy_since>=5 and self.camera_retries:
                            self.camera_retries=0;self.next_camera_retry=0.
                            self.publish(camera_retries=0)
                            if self.motion is None and self.recorder is None:
                                self.publish(message='Kameralar canlı. Hareket için yeniden başlatma gerekir.')
                        raw=base64.b64decode(cameras['top']['image'].split(',')[-1],validate=True)
                        bgr=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
                        if bgr is None:raise ValueError('Kamera görüntüsü çözülemedi')
                        decision=visual_command(self.policy,cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB))
                        if self.bus is None and self.motion is None:self.reopen()
                        if command:
                            try:self.action(command)
                            except Exception as exc:
                                self.publish(action_error=str(exc))
                                raise
                        if self.motion:
                            if time.monotonic()-self.last_verify>1.:
                                self.identity();self.motion.bus.verify(self.saved['motors'])
                                self.last_verify=time.monotonic()
                            self.check_live(self.run_cameras)
                            step=self.motion.step(decision['drive'],decision['visible'],
                                time.monotonic()-self.last_view,time.time()-cameras['top']['wall_time'])
                            self.publish(**step,motor_wall_time=time.time(),brain_connected=getattr(self.motion,'brain_driven',True) and self.motion.commands>0,
                                run_commands=self.motion.commands,seconds_left=max(0,self.motion.duration-(time.monotonic()-self.motion.started)))
                            if isinstance(self.motion,BodyMotion) and self.motion.thermal_review is not None:
                                self.publish(message=('Sıcaklık uyarısı: poz tutuluyor; kararlı düşük ölçüm bekleniyor.'
                                    if step['thermal_paused'] else 'Sınırlı kamera ölçümü konumlandırması.'))
                            record=dict(time=time.time(),**step,decision=decision,
                                        frame={k:cameras['top'][k] for k in ('session','sequence','wall_time')},
                                        input_image_sha256=hashlib.sha256(raw).hexdigest())
                            log.write(json.dumps(record,allow_nan=False)+'\n');log.flush()
                            if step.get('complete'):self.finish('Konumlandırma tamamlandı. Mevcut poz tutuluyor.')
                        self.sequence+=1
                        self.publish(decision=decision,wall_time=time.time(),sequence=self.sequence,
                                     images={k:c['image'] for k,c in cameras.items()},error=None,
                                     camera_wall_time=cameras['top']['wall_time'])
                    except Exception as exc:
                        if self.motion:self.finish(str(exc))
                        self.publish(error=str(exc),last_error=str(exc),brain_connected=False)
                    self.shutdown.wait(max(0,.1-(time.monotonic()-start)))
        except Exception as exc:self.publish(stage='failed',error=str(exc))
        finally:
            if self.recorder:self.end_teaching('Program kapandı; kayıt kesildi')
            if self.motion:self.finish('Program kapandı; hareket durdu.')
            if self.bus:self.bus.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True);parser.add_argument('--serial',required=True)
    parser.add_argument('--calibration',required=True)
    parser.add_argument('--model',default=str(ROOT/'models/lab_runs/local-vision-seed42/trained.npz'))
    parser.add_argument('--source',default='http://127.0.0.1:8766')
    parser.add_argument('--listen',type=int,default=8767)
    parser.add_argument('--top',type=int,default=0);parser.add_argument('--wrist',type=int,default=1)
    args=parser.parse_args();lab=NeuralLab(args)
    origin=f'http://127.0.0.1:{args.listen}'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def respond(self,value,status=200,kind='application/json'):
            data=json.dumps(value,allow_nan=False).encode() if kind=='application/json' else value
            self.send_response(status);self.send_header('Content-Type',kind)
            self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)))
            self.end_headers()
            try:self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):pass
        def allowed(self):
            return self.headers.get('Host')==f'127.0.0.1:{args.listen}'
        def do_GET(self):
            if not self.allowed():return self.respond({'error':'local host required'},403)
            if self.path=='/':
                self.send_response(302);self.send_header('Location',lab.args.source+'/?physical=1')
                self.send_header('Content-Length','0');self.end_headers();return
            if self.path=='/state':
                # A page that is open and polling acts as the one-second lease.
                return self.respond(lab.snapshot(heartbeat=self.headers.get('X-Neural-Session')==lab.session))
            self.respond({'error':'not found'},404)
        def do_POST(self):
            if not self.allowed() or self.headers.get('Origin')!=origin:
                return self.respond({'error':'same-origin control required'},403)
            try:
                length=int(self.headers.get('Content-Length','0'))
                if self.path!='/command' or not 1<=length<=4096:raise ValueError('Geçersiz istek')
                lab.submit(json.loads(self.rfile.read(length)))
                self.respond({'accepted':True})
            except (ValueError,queue.Full) as exc:self.respond({'error':str(exc)},409)
    server=ThreadingHTTPServer(('127.0.0.1',args.listen),Handler)
    thread=threading.Thread(target=lab.loop,daemon=True);thread.start()
    def stop(*_):
        lab.stop_requested.set();lab.shutdown.set()
        threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    print(f'Fiziksel beyin ekranı: {origin} (başlangıç salt okuma)',flush=True)
    try:server.serve_forever(poll_interval=.1)
    finally:
        lab.stop_requested.set();lab.shutdown.set();thread.join(timeout=5);server.server_close()


if __name__=='__main__':main()
