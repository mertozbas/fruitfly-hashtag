"""Latch measured positions of body motors 1..5 while the operator supports the arm.

The gripper remains off. No motion targets other than the measured pose, no
EEPROM writes, and no automatic torque release that could drop the arm.
"""
import time
from .alignment_probe import ProbeBus
from .hardware_contract import assert_read_packet,JOINTS


class HoldBus(ProbeBus):
    def guard(self,packet):
        p=bytes(packet)
        if len(p)>4 and p[4] in (1,2):return assert_read_packet(p)
        if len(p)<8 or p[:2]!=b'\xff\xff' or p[2] not in range(1,6) or p[3]+4!=len(p) or p[4]!=3 or sum(p[2:])&255!=255:
            raise PermissionError('Hold may only address body motors 1..5')
        i,a,data=p[2],p[5],p[6:-1];value=int.from_bytes(data,'little')
        if self.permit!=(i,a,data):raise PermissionError('Missing hold packet permit')
        self.permit=None
        if self.phase=='setup':
            allowed=len(data)==2 and (a,value) in ((42,self.q0[i-1]),(44,0),(46,20),(48,self.caps[i]))
        else:allowed=self.phase=='enable' and len(data)==1 and a==40 and value==1
        if not allowed:raise PermissionError('Only the measured hold position is permitted')
        return p

    def write_for(self,i,a,v,size=2):
        self.permit=(i,a,int(v).to_bytes(size,'little'))
        try:
            comm,error=(self.packet.write1ByteTxRx if size==1 else self.packet.write2ByteTxRx)(self.port,i,a,v)
            if comm or error:raise OSError(f'Hold motor {i} write {a}: {comm}/{error}')
        finally:self.permit=None
        if self.read(i,a,size)!=v:raise OSError(f'Hold motor {i}: readback mismatch at {a}')


class HeldJointProbeBus(ProbeBus):
    """Probe one already supported body joint; never release supporting torque."""
    body_holding=True

    def __init__(self,port,motor_id):
        if type(motor_id) is not int or motor_id not in range(1,6):raise ValueError('One body motor 1..5 required')
        super().__init__(port);self.motor_id=motor_id;self.may_be_on=True

    def guard(self,packet):
        p=bytes(packet)
        if len(p)>4 and p[4] in (1,2):return assert_read_packet(p)
        if len(p)!=9 or p[:2]!=b'\xff\xff' or p[2]!=self.motor_id or p[3]!=5 or p[4]!=3 or p[5]!=42 or sum(p[2:])&255!=255:
            raise PermissionError('Held probe may write only the selected joint Goal_Position')
        data=p[6:-1];v=int.from_bytes(data,'little')
        if self.permit!=(42,data):raise PermissionError('Missing joint goal permit')
        self.permit=None
        if self.phase=='setup':valid=v==self.initial
        elif self.phase=='move':valid=self.initial<=v<=self.initial+8 and abs(v-self.last_goal)<=2
        elif self.phase=='hold':valid=v==self.stop_position and self.initial-3<=v<=self.initial+11 and abs(v-self.last_goal)<=8
        else:valid=False
        if not valid:raise PermissionError('Held joint goal outside reviewed range')
        return p

    def prepare(self,q):
        if self.phase!='read' or any(abs(a-b)>2 for a,b in zip(self.positions(),q)):raise ValueError('Arm moved before probe')
        for i in range(1,6):
            if self.read(i,40,1)!=1 or self.read(i,46)!=20 or self.read(i,44)!=0 or not 1<=self.read(i,48)<=500:
                raise ValueError('Expected verified limited pose hold')
            if abs(self.read(i,42)-q[i-1])>(3 if i==self.motor_id else 8):raise ValueError('Arm has not settled at its holding target')
        if self.read(6,40,1):raise ValueError('Gripper must remain off')
        self.initial=self.last_goal=q[self.motor_id-1]
        return dict(initial=q.copy(),span_counts=8,other_body_motors_holding=True)

    def enable(self):
        self.phase='setup';self.write(42,self.initial);self.phase='move'

    def finish(self):
        if self.phase=='read':return []
        self.phase='hold'
        try:
            self.stop_position=self.positions()[self.motor_id-1];self.write(42,self.stop_position);self.phase='done';return []
        except Exception as exc:return [str(exc)]


class HeldWristProbeBus(HeldJointProbeBus):
    def __init__(self,port):super().__init__(port,5)

