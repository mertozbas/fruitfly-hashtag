"""Supervised teach/repeat and 0.7-degree probes. No autonomous brain controller."""
import argparse
import json
from pathlib import Path
import queue
import signal
import sys
import threading
import time
import uuid
from .calibration_contract import atomic_json,digest
from .hardware_contract import calibration,JOINTS
from .physical_contract import (RATE,MAX_STEP,MAX_RECORD_SECONDS,MAX_RUN_SECONDS,MAX_SAMPLES,HOLD_TIMEOUT,
    HEARTBEAT_TIMEOUT,check_pose,interpolate,limits,signature,validate_trajectory)
from .physical_driver import PhysicalBus


class PhysicalSession:
    def __init__(self,bus,path,sha,directory,identity,clock=time.monotonic):
        self.bus=bus;self.path=Path(path);self.sha=sha;self.directory=Path(directory);self.identity=identity;self.clock=clock
        self.stage='connecting';self.revision=0;self.warning=None;self.errors=[];self.q=[];self.motors=[]
        self.cal=None;self.bounds=[];self.points=[];self.plan=None;self.token=None;self.expires=0.;self.used=set()
        self.last_heartbeat=0.;self.cameras_ok=False;self.last_hold=0.;self.hold_sequence=-1;self.last_sample=0.
        self.record_start=0.;self.record_id=None;self.run_start=0.;self.run_index=1;self.segment_time=0.;self.last_tick=0.
        self.last_verify=0.;self.run_id=None;self.result=None;self.audit=[];self.last_command_id=None

    def event(self,note):
        self.audit.append(dict(time=time.time(),stage=self.stage,note=note))
        atomic_json(self.directory/'status.json',dict(session=self.directory.name,stage=self.stage,warning=self.warning,errors=self.errors,
            calibration_sha256=self.sha,identity=self.identity,torque_may_be_on=self.bus.enabled,events=self.audit[-100:]))

    def change(self,stage,note=None):
        self.stage=stage;self.revision+=1
        if note:self.warning=note
        self.event(note or stage)

    def start(self):
        saved=calibration(self.path)
        if not saved['valid'] or saved['sha256']!=self.sha:raise ValueError('Kalibrasyon dosyası geçersiz / değişmiş')
        self.cal=saved['motors'];self.bounds=limits(self.cal);self.bus.open();self.bus.verify(self.cal)
        self.sample();self.change('idle','Salt okuma hazır. Elle öğretim için tork kapalı olmalı.')

    def sample(self):
        start=self.clock();self.q,self.motors=self.bus.telemetry(self.cal);self.last_sample=self.clock()
        if self.last_sample-start>.15:raise OSError('Motor okuma gecikmesi 150 ms sınırını aştı')
        if digest(self.path)!=self.sha:raise OSError('Kalibrasyon dosyası değişti; hareket izni iptal edildi')
        for row in self.motors:
            if row['temperature_c']>=50:raise OSError(f'{row["name"]}: sıcaklık 50 °C sınırında')
            if not 6<=row['voltage_v']<=13.2:raise OSError(f'{row["name"]}: besleme voltajı sınır dışında')
            if row['operating_mode']!=0:raise OSError('Motor çalışma modu değişti')
        if self.last_sample-self.last_verify>=1:
            self.bus.verify(self.cal);self.last_verify=self.clock()

    def fresh(self):
        now=self.clock()
        if now-self.last_sample>.2:raise ValueError('Güncel motor ölçümü gerekli')
        if now-self.last_heartbeat>HEARTBEAT_TIMEOUT or not self.cameras_ok:raise ValueError('İki canlı kamera ve güncel panel bağlantısı gerekli')

    def off(self):
        if self.bus.enabled or any(r['torque_enabled'] for r in self.motors):raise ValueError('Önce kolu destekleyip Serbest bırak işlemini kullan')

    def state(self):
        p=self.plan
        plan=None if not p else dict(kind=p['kind'],token=self.token,expires_in_s=max(0,self.expires-self.clock()),
            signature=p['signature'],samples=len(p['points']),duration_s=p['duration'],start=p['points'][0]['q'],
            finish=p['points'][-1]['q'],joint=p.get('joint'),direction=p.get('direction'),record_id=p.get('record_id'),
            max_degrees_per_s=RATE*360/4095,start_error_counts=max(abs(a-b) for a,b in zip(self.q,p['points'][0]['q'])) if self.q else None)
        return dict(kind='physical',session=self.directory.name,stage=self.stage,revision=self.revision,q=self.q,motors=self.motors,bounds=self.bounds,
            warning=self.warning,errors=self.errors,plan=plan,record_id=self.record_id,sample_count=len(self.points),
            record_seconds=max(0,self.clock()-self.record_start) if self.stage=='recording' else None,
            torque_owned=self.bus.enabled,cameras_ok=self.cameras_ok,run_id=self.run_id,result=self.result,
            progress=0 if not p else min(1,self.run_index/max(1,len(p['points'])-1)),last_command_id=self.last_command_id,
            controller='operator_taught_joint_trajectory',brain_connected=False,calibration_sha256=self.sha,
            note='Elle öğretilen yol; nesne algısı / otomatik kavrama doğrulaması / beyin kontrolü değildir.')

    def command(self,c):
        op=c['op'];now=self.clock()
        if op=='heartbeat':
            self.last_heartbeat=now;self.cameras_ok=c.get('cameras_ok') is True;return
        if op=='hold':
            if c.get('token')!=self.token or self.stage!='running' or type(c.get('sequence')) is not int or c['sequence']<=self.hold_sequence:return
            self.hold_sequence=c['sequence'];self.last_hold=now;return
        self.last_command_id=c.get('command_id')
        if op=='stop':
            if c.get('token'):self.used.add(c['token'])
            self.stop('Operatör durdurdu. Tork açık kalabilir; kolu destekleyerek serbest bırak.');return
        if c.get('revision')!=self.revision:raise ValueError('Ekran adımı değişti; güncel durumu bekle')
        if op=='release':
            if c.get('supported') is not True:raise ValueError('Kolu desteklediğini doğrula')
            self.stop('Serbest bırakma istendi.');self.bus.release();self.sample();self.plan=None;self.token=None
            self.change('idle','Tork kapalı. Kolu elle yönlendirebilirsin.');return
        if self.stage in {'running','failed'}:raise ValueError('Önce hareketi durdur ve kolu destekleyerek serbest bırak')
        self.fresh();self.off();check_pose(self.q,self.bounds)
        if op=='record_start':
            self.points=[];self.plan=None;self.token=None;self.result=None;self.record_start=now;self.record_id=uuid.uuid4().hex
            self.points.append(dict(t=0.,q=self.q.copy()));self.change('recording','Kolu elle yavaşça yönlendir; kıskacı elle aç/kapat. En fazla 90 saniye.')
        elif op=='record_stop':
            if self.stage!='recording':raise ValueError('Kayıt açık değil')
            duration=validate_trajectory(self.points,self.bounds)
            record=dict(schema=1,id=self.record_id,calibration_sha256=self.sha,identity=self.identity,points=self.points,
                created=time.time(),estimated_duration_s=duration,cube_design_mm=30,controller='operator_taught_joint_trajectory',brain_connected=False)
            atomic_json(self.directory/self.record_id/'trajectory.json',record)
            self.change('recorded','Yol kaydedildi. Küpü yerine koy; kolu ilk poza elle geri getir. Önizlemede başlangıç farkını kontrol et.')
        elif op=='preview':
            if self.stage=='recording':raise ValueError('Önce kaydı bitir')
            kind=c.get('kind');record_id=None
            if kind=='probe':
                joint=c.get('joint');direction=c.get('direction')
                if joint not in JOINTS or type(direction) is not int or direction not in (-1,1):raise ValueError('Eklem ve yön gerekli')
                end=self.q.copy();end[JOINTS.index(joint)]+=direction*8;check_pose(end,self.bounds)
                points=[dict(t=0.,q=self.q.copy()),dict(t=.25,q=end)];duration=.25
            elif kind=='trajectory':
                record_id=c.get('record_id') or self.record_id
                if not isinstance(record_id,str) or len(record_id)!=32 or any(x not in '0123456789abcdef' for x in record_id):raise ValueError('Geçerli yol kaydı gerekli')
                file=self.directory/record_id/'trajectory.json';record=json.loads(file.read_text())
                if record['calibration_sha256']!=self.sha or record['identity']!=self.identity:raise ValueError('Yol kaydı bu kol / kalibrasyonla eşleşmiyor')
                points=record['points'];duration=validate_trajectory(points,self.bounds)
                if max(abs(a-b) for a,b in zip(self.q,points[0]['q']))>20:raise ValueError('Kol ilk kayıt pozundan uzakta; elle başlangıca getir (en fazla 20 sayım fark)')
                # Explicit short interpolation from the current pose, also shown in the preview.
                points=[dict(t=0.,q=self.q.copy()),*[dict(t=p['t']+.25,q=p['q']) for p in points]]
                duration+=.5
            else:raise ValueError('Geçerli önizleme türü gerekli')
            self.plan=dict(kind=kind,points=points,duration=duration,joint=c.get('joint'),direction=c.get('direction'),record_id=record_id)
            self.plan['signature']=signature(self.plan);self.token=uuid.uuid4().hex;self.expires=now+20;self.run_index=1;self.result=None
            self.change('prepared','Yolu ve alanı kontrol et. Başlatma onayı 20 saniye geçerli; düğme basılı tutulmalı.')
        elif op=='run':
            if self.stage!='prepared' or not self.plan or c.get('token')!=self.token or self.token in self.used or now>self.expires:raise ValueError('Hareket önizlemesi eski / kullanılmış; yeniden önizle')
            if any(c.get(k) is not True for k in ('mounted','clear','reviewed')):raise ValueError('Sabit taban, boş hareket alanı ve yol incelemesi doğrulanmalı')
            self.used.add(self.token)
            # Recheck EEPROM/identity and measured start immediately before first write.
            self.bus.verify(self.cal);self.sample();self.fresh()
            self.bus.enable_at_current(self.plan['points'][0]['q'],self.bounds)
            self.run_id=uuid.uuid4().hex;self.run_start=now;self.last_hold=now;self.hold_sequence=-1;self.last_tick=now;self.segment_time=0.;self.run_index=1
            atomic_json(self.directory/f'{self.run_id}-plan.json',dict(plan=self.plan,identity=self.identity,calibration_sha256=self.sha,operator_confirmations={k:c[k] for k in ('mounted','clear','reviewed')}))
            self.change('running','Düğme basılıyken hareket ediyor. Bırakınca durur; tork açık kalır.')
        else:raise ValueError('Geçersiz fiziksel görev işlemi')

    def stop(self,note):
        if self.token:self.used.add(self.token)
        if self.bus.enabled:
            try:self.bus.hold()
            except Exception as exc:
                self.errors.append(str(exc));self.change('failed','Tutma doğrulanamadı. Kolu destekle ve gücü güvenle kes.');return
        if self.stage not in {'idle','connecting','failed'}:self.change('stopped',note)

    def tick(self):
        self.sample();now=self.clock()
        if self.stage=='recording':
            self.fresh();self.off();check_pose(self.q,self.bounds)
            point=dict(t=round(now-self.record_start,6),q=self.q.copy())
            if point['t']<=self.points[-1]['t']:return
            if point['t']-self.points[-1]['t']>.3 or max(abs(a-b) for a,b in zip(self.q,self.points[-1]['q']))>35:raise ValueError('Öğretim hızlı veya okuma kesildi; kaydı yeniden başlat')
            self.points.append(point)
            if len(self.points)>=MAX_SAMPLES or point['t']>=MAX_RECORD_SECONDS:
                # Finish only valid records; never silently trim a task.
                self.command(dict(op='record_stop',revision=self.revision))
        elif self.stage=='running':
            if now-self.last_hold>HOLD_TIMEOUT or now-self.last_heartbeat>HEARTBEAT_TIMEOUT or not self.cameras_ok:
                self.stop('Basılı tutma veya kamera bağlantısı kesildi. Hareket durdu; tork açık kalır.');return
            if now-self.run_start>MAX_RUN_SECONDS:
                self.stop('180 saniyelik deneme sınırına ulaşıldı.');return
            dt=now-self.last_tick;self.last_tick=now
            if dt>.15:self.stop('Kontrol döngüsü gecikti; hareket durdu.');return
            points=self.plan['points'];a,b=points[self.run_index-1:self.run_index+1]
            duration=max(b['t']-a['t'],max(abs(x-y) for x,y in zip(a['q'],b['q']))/RATE,.05)
            self.segment_time=min(duration,self.segment_time+dt)
            desired=interpolate(a['q'],b['q'],self.segment_time/duration)
            target=[int(old+max(-MAX_STEP,min(MAX_STEP,new-old))) for old,new in zip(self.bus.targets,desired)]
            self.bus.goal(target,self.bounds)
            if self.segment_time>=duration and target==b['q']:
                self.run_index+=1;self.segment_time=0.
                if self.run_index>=len(points):
                    self.bus.hold();self.result=dict(trajectory_completed=True,grasp_success_verified=False,brain_connected=False)
                    self.change('finished','Hareket dizisi bitti. Bu sonuç küpün başarıyla taşındığını otomatik doğrulamaz; görüntüyü kontrol et.')


