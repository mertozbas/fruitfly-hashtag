"""Session ownership and server-resolved calibration paths; no SDK imports."""
import json
from pathlib import Path
import re
import time
import uuid
from .calibration_contract import TERMINAL


class Commissioning:
    def __init__(self,hardware):
        self.hardware=hardware;self.root=hardware.root/'.runtime/hardware';self.last_heartbeat=0

    def histories(self):
        rows=[]
        for path in self.root.glob('motors/*/backup.json'):
            try:
                backup=json.loads(path.read_text());status=json.loads((path.parent/'status.json').read_text()) if (path.parent/'status.json').exists() else {}
                rows.append(dict(id=path.parent.name,target=Path(backup['target']).name,created=backup['created'],stage=status.get('stage','interrupted'),
                    warning=status.get('warning'),recovery_needed=status.get('stage') not in {'saved','restored','cancelled'}))
            except (ValueError,OSError,KeyError):continue
        return sorted(rows,key=lambda r:r['created'],reverse=True)[:30]

    def camera_profiles(self):
        rows=[]
        for path in self.root.glob('cameras/*/*/calibration.json'):
            try:
                record=json.loads(path.read_text())
                rows.append(dict(id=f'{path.parent.parent.name}/{path.parent.name}',role=record['role'],device_label=record['device_label'],size=record['size'],rms_px=record['rms_px'],created=record['created']))
            except (OSError,ValueError,KeyError):continue
        return sorted(rows,key=lambda r:r['created'],reverse=True)[:30]

    def active(self):
        worker=self.hardware.processes.get('calibration')
        return bool(worker and worker.snapshot().get('running'))

    def start(self,port,robot_id,calibration_id=None,backup_id=None):
        from .hardware import DiagnosticProcess
        h=self.hardware
        with h.lock:
            if self.active():raise ValueError('Bir kalibrasyon oturumu zaten açık')
            h.inventory();device=next((p for p in h.cached_inventory['ports'] if p['device']==port),None)
            if not device:raise ValueError('Kol bağlı değil; önce USB envanterini yenile')
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',robot_id):raise ValueError('Profil adı 1–64 harf, rakam, alt çizgi veya tire içermeli')
            if calibration_id:
                selected=next((r for r in h.calibrations() if r['id']==calibration_id),None)
                if not selected:raise ValueError('Kalibrasyon profili bulunamadı')
                target=Path(selected['path'])
            else:target=h.calibration_root/'so_follower'/f'{robot_id}.json'
            identity={k:device.get(k) for k in ('vid','pid','serial_number')}
            if not identity.get('serial_number'):identity['port']=port
            restore=None
            if backup_id:
                if not re.fullmatch(r'[0-9a-f]{32}',backup_id):raise ValueError('Geçersiz yedek kimliği')
                restore=self.root/'motors'/backup_id/'backup.json'
                record=json.loads(restore.read_text())
                if record['identity']!=identity or record['target']!=str(target):raise ValueError('Yedek seçilen USB kolu / profiliyle eşleşmiyor')
            if old:=h.processes.pop('arm',None):old.stop()
            if old:=h.processes.pop('calibration',None):old.stop()
            session=uuid.uuid4().hex;directory=self.root/'motors'/session
            command=[str(h.python),'-u','-m','so101.calibration_motor','--port',port,'--target',str(target),'--directory',str(directory),'--identity',json.dumps(identity)]
            if restore:command.extend(['--restore',str(restore)])
            worker=DiagnosticProcess(command,h.root,'calibration',interactive=True)
            worker.session=session;worker.pending_revision=None;h.processes['calibration']=worker;h.last_poll=time.monotonic()
            h._event('Kalibrasyon yedekleme oturumu açıldı. Tork bırakma ayrı onay adımıdır.')
            return h.state()

    def command(self,session,command):
        h=self.hardware
        with h.lock:
            worker=h.processes.get('calibration')
            if not worker or worker.session!=session:raise ValueError('Kalibrasyon oturumu değişti')
            state=worker.snapshot()
            if not state['running']:raise ValueError('Kalibrasyon oturumu sona erdi')
            revision=command.get('revision')
            if command['op']!='cancel':
                if not state['fresh'] or revision!=state.get('revision') or worker.pending_revision==revision:raise ValueError('Güncel adımı bekle; aynı komut yeniden gönderilmedi')
                worker.pending_revision=revision
            worker.send(command);h.last_poll=time.monotonic();return h.state()

    def camera_command(self,role,session,command):
        h=self.hardware
        with h.lock:
            worker=h.processes.get(role)
            if not worker or worker.session!=session:raise ValueError('Kamera oturumu değişti; yeniden aç')
            state=worker.snapshot()
            if not state['fresh']:raise ValueError('Güncel kamera karesi gerekli')
            pending=getattr(worker,'pending_command',None)
            if pending and state.get('calibration',{}).get('last_command_id')!=pending:raise ValueError('Önceki kamera işlemi sürüyor')
            command=dict(command,command_id=uuid.uuid4().hex);worker.pending_command=command['command_id'];worker.send(command)
            return h.state()

    def heartbeat(self):
        worker=self.hardware.processes.get('calibration')
        if worker and worker.process.poll() is None and time.monotonic()-self.last_heartbeat>2:
            try:worker.send(dict(op='heartbeat'))
            except OSError:pass
            self.last_heartbeat=time.monotonic()

    def report(self,kind,record_id):
        if kind=='motor':
            if not re.fullmatch(r'[0-9a-f]{32}',record_id):raise ValueError('Geçersiz kayıt')
            directory=self.root/'motors'/record_id
            return {name:json.loads((directory/f'{name}.json').read_text()) for name in ('backup','status','candidate') if (directory/f'{name}.json').exists()}
        if not re.fullmatch(r'(wrist|top)/[0-9a-f]{32}',record_id):raise ValueError('Geçersiz kamera kaydı')
        directory=self.root/'cameras'/record_id
        result={name:json.loads((directory/f'{name}.json').read_text()) for name in ('calibration','workspace') if (directory/f'{name}.json').exists()}
        source=result.get('workspace',{}).get('camera_profile_session','')
        if 'calibration' not in result and re.fullmatch(r'[0-9a-f]{32}',source):
            result['calibration']=json.loads((directory.parent/source/'calibration.json').read_text())
        return result
