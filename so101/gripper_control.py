"""Finite opening of an empty gripper; body holding goals are never written."""
import time

from .alignment_probe import ProbeBus
from .hardware_contract import assert_read_packet
from .neural_control import telemetry


class GripperBus(ProbeBus):
    motor_id=6

    def guard(self,packet):
        p=bytes(packet)
        if len(p)>4 and p[4] in (1,2):return assert_read_packet(p)
        if (len(p)<8 or p[:2]!=b'\xff\xff' or p[2]!=6 or p[3]+4!=len(p)
                or p[4]!=3 or sum(p[2:])&255!=255):
            raise PermissionError('Only the empty gripper may be written')
        address=p[5];data=p[6:-1];value=int.from_bytes(data,'little')
        if self.permit!=(address,data):raise PermissionError('Missing gripper packet permit')
        self.permit=None;allowed=False
        if self.phase=='setup':
            allowed=len(data)==2 and ((address,value) in ((44,0),(46,20),(48,self.cap))
                                      or (address==42 and value==self.initial))
        elif self.phase=='enable':allowed=len(data)==1 and address==40 and value==1
        elif self.phase=='move':
            allowed=(len(data)==2 and address==42 and self.initial<=value<=self.target
                     and 0<=value-self.last_goal<=2)
        elif self.phase=='off':allowed=len(data)==1 and address==40 and value==0
        elif self.phase=='restore':
            allowed=len(data)==2 and address in (44,46,48) and value==self.backup.get(address)
        if not allowed:raise PermissionError('Gripper packet outside its opening plan')
        return p

    def prepare(self,expected,target,saved):
        if self.phase!='read':raise ValueError('Kıskaç oturumu yeniden kullanılamaz')
        q=self.positions()
        if max(abs(a-b) for a,b in zip(q,expected))>3:raise ValueError('Kol önizlemeden sonra değişti')
        if not isinstance(target,list) or len(target)!=6 or any(type(v) is not int for v in target):
            raise ValueError('Altı tam sayı hedef gerekli')
        if target[:5]!=expected[:5] or not 1<=target[5]-expected[5]<=128:
            raise ValueError('Yalnız boş kıskacı 1–128 sayım açma hedefi kabul edilir')
        if not saved['gripper']['range_min']<=q[5]<target[5]<=saved['gripper']['range_max']:
            raise ValueError('Kıskaç açma hedefi kalibrasyon aralığında değil')
        if any(bool(self.read(i,40,1))!=(i<6) for i in range(1,7)):
            raise ValueError('Gövde poz tutmalı, kıskaç başlangıçta serbest olmalı')
        self.initial=self.last_goal=q[5];self.target=target[5]
        self.backup={a:self.read(6,a) for a in (44,46,48)}
        if not 1<=self.backup[48]<=1000:raise ValueError('Geçersiz kıskaç tork ayarı')
        self.cap=min(self.backup[48],self.read(6,16),100)
        if self.cap<=0:raise ValueError('Geçersiz kıskaç tork tavanı')

    def enable(self):
        self.phase='setup'
        self.write(46,20);self.write(44,0);self.write(48,self.cap);self.write(42,self.initial)
        if abs(self.positions()[5]-self.initial)>2:raise ValueError('Kıskaç tork açılmadan değişti')
        self.phase='enable';self.may_be_on=True;self.write(40,1,1);self.phase='move'

    def finish(self):
        if self.phase=='done':return []
        return super().finish()


class GripperOpening:
    brain_driven=False
    duration=15

    def __init__(self,bus,saved,expected,target,empty_gripper=False,check_live=lambda:None,clock=time.monotonic):
        if empty_gripper is not True:raise ValueError('Boş kıskaç görüntüden doğrulanmalı')
        self.bus=bus;self.saved=saved;self.expected=expected;self.target=target
        self.check_live=check_live;self.clock=clock;self.started=None;self.last_tick=None
        self.commands=0;self.stall_since=None;self.settled_since=None;self.goal_finished=None

    def start(self):
        self.bus.open();self.bus.verify(self.saved);telemetry(self.bus,self.saved)
        self.bus.prepare(self.expected,self.target,self.saved)
        self.check_live();telemetry(self.bus,self.saved)
        self.bus.enable();self.started=self.last_tick=self.clock()

    def step(self,drive,visible,heartbeat_age,source_age):
        now=self.clock()
        if self.started is None or now-self.started>=self.duration:raise ValueError('Kıskaç açma süresi doldu')
        if heartbeat_age>1 or not 0<=source_age<=.4:raise ValueError('Panel veya kamera güncel değil')
        dt=now-self.last_tick;self.last_tick=now
        if dt>.25:raise ValueError('Kıskaç döngüsü 250 ms sınırını aştı')
        q,rows=telemetry(self.bus,self.saved)
        if source_age+self.clock()-now>.4:raise ValueError('Kamera ölçümü eskidi')
        if not all(row['torque'] for row in rows):raise ValueError('Tutma veya kıskaç torku kayboldu')
        if max(abs(a-b) for a,b in zip(q[:5],self.expected[:5]))>8:raise ValueError('Gövde tutma konumu kaydı')
        if not self.bus.initial-3<=q[5]<=self.bus.target+8:raise ValueError('Kıskaç ölçümü açma aralığını aştı')
        if abs(rows[5]['load'])>80:raise ValueError('Boş kıskaç açılırken yük sınırı aşıldı')
        if dt>=.08 and self.bus.last_goal<self.bus.target:
            candidate=min(self.bus.target,self.bus.last_goal+2)
            if abs(candidate-q[5])>8:
                if self.stall_since is None:self.stall_since=now
                if now-self.stall_since>=1:raise ValueError('Kıskaç hedefi izlemiyor; açma durdu')
            else:self.bus.goal(candidate);self.commands+=1;self.stall_since=None
        finished=self.bus.last_goal==self.bus.target
        if finished and self.goal_finished is None:self.goal_finished=now
        reached=finished and abs(q[5]-self.bus.target)<=5
        if finished and not reached and now-self.goal_finished>=2:raise ValueError('Kıskaç hedefe yerleşemedi')
        if reached:
            if self.settled_since is None:self.settled_since=now
        else:self.settled_since=None
        return dict(q=q,motors=rows,goal=[*self.expected[:5],self.bus.last_goal],desired=self.target,
                    neural_command=False,complete=self.settled_since is not None and now-self.settled_since>=.5)

    def stop(self):
        try:errors=self.bus.finish()
        finally:self.bus.close()
        if errors:raise OSError('; '.join(errors))
