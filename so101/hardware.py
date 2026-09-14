"""Host-side controller for isolated, read-only SO-101 commissioning workers."""
from collections import deque
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

from .hardware_contract import calibration, readiness


class DiagnosticProcess:
    def __init__(self, command, root, kind):
        self.kind=kind;self.latest={};self.received=0.;self.error=None
        self.started=time.monotonic()
        self.lock=threading.Lock();self.stopped=False
        self.process=subprocess.Popen(command,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                                      text=True,encoding='utf-8',errors='replace',bufsize=1)
        self.reader=threading.Thread(target=self._read,daemon=True);self.reader.start()

    def _read(self):
        try:
            while line:=self.process.stdout.readline(2_000_001):
                if len(line)>2_000_000:raise ValueError('Tanılama kaydı boyut sınırını aştı')
                record=json.loads(line)
                with self.lock:
                    if record.get('kind')=='error':self.error=record['error']
                    elif record.get('kind')==self.kind:
                        self.latest=record;self.received=time.monotonic()
        except (OSError,ValueError) as exc:
            with self.lock:self.error=str(exc)
            self.process.terminate()
        finally:self.process.stdout.close()

    def snapshot(self):
        with self.lock:
            alive=self.process.poll() is None
            age=time.monotonic()-self.received if self.received else None
            fresh=bool(alive and not self.error and age is not None and age<2)
            result=dict(self.latest,running=alive,fresh=fresh,age_ms=round(age*1000) if age is not None else None,
                        error=self.error or (None if alive or self.stopped else 'Tanılama sona erdi; yeniden bağlanabilirsin.'))
            if self.kind=='arm':result['connected']=fresh
            # A frozen frame must not look like live perception.
            if not fresh:result.pop('image',None)
            return result

    def stop(self):
        self.stopped=True
        if self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
        self.reader.join(timeout=1)


