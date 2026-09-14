"""SO-101 manual calibration, matching LeRobot 0.6 STS3215 semantics.

Only this worker may release torque and write the allowlisted calibration
registers, after explicit wizard commands. Autonomous actuation is absent.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import queue
import signal
import sys
import threading
import time
from .hardware_contract import JOINTS,signed_magnitude
from .calibration_contract import RANGED_JOINTS,TERMINAL,atomic_bytes,atomic_json,calibration_packet,digest,range_errors,signed_word,validate_backup


class CalibrationBus:
    def __init__(self,port_name):
        from scservo_sdk import PortHandler,PacketHandler
        class GuardedPort(PortHandler):
            permit=None
            def writePort(self,packet):
                allowed=calibration_packet(packet,self.permit);self.permit=None
                return super().writePort(allowed)
            def getCurrentTime(self):return time.monotonic()*1000
        self.port=GuardedPort(port_name);self.packet=PacketHandler(0);self.unlocked=False

    def open(self):
        if not self.port.openPort():raise OSError('Motor portu açılamadı')
        if os.name=='posix':
            import fcntl,termios
            if hasattr(termios,'TIOCEXCL'):fcntl.ioctl(self.port.ser.fileno(),termios.TIOCEXCL)

    def close(self):
        if self.port.is_open:self.port.closePort()

    def read(self,motor,address,size=2):
        value,comm,error=(self.packet.read1ByteTxRx if size==1 else self.packet.read2ByteTxRx)(self.port,motor,address)
        if comm or error:raise OSError(f'Motor {motor}: okuma başarısız ({comm}/{error})')
        return int(value)

    def write(self,motor,address,value,size=2):
        if address!=40 and not self.unlocked:raise PermissionError('Önce tork bırakma adımı gerekli')
        data=int(value).to_bytes(size,'little');self.port.permit=(motor,address,data)
        try:
            comm,error=(self.packet.write1ByteTxRx if size==1 else self.packet.write2ByteTxRx)(self.port,motor,address,value)
            if comm or error:raise OSError(f'Motor {motor}: yazma başarısız ({comm}/{error})')
        finally:self.port.permit=None
        if self.read(motor,address,size)!=value:raise OSError(f'Motor {motor}: yazılan ayar geri okunamadı')

    def snapshot(self):
        result={}
        for i,name in enumerate(JOINTS,1):
            if self.read(i,3)!=777:raise ValueError(f'Motor {i}: STS3215 değil')
            result[name]=dict(id=i,range_min=self.read(i,9),range_max=self.read(i,11),homing_offset=signed_magnitude(self.read(i,31),11),
                operating_mode=self.read(i,33,1),torque=self.read(i,40,1),lock=self.read(i,55,1))
        return result

    def positions(self):
        return {name:signed_magnitude(self.read(i,56),15) for i,name in enumerate(JOINTS,1)}

    def torque_off(self):
        # Disable every joint before unlocking EEPROM, never re-enable torque.
        for i in range(1,7):self.write(i,40,0,1)
        self.unlocked=True
        for i in range(1,7):self.write(i,55,0,1)

    def assert_off(self):
        if any(self.read(i,40,1)!=0 for i in range(1,7)):raise OSError('Tork beklenmedik şekilde açıldı; kalibrasyon durduruldu')

    def apply(self,motors,restore_modes=False):
        self.assert_off()
        for name in JOINTS:
            m=motors[name];i=m['id']
            self.write(i,31,signed_word(m['homing_offset']));self.write(i,9,m['range_min']);self.write(i,11,m['range_max'])
            if restore_modes:self.write(i,33,m['operating_mode'],1)

    def seal(self):
        for i in range(1,7):self.write(i,55,1,1)


class MotorCalibration:
    def __init__(self,bus,target,directory,identity,restore=None):
        self.bus=bus;self.target=Path(target);self.directory=Path(directory);self.identity=identity;self.restore=restore
        self.stage='connecting';self.revision=0;self.ranges={};self.samples={};self.positions={};self.reference={}
        self.candidate=None;self.current=None;self.errors=[];self.changed=False;self.file_written=False;self.last_command=None
        self.expected_sha=digest(self.target);self.before=None;self.warning=None;self.backup=None

    def start(self):
        self.bus.open();self.before=self.bus.snapshot()
        if self.restore:
            if self.restore['identity']!=self.identity or self.restore['target']!=str(self.target):raise ValueError('Yedek bu kol / profil ile eşleşmiyor')
            validate_backup(self.restore)
        # Backup is durably written before ANY motor write or torque release.
        original=self.target.read_bytes() if self.target.exists() else None
        original_sha=hashlib.sha256(original).hexdigest() if original is not None else None
        if original_sha!=self.expected_sha:raise OSError('Profil yedek hazırlanırken değişti; yeniden başlat')
        record=dict(schema=1,identity=self.identity,target=str(self.target),motors=self.before,file_sha256=original_sha,
                    file_base64=base64.b64encode(original).decode() if original is not None else None,created=time.time())
        validate_backup(record)
        atomic_json(self.directory/'backup.json',record)
        self.backup=record
        self.transition('backup')

    def transition(self,stage):
        previous=(self.stage,self.revision);self.stage=stage;self.revision+=1
        try:atomic_json(self.directory/'status.json',self.state())
        except Exception:
            self.stage,self.revision=previous;raise

    def replace_target(self,raw):
        # Track ownership before replace: directory fsync can fail AFTER rename.
        self.file_written=True;self.written_sha=hashlib.sha256(raw).hexdigest() if raw is not None else None
        if raw is not None:atomic_bytes(self.target,raw)
        elif self.target.exists():self.target.unlink()

    def state(self):
        return dict(kind='calibration',stage=self.stage,revision=self.revision,session=self.directory.name,positions=self.positions,
            ranges={n:dict(min=v[0],max=v[1],samples=self.samples.get(n,0)) for n,v in self.ranges.items()},
            joint=self.current,candidate=self.restore['motors'] if self.restore else self.candidate,errors=self.errors,warning=self.warning,
            backup_id=self.directory.name if self.before else None,torque_released=self.changed,
            target=self.target.name,file_sha256=digest(self.target),restore_mode=bool(self.restore),last_command=self.last_command)

    def sample(self):
        if self.stage in TERMINAL:return
        self.positions=self.bus.positions()
        if self.changed:self.bus.assert_off()
        if self.stage=='ranges' and self.current:
            name=self.current;value=self.positions[name]
            if not 0<=value<=4095:raise ValueError(f'{name}: enkoder sarımı algılandı; orta konum yeniden seçilmeli')
            if name not in self.ranges:self.ranges[name]=[value,value]
            self.ranges[name]=[min(self.ranges[name][0],value),max(self.ranges[name][1],value)]
            self.samples[name]=self.samples.get(name,0)+1

    def command(self,command):
        op=command['op']
        if op=='cancel':self.cancel();return
        if command.get('revision')!=self.revision:raise ValueError('Adım değişti; güncel ekranı kullan')
        if self.stage in TERMINAL:raise ValueError('Kalibrasyon oturumu sona erdi')
        self.last_command=op
        if op=='release' and self.stage=='backup':
            if command.get('supported') is not True:raise ValueError('Kolun desteklendiği doğrulanmalı')
            if digest(self.target)!=self.expected_sha:raise OSError('Profil yedeklemeden sonra değişti; tork bırakılmadı')
            self.changed=True;self.bus.torque_off()
            for i in range(1,7):self.bus.write(i,33,0,1)
            self.transition('restore_review' if self.restore else 'reference')
        elif op=='reference' and self.stage=='reference':
            if command.get('supported') is not True:raise ValueError('Orta konum doğrulaması gerekli')
            self.bus.assert_off()
            for i in range(1,7):self.bus.write(i,31,0);self.bus.write(i,9,0);self.bus.write(i,11,4095)
            actual=self.bus.positions();self.offsets={name:actual[name]-2047 for name in JOINTS}
            for value in self.offsets.values():signed_word(value)
            for i,name in enumerate(JOINTS,1):self.bus.write(i,31,signed_word(self.offsets[name]))
            self.reference=self.bus.positions()
            if any(abs(value-2047)>40 for value in self.reference.values()):raise OSError('Referans konumu kararlı değil; kolu sabit tut')
            self.current=RANGED_JOINTS[0];self.transition('ranges')
        elif op=='next' and self.stage=='ranges':
            if command.get('range_confirmed') is not True:raise ValueError('Her iki mekanik uç doğrulanmalı')
            self.sample();name=self.current
            allranges={n:self.ranges.get(n,[2047,2047]) for n in RANGED_JOINTS}
            problems=[e for e in range_errors(allranges,self.samples,self.reference) if e.startswith(name+':')]
            if problems:raise ValueError(' · '.join(problems))
            index=RANGED_JOINTS.index(name)
            if index+1<len(RANGED_JOINTS):self.current=RANGED_JOINTS[index+1];self.transition('ranges')
            else:
                self.current=None;self.errors=range_errors(self.ranges,self.samples,self.reference)
                if self.errors:raise ValueError(' · '.join(self.errors))
                self.candidate={n:dict(id=i,drive_mode=0,homing_offset=self.offsets[n],range_min=0 if n=='wrist_roll' else self.ranges[n][0],range_max=4095 if n=='wrist_roll' else self.ranges[n][1]) for i,n in enumerate(JOINTS,1)}
                atomic_json(self.directory/'candidate.json',self.candidate);self.transition('review')
        elif op=='save' and self.stage=='review':
            if command.get('confirmed') is not True:raise ValueError('Sonuç onayı gerekli')
            if digest(self.target)!=self.expected_sha:raise OSError('Kalibrasyon dosyası dışarıdan değişti; üzerine yazılmadı')
            self.bus.apply(self.candidate)
            actual=self.bus.snapshot()
            for name in JOINTS:
                if any(actual[name][key]!=self.candidate[name][key] for key in ('id','range_min','range_max','homing_offset')):raise OSError('Son motor doğrulaması başarısız')
            # Recheck after EEPROM operations, before replacing the file.
            if digest(self.target)!=self.expected_sha:raise OSError('Dosya eşzamanlı değişti')
            self.bus.seal();self.replace_target(json.dumps(self.candidate,indent=2,allow_nan=False).encode())
            self.warning='Kalibrasyon kaydedildi. Tork kapalı bırakıldı; hareket ve simülasyon eşleştirmesi ayrı doğrulanır.'
            self.transition('saved')
        elif op=='restore' and self.stage=='restore_review':
            if command.get('confirmed') is not True:raise ValueError('Yedek geri yükleme onayı gerekli')
            if digest(self.target)!=self.expected_sha:raise OSError('Profil dışarıdan değişti')
            self.bus.apply(self.restore['motors'],restore_modes=True)
            original=self.restore.get('file_base64')
            self.bus.seal()
            if digest(self.target)!=self.expected_sha:raise OSError('Profil eşzamanlı değişti')
            self.replace_target(base64.b64decode(original) if original is not None else None)
            self.warning='Yedek geri yüklendi. Tork kapalı bırakıldı.';self.transition('restored')
        else:raise ValueError('Bu adımda bu işlem kullanılamaz')

    def cancel(self):
        if self.stage in TERMINAL:return
        if self.changed:
            try:
                self.bus.torque_off();self.bus.apply(self.before,restore_modes=True)
                self.bus.seal()
                if self.file_written and digest(self.target)!=self.expected_sha:
                    if digest(self.target)!=self.written_sha:raise OSError('Dosya başka işlem tarafından değiştirildi; eski dosya yedekte korundu')
                    raw=self.backup['file_base64']
                    if raw is not None:atomic_bytes(self.target,base64.b64decode(raw))
                    elif self.target.exists():self.target.unlink()
                self.warning='Önceki motor kalibrasyonu geri yüklendi. Tork kapalı bırakıldı.'
            except Exception as exc:
                self.errors=[f'Geri yükleme tamamlanamadı: {exc}'];self.warning='Kolun gücünü güvenle kes; yedekten kurtarma gerekli.'
                self.transition('failed');return
        self.transition('failed' if self.errors else 'cancelled')


def main():
    p=argparse.ArgumentParser();p.add_argument('--port',required=True);p.add_argument('--target',required=True);p.add_argument('--directory',required=True)
    p.add_argument('--identity',required=True);p.add_argument('--restore');a=p.parse_args()
    commands=queue.Queue(16);stop=threading.Event()
    def read_commands():
        try:
            for line in sys.stdin:
                if len(line)>4096:break
                commands.put_nowait(json.loads(line))
        except (ValueError,queue.Full):pass
        finally:stop.set()
    threading.Thread(target=read_commands,daemon=True).start();signal.signal(signal.SIGTERM,lambda *_:stop.set())
    restore=json.loads(Path(a.restore).read_text()) if a.restore else None
    session=MotorCalibration(CalibrationBus(a.port),a.target,a.directory,json.loads(a.identity),restore)
    lock=None
    try:
        Path(a.target).parent.mkdir(parents=True,exist_ok=True)
        lock=open(str(a.target)+'.lock','a')
        if os.name=='posix':
            import fcntl
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        session.start();deadline=time.monotonic()+600;heartbeat=time.monotonic()
        while not stop.is_set() and time.monotonic()<deadline and time.monotonic()-heartbeat<15:
            while not commands.empty():
                command=commands.get_nowait()
                if command.get('op')=='heartbeat':heartbeat=time.monotonic();continue
                try:session.command(command)
                except ValueError as exc:session.warning=str(exc);session.revision+=1
            session.sample()
            print(json.dumps(session.state(),allow_nan=False),flush=True)
            if session.stage in TERMINAL:break
            stop.wait(.1)
    except Exception as exc:
        session.warning=str(exc);session.errors.append(str(exc))
        print(json.dumps(dict(kind='calibration',**{k:v for k,v in session.state().items() if k!='kind'})),flush=True)
    finally:
        try:
            session.cancel()
            print(json.dumps(session.state(),allow_nan=False),flush=True)
        finally:
            session.bus.close()
            if lock:lock.close()


if __name__=='__main__':main()