def main():
    p=argparse.ArgumentParser();p.add_argument('--port',required=True);p.add_argument('--calibration',required=True);p.add_argument('--sha',required=True)
    p.add_argument('--directory',required=True);p.add_argument('--identity',required=True);a=p.parse_args()
    commands=queue.Queue(32);stop=threading.Event()
    def receive():
        try:
            for line in sys.stdin:
                if len(line)>4096:break
                commands.put_nowait(json.loads(line))
        except (ValueError,queue.Full):pass
        finally:stop.set()
    threading.Thread(target=receive,daemon=True).start();signal.signal(signal.SIGTERM,lambda *_:stop.set())
    session=PhysicalSession(PhysicalBus(a.port),a.calibration,a.sha,a.directory,json.loads(a.identity));deadline=time.monotonic()+600
    try:
        session.start()
        while not stop.is_set() and time.monotonic()<deadline:
            begin=time.monotonic()
            while not commands.empty():
                command=commands.get_nowait()
                try:session.command(command)
                except ValueError as exc:
                    session.warning=str(exc);session.revision+=1
                    if session.bus.enabled:session.stop(str(exc))
            try:session.tick()
            except ValueError as exc:session.stop(str(exc));session.warning=str(exc);session.revision+=1
            print(json.dumps(session.state(),allow_nan=False),flush=True)
            stop.wait(max(0,.05-(time.monotonic()-begin)))
    except Exception as exc:
        session.errors.append(str(exc));session.stop(str(exc));session.stage='failed';session.warning=str(exc)
    finally:
        try:
            session.stop('Oturum kapandı. Son hedef yakındır; motor torku açık kalabilir.')
            session.event('Port bırakıldı; motor torku otomatik açılmaz/kapatılmaz.')
            print(json.dumps(session.state(),allow_nan=False),flush=True)
        finally:session.bus.close()


if __name__=='__main__':main()