class HardwareLab:
    lease_seconds=15

    def __init__(self,root,calibration_root=None):
        self.root=Path(root)
        self.python=self.root/'.runtime/hardware-venv'/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
        self.calibration_root=Path(calibration_root) if calibration_root else Path.home()/'.cache/huggingface/lerobot/calibration/robots'
        self.lock=threading.RLock();self.processes={};self.selected=None
        self.last_poll=time.monotonic();self.events=deque(maxlen=20)
        self.shutdown=threading.Event();self.watchdog=None
        self.cached_inventory=dict(ports=[],versions={},cameras_opened=False,motors_opened=False)

    def start(self):
        if self.watchdog is None:
            self.watchdog=threading.Thread(target=self._watch,daemon=True);self.watchdog.start()

    def _watch(self):
        while not self.shutdown.wait(1):
            with self.lock:
                for worker in self.processes.values():
                    if worker.process.poll() is None and time.monotonic()-worker.started>=600:
                        worker.stop();self._event('10 dakikalık tanılama sınırına ulaşıldı; oturum kapatıldı.')
                if self.processes and time.monotonic()-self.last_poll>self.lease_seconds:
                    self.disconnect();self._event('Panelden güncelleme gelmedi; USB ve kamera oturumları kapatıldı.')

    def _event(self,note):self.events.append(dict(time=time.time(),note=note))

    def _command(self,*args):
        if not self.python.is_file():raise ValueError('Donanım ortamı eksik. Önce tools/setup_so101_hardware.py çalıştır.')
        return [str(self.python),'-u','-m','so101.hardware_worker',*map(str,args)]

    def calibrations(self):
        records=[]
        for role in ('so_follower','so101_follower'):
            for path in sorted((self.calibration_root/role).glob('*.json')):
                try:record=calibration(path)
                except (OSError,ValueError) as exc:record=dict(valid=False,errors=[str(exc)],sha256=None)
                records.append(dict(id=f'{role}/{path.name}',name=path.stem,path=str(path),**record))
        return records

    def inventory(self):
        # Enumerating serial device metadata does not open serial ports or cameras.
        try:
            result=subprocess.run(self._command('inventory'),cwd=self.root,capture_output=True,text=True,timeout=8,check=True)
            inv=json.loads(result.stdout.strip().splitlines()[-1])
            if inv.get('kind')!='inventory':raise ValueError('Geçersiz envanter yanıtı')
            with self.lock:self.cached_inventory=inv
        except (OSError,ValueError,subprocess.SubprocessError) as exc:
            with self.lock:self.cached_inventory=dict(ports=[],versions={},error=str(exc),cameras_opened=False,motors_opened=False)
        return self.state()

    def connect(self,port,calibration_id):
        with self.lock:
            if 'arm' in self.processes and self.processes['arm'].snapshot()['running']:
                raise ValueError('Önce mevcut motor tanılama oturumunu kapat.')
            self.inventory()
            if port not in {p['device'] for p in self.cached_inventory['ports']}:
                raise ValueError('Seçilen USB portu güncel envanterde yok.')
            saved=next((r for r in self.calibrations() if r['id']==calibration_id),None)
            if not saved or not saved['valid']:raise ValueError('Geçerli bir follower kalibrasyonu seç.')
            if 'arm' in self.processes:self.processes.pop('arm').stop()
            self.processes['arm']=DiagnosticProcess(self._command('arm','--port',port,'--calibration',saved['path'],
                '--sha',saved['sha256'],'--duration',600),self.root,'arm')
            self.selected=saved;self.last_poll=time.monotonic()
            self._event(f'Salt okuma tanılaması: {port} · kalibrasyon {saved["sha256"][:12]}')
            return self.state()

    def camera(self,role,index):
        if role not in ('wrist','top') or type(index) is not int or not 0<=index<=15:
            raise ValueError('Kamera rolü ve 0–15 arasında bir indeks gerekli.')
        with self.lock:
            for key,worker in self.processes.items():
                if key in ('wrist','top') and worker.snapshot()['running'] and worker.index==index:
                    raise ValueError('Bu kamera zaten bir önizlemede açık; önce onu durdur.')
            self.stop_camera(role)
            worker=DiagnosticProcess(self._command('camera','--role',role,'--camera-index',index,'--duration',600),self.root,'camera')
            worker.index=index;self.processes[role]=worker;self.last_poll=time.monotonic()
            self._event(f'Kamera önizlemesi: {role} · indeks {index}')
            return self.state()

    def stop_camera(self,role):
        if role not in ('wrist','top'):raise ValueError('Geçersiz kamera rolü')
        with self.lock:
            if worker:=self.processes.pop(role,None):worker.stop();self._event(f'Kamera kapatıldı: {role}')

    def disconnect(self):
        with self.lock:
            for worker in self.processes.values():worker.stop()
            self.processes.clear();self._event('Tanılama kapatıldı. Motor torkuna komut gönderilmedi.')

    def state(self):
        with self.lock:
            self.last_poll=time.monotonic()
            sessions={key:worker.snapshot() for key,worker in self.processes.items()}
            arm=sessions.get('arm',{});cameras={k:sessions.get(k,{}) for k in ('wrist','top')}
            choices=self.calibrations()
            saved=next((r for r in choices if self.selected and r['id']==self.selected['id']),None)
            saved=saved or (choices[0] if not self.selected and choices else None)
            if arm.get('connected') and (not saved or saved['sha256']!=arm.get('calibration_sha256')):
                arm=dict(arm,calibration_match=False,error='Kalibrasyon dosyası oturum sırasında değişti.')
            versions=self.cached_inventory.get('versions',{})
            environment_ready=self.python.is_file() and all(versions.get(name) for name in ('pyserial','feetech-servo-sdk','numpy','opencv-python-headless'))
            return dict(environment_ready=environment_ready,inventory=self.cached_inventory,
                calibrations=choices,selected_calibration=self.selected['id'] if self.selected else None,
                arm=arm,cameras=cameras,checks=readiness(saved,arm,cameras),events=list(self.events),
                mode='read_only',autonomous_ready=False,simulation_connected_to_hardware=False,
                note='Motor yürütmesi kapalı. Ana ekrandaki beyin ve hareket simülasyona bağlıdır.',
                session_limit_seconds=600,idle_timeout_seconds=self.lease_seconds)

    def close(self):
        self.shutdown.set();self.disconnect()
        if self.watchdog:self.watchdog.join(timeout=4)