def hold_current(bus,saved,expected,check_live,save,clock=time.monotonic,sleep=time.sleep):
    report=dict(status='preflight',brain_connected=False,joint_mapping_verified=False,gripper_commanded=False,
                samples=[],torque_may_be_on=False)
    start=clock();q0=None
    def sample():
        begin=clock();check_live();q=bus.positions()
        for i,n in enumerate(JOINTS,1):
            m=saved[n];margin=0 if i==6 else 20
            if not m['range_min']+margin<=q[i-1]<=m['range_max']-margin:raise ValueError(f'{n}: outside calibrated margin')
            if bus.read(i,33,1)!=0 or bus.read(i,63,1)>=50 or not 8<=bus.read(i,62,1)/10<=13.2:raise ValueError('Hold telemetry invalid')
        if q0 and any(abs(a-b)>6 for a,b in zip(q[:5],q0[:5])):raise ValueError('Arm moved beyond hold tolerance; keep supporting it')
        if clock()-begin>.15 or clock()-start>5:raise ValueError('Hold observation deadline exceeded')
        report['samples'].append(dict(t=round(clock()-start,4),q=q));return q
    try:
        bus.open();bus.verify(saved);q0=sample()
        if any(abs(a-b)>3 for a,b in zip(q0,expected)):raise ValueError('Arm moved since reviewed snapshot')
        if any(bus.read(i,40,1) for i in range(1,7)):raise ValueError('Expected initial torque off')
        before={i:{a:bus.read(i,a) for a in (42,44,46,48,16)} for i in range(1,6)}
        bus.caps={i:min(m[48],m[16],500) for i,m in before.items()}
        if any(v<=0 for v in bus.caps.values()):raise ValueError('Invalid holding torque limits')
        bus.q0=q0;report.update(status='prepared',initial=q0,sram_before=before,torque_caps=bus.caps)
        save(report) # durable before first configuration write
        bus.phase='setup'
        for i in range(1,6):
            for a,v in ((46,20),(44,0),(48,bus.caps[i]),(42,q0[i-1])):bus.write_for(i,a,v)
        if any(abs(a-b)>3 for a,b in zip(sample(),q0)):raise ValueError('Arm moved before torque enable')
        bus.phase='enable';report['torque_may_be_on']=True
        for i in range(1,6):bus.write_for(i,40,1,1)
        bus.phase='holding'
        for _ in range(10):
            sample()
            if any(bus.read(i,40,1)!=1 for i in range(1,6)) or bus.read(6,40,1):raise ValueError('Unexpected torque state')
            sleep(.05)
        bus.verify(saved);report.update(status='holding_at_measured_pose',calibration_preserved=True,
            note='Body motors hold their measured pose. Operator support must be withdrawn gradually under observation; gripper stays off.')
    except Exception as exc:report.update(status='failed',error=str(exc))
    finally:
        # Never disable a supporting motor automatically on timeout / process exit.
        try:report['torque_after']=[bool(bus.read(i,40,1)) for i in range(1,7)]
        except Exception as exc:report['torque_read_error']=str(exc)
        bus.close();save(report)
    return report


class RecordedReturnBus(HeldJointProbeBus):
    """Return inside an earlier measured excursion; no new search or wider range."""
    def __init__(self,port,motor_id,target):
        super().__init__(port,motor_id)
        if type(target) is not int:raise ValueError('Recorded integer target required')
        self.target=target

    def prepare(self,q):
        if not 1<=q[self.motor_id-1]-self.target<=8:raise ValueError('Return must stay within eight counts of the measured pose')
        report=super().prepare(q)
        return dict(report,return_target=self.target,span_counts=self.initial-self.target)

    def guard(self,packet):
        p=bytes(packet)
        if len(p)>4 and p[4] in (1,2):return assert_read_packet(p)
        if len(p)!=9 or p[:2]!=b'\xff\xff' or p[2]!=self.motor_id or p[3]!=5 or p[4]!=3 or p[5]!=42 or sum(p[2:])&255!=255:
            raise PermissionError('Return may only write the reviewed joint goal')
        data=p[6:-1];v=int.from_bytes(data,'little')
        if self.permit!=(42,data):raise PermissionError('Missing return goal permit')
        self.permit=None
        if self.phase=='setup':valid=v==self.initial
        elif self.phase=='move':valid=self.target<=v<=self.initial and 0<=self.last_goal-v<=2
        elif self.phase=='hold':valid=v==self.stop_position and self.target-3<=v<=self.initial+3 and abs(v-self.last_goal)<=8
        else:valid=False
        if not valid:raise PermissionError('Return outside the recorded excursion')
        return p


