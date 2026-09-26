"""Finite coordinated positioning of an already-supported, torque-held SO-101.

This is a deterministic positioning primitive, not a learned grasp policy.
The serial boundary permits only bounded position goals on body motors 1..5.
"""
import time

from .alignment_probe import ProbeBus
from .hardware_contract import JOINTS,assert_read_packet
from .neural_control import telemetry

# Tracking error is bounded separately from the planned travel envelope.
MAX_TRACKING_LEAD=16


class BodyBus(ProbeBus):
    def __init__(self,port):
        super().__init__(port)
        self.goals=None;self.bounds=None;self.stop_positions=None

    def guard(self,packet):
        p=bytes(packet)
        if len(p)>4 and p[4] in (1,2):return assert_read_packet(p)
        if (len(p)!=9 or p[:2]!=b'\xff\xff' or p[2] not in range(1,6)
                or p[3:6]!=bytes([5,3,42]) or sum(p[2:])&255!=255):
            raise PermissionError('Only body Goal_Position packets are allowed')
        i=p[2]-1;data=p[6:-1];value=int.from_bytes(data,'little')
        if self.permit!=(i+1,42,data):raise PermissionError('Missing body goal permit')
        self.permit=None
        if self.goals is None or self.bounds is None:raise PermissionError('Body plan not prepared')
        low,high=self.bounds[i]
        if self.phase=='move':valid=low<=value<=high and abs(value-self.goals[i])<=2
        elif self.phase=='hold':
            valid=value==self.stop_positions[i] and low-8<=value<=high+8 and abs(value-self.goals[i])<=MAX_TRACKING_LEAD
        else:valid=False
        if not valid:raise PermissionError('Body goal outside reviewed envelope/step')
        return p

    def prepare(self,expected,target,saved):
        if (not isinstance(target,list) or len(target)!=6
                or any(type(v) is not int for v in target)):
            raise ValueError('Altı tam sayı hedef gerekli')
        q=self.positions()
        if any(abs(a-b)>3 for a,b in zip(q,expected)):raise ValueError('Kol önizlemeden sonra değişti')
        if target[5]!=expected[5]:raise ValueError('Bu hareket kıskacı değiştiremez')
        goals=[];bounds=[];effective=[];moving=set()
        for i in range(1,6):
            if self.read(i,40,1)!=1 or self.read(i,46)!=20 or self.read(i,44)!=0 or not 1<=self.read(i,48)<=500:
                raise ValueError('Sınırlı poz tutma ayarları değişti')
            goal=self.read(i,42)
            if abs(goal-q[i-1])>8:raise ValueError('Kol tutma hedefini izlemiyor')
            requested=goal if target[i-1]==expected[i-1] else target[i-1]
            if requested!=goal:moving.add(i)
            if abs(requested-goal)>170:raise ValueError('Tek konumlandırma en fazla 170 sayım/eklem')
            low,high=sorted((goal,requested));c=saved[JOINTS[i-1]]
            if low<c['range_min']+20 or high>c['range_max']-20:raise ValueError('Hedef kalibrasyon sınırının dışında')
            goals.append(goal);bounds.append((low,high));effective.append(requested)
        if self.read(6,40,1):raise ValueError('Kıskaç torku kapalı kalmalı')
        self.goals=goals;self.bounds=bounds;self.target=effective;self.moving=moving;self.phase='move'

    def write_goal(self,i,value):
        data=int(value).to_bytes(2,'little');self.permit=(i,42,data)
        try:
            comm,error=self.packet.write2ByteTxRx(self.port,i,42,value)
            if comm or error:raise OSError(f'Motor {i}: hedef yazma hatası {comm}/{error}')
        finally:self.permit=None
        if self.read(i,42)!=value:raise OSError(f'Motor {i}: hedef geri okuması uyuşmuyor')
        self.goals[i-1]=value

    def goal(self,target):
        q=self.positions()
        for i,value in enumerate(target):
            if not self.bounds[i][0]<=value<=self.bounds[i][1] or abs(value-self.goals[i])>2:
                raise ValueError('Hedef adımı veya çalışma aralığı aşıldı')
            if abs(value-q[i])>MAX_TRACKING_LEAD:raise ValueError('Motor hedefi izleyemiyor; konumlandırma durdu')
            if self.read(i+1,40,1)!=1:raise ValueError('Gövde torku kayboldu')
        for i,value in enumerate(target,1):
            if value!=self.goals[i-1]:self.write_goal(i,value)

    def hold(self):
        if self.phase!='move':return []
        errors=[];self.stop_positions=self.positions();self.phase='hold'
        for i,value in enumerate(self.stop_positions[:5],1):
            if i not in self.moving:continue
            try:
                if value!=self.goals[i-1]:self.write_goal(i,value)
            except Exception as exc:errors.append(str(exc))
        return errors

    def finish(self):
        errors=self.hold()
        if self.phase=='hold':self.phase='done'
        return errors