def recorded_return_target(plan):
    import hashlib,json
    from pathlib import Path
    source=Path(plan['reference_plan']).resolve()
    root=Path('.runtime/hardware/probes').resolve()
    if not source.is_relative_to(root) or source.name!='plan.json':raise ValueError('Local commissioning reference required')
    original=source.read_bytes();result=source.with_name('result.json').read_bytes()
    if hashlib.sha256(original+result).hexdigest()!=plan['reference_sha256']:raise ValueError('Reference record changed')
    prior=json.loads(original);report=json.loads(result)
    if prior.get('kind')!='held_joint_probe_v1' or report.get('status') not in ('no_confirmed_motion','return_outside_tolerance'):raise ValueError('An unresolved held probe is required')
    for key in ('motor_id','port','serial_number','calibration_sha256'):
        if prior.get(key)!=plan.get(key):raise ValueError('Reference belongs to another joint or robot')
    if report.get('motor_id')!=plan['motor_id'] or report.get('calibration_preserved') is not True:raise ValueError('Invalid measured reference')
    j=plan['motor_id']-1;initial=report['initial']
    if len(initial)!=6 or any(type(v) is not int for v in initial):raise ValueError('Invalid measured reference pose')
    if any(abs(plan['q'][i]-initial[i])>3 for i in range(6) if i!=j):raise ValueError('Other joints moved since the reference')
    if not 1<=plan['q'][j]-initial[j]<=8:raise ValueError('Reference return exceeds eight counts')
    return initial[j]


def return_recorded_pose(bus,saved,expected,check_live,save,clock=time.monotonic,sleep=time.sleep):
    report=dict(status='preflight',brain_connected=False,joint_mapping_verified=False,
                commanded_joint=JOINTS[bus.motor_id-1],motor_id=bus.motor_id,samples=[],started_wall_time=time.time())
    start=clock();q0=None;j=bus.motor_id-1
    def sample():
        begin=clock();check_live();q=bus.positions()
        for i,n in enumerate(JOINTS):
            c=saved[n];margin=0 if i==5 else 20
            if not c['range_min']+margin<=q[i]<=c['range_max']-margin:raise ValueError('Outside calibrated range')
            if bool(bus.read(i+1,40,1))!=(i<5) or bus.read(i+1,33,1)!=0:raise ValueError('Holding state changed')
            if bus.read(i+1,63,1)>=50 or not 8<=bus.read(i+1,62,1)/10<=13.2:raise ValueError('Invalid temperature or voltage')
        if q0 is not None:
            if any(abs(q[i]-q0[i])>3 for i in range(6) if i!=j):raise ValueError('Another joint moved')
            if not bus.target-3<=q[j]<=q0[j]+3:raise ValueError('Return envelope exceeded')
        if clock()-begin>.15 or clock()-start>5:raise ValueError('Return observation deadline exceeded')
        report['samples'].append(dict(t=round(clock()-start,4),q=q,goal=bus.last_goal));return q
    try:
        bus.open();bus.verify(saved);q0=sample()
        if any(abs(a-b)>2 for a,b in zip(q0,expected)):raise ValueError('Reviewed pose changed')
        report.update(bus.prepare(q0));report['status']='prepared';save(report)
        sample();bus.enable()
        while bus.last_goal>bus.target:
            sample();bus.goal(max(bus.target,bus.last_goal-2))
            for _ in range(2):sleep(.1);sample()
        # Observe a full two seconds at the final goal; no repeated goal writes.
        for _ in range(20):sleep(.1);sample()
        tail=report['samples'][-5:];error=tail[-1]['q'][j]-bus.target
        report.update(return_error_counts=error,final_position=tail[-1]['q'],motion_observed=any(s['q'][j]!=q0[j] for s in report['samples']))
        report['status']='returned_to_reference' if all(abs(s['q'][j]-bus.target)<=3 for s in tail) else 'return_outside_tolerance'
    except Exception as exc:report.update(status='failed',error=str(exc))
    finally:
        errors=bus.finish()
        if errors:report.update(status='failed',cleanup_errors=errors)
        report['torque_may_be_on']=bus.may_be_on
        try:
            if q0 is not None:bus.verify(saved);report['calibration_preserved']=True
        except Exception as exc:report.update(status='failed',verification_error=str(exc))
        bus.close();save(report)
    return report