class BodyMotion:
    brain_driven=False
    duration=30

    def __init__(self,bus,saved,expected,target,clock=time.monotonic,thermal_pause_review=None):
        self.bus=bus;self.saved=saved;self.expected=expected;self.target=target;self.clock=clock
        self.started=None;self.last_tick=None;self.commands=0;self.settled_since=None
        self.stall_since=None;self.goals_finished_at=None
        self.thermal_review=thermal_pause_review;self.thermal_events=[]
        self.thermal_started=None;self.cool_since=None
        if thermal_pause_review is not None:
            if not isinstance(thermal_pause_review,str) or not thermal_pause_review.strip():
                raise ValueError('Sıcaklık duraklaması için ölçüm planı incelemesi gerekli')
            if not isinstance(target,list) or len(target)!=6:raise ValueError('Altı hedef gerekli')
            changed={i for i,(a,b) in enumerate(zip(expected,target)) if a!=b}
            if len(changed)!=1 or not changed<={0,4}:
                raise ValueError('Sıcaklık duraklaması yalnız tek taban/bilek dönüşü ölçümünde kullanılabilir')

    def start(self):
        self.bus.open();self.bus.verify(self.saved)
        telemetry(self.bus,self.saved)
        self.bus.prepare(self.expected,self.target,self.saved)
        self.target=self.bus.target+[self.expected[5]]
        self.started=self.last_tick=self.clock()

    def step(self,drive,visible,heartbeat_age,source_age):
        now=self.clock()
        if self.started is None or now-self.started>=self.duration:raise ValueError('Konumlandırma süresi doldu')
        if heartbeat_age>1 or not 0<=source_age<=.4:raise ValueError('Panel veya kamera güncel değil')
        dt=now-self.last_tick;self.last_tick=now
        if dt>.25:raise ValueError('Konumlandırma döngüsü 250 ms sınırını aştı')
        q,rows=telemetry(self.bus,self.saved,permit_warm=self.thermal_review is not None)
        if source_age+self.clock()-now>.4:raise ValueError('Kamera ölçümü eskidi')
        if any(row['torque']!=(row['id']<6) for row in rows):raise ValueError('Tork durumu değişti')
        if abs(q[5]-self.expected[5])>8:raise ValueError('Kıskaç konumu dışarıdan değişti')
        if any(not low-8<=value<=high+8 for value,(low,high) in zip(q,self.bus.bounds)):
            raise ValueError('Ölçülen gövde konumu çalışma aralığını aştı')
        if self.thermal_review is not None:
            maximum=max(row['temperature_c'] for row in rows)
            if self.thermal_started is None and maximum>=50:
                if len(self.thermal_events)>=2:raise ValueError('Üçüncü sıcaklık uyarısı; ölçüm sonlandı')
                errors=self.bus.hold()
                if errors:raise OSError('; '.join(errors))
                self.thermal_started=now;self.cool_since=None
                self.settled_since=self.stall_since=self.goals_finished_at=None
                self.thermal_events.append(dict(wall_time=time.time(),start_t=now-self.started,
                    hold_q=q.copy(),motors=[row for row in rows if row['temperature_c']>=50]))
            if self.thermal_started is not None:
                if now-self.thermal_started>=8:raise ValueError('Sıcaklık sekiz saniyede kararlı biçimde normale dönmedi')
                if any(abs(q[i-1]-self.bus.goals[i-1])>8 for i in self.bus.moving):
                    raise ValueError('Sıcaklık beklemesinde tutma konumu kaydı')
                if maximum<45:
                    if self.cool_since is None:self.cool_since=now
                    if now-self.cool_since>=2:
                        self.thermal_events[-1]['resume_t']=now-self.started
                        self.thermal_started=None;self.cool_since=None;self.bus.phase='move'
                else:self.cool_since=None
                # Never advance on the warning, any waiting tick, or the resume tick.
                return self.status(q,rows,False)
        if dt>=.08 and self.bus.goals!=self.target[:5]:
            goals=[old+max(-2,min(2,new-old)) for old,new in zip(self.bus.goals,self.target)]
            blocked=[i for i,(value,measured) in enumerate(zip(goals,q))
                     if abs(value-measured)>MAX_TRACKING_LEAD]
            if blocked:
                if self.stall_since is None:self.stall_since=now
                if now-self.stall_since>1:
                    detail='; '.join(f'{JOINTS[i]} (motor {i+1}): ölçüm={q[i]}, '
                        f'son hedef={self.bus.goals[i]}, gönderilmeyen hedef={goals[i]}, '
                        f'takip sınırı={MAX_TRACKING_LEAD}' for i in blocked)
                    raise ValueError(f'Motor hedefi bir saniyede izleyemedi; konumlandırma durdu. {detail}')
            else:
                self.bus.goal(goals);self.commands+=1;self.stall_since=None
        goals_finished=self.bus.goals==self.target[:5]
        if goals_finished and self.goals_finished_at is None:self.goals_finished_at=now
        reached=goals_finished and max(abs(a-b) for a,b in zip(q[:5],self.target))<=8
        if goals_finished and not reached and now-self.goals_finished_at>2:
            detail='; '.join(f'{JOINTS[i]} (motor {i+1}): ölçüm={q[i]}, '
                f'hedef={self.target[i]}, fark={abs(q[i]-self.target[i])}, tolerans=8'
                for i in range(5) if abs(q[i]-self.target[i])>8)
            raise ValueError(f'Motor son hedefe iki saniyede yerleşemedi; konumlandırma durdu. {detail}')
        if reached:
            if self.settled_since is None:self.settled_since=now
        else:self.settled_since=None
        return self.status(q,rows,self.settled_since is not None and now-self.settled_since>=.5)

    def status(self,q,rows,complete):
        result=dict(q=q,motors=rows,goal=self.bus.goals.copy(),desired=self.target,
                    neural_command=False,complete=complete,thermal_paused=self.thermal_started is not None,
                    thermal_pauses=self.thermal_events.copy())
        if self.thermal_events:result['last_motor_warning']=self.thermal_events[-1]
        return result

    def stop(self):
        try:errors=self.bus.finish()
        finally:self.bus.close()
        if errors:raise OSError('; '.join(errors))
