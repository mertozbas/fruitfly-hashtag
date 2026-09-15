"""One-use, bounded single-joint commissioning; not a policy controller.

A probe writes one reviewed motor within its initial position .. +8 counts and
returns. Held probes preserve body support. The unpowered variant is wrist-only.
No EEPROM writes. Failed probes are not automatically retried or enlarged.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import time
import urllib.request

from .calibration_contract import atomic_json
from .hardware_contract import JOINTS,assert_read_packet,calibration,compare_calibration,signed_magnitude

SPAN=8


class ProbeBus:
    body_holding=False
    motor_id=5
    def __init__(self,port):
        from scservo_sdk import PortHandler,PacketHandler
        owner=self
        class Port(PortHandler):
            def writePort(self,packet):return super().writePort(owner.guard(packet))
            def getCurrentTime(self):return time.monotonic()*1000
        self.port=Port(port);self.packet=PacketHandler(0);self.permit=None
        self.phase='read';self.initial=None;self.last_goal=None;self.backup={};self.may_be_on=False

    def guard(self,packet):
        p=bytes(packet)
        if len(p)>4 and p[4] in (1,2):return assert_read_packet(p)
        if len(p)<8 or p[:2]!=b'\xff\xff' or p[2]!=5 or p[3]+4!=len(p) or p[4]!=3 or sum(p[2:])&255!=255:
            raise PermissionError('Only one verified wrist motor may be written')
        address=p[5];data=p[6:-1];value=int.from_bytes(data,'little')
        if self.permit!=(address,data):raise PermissionError('Missing one-packet permit')
        self.permit=None
        allowed=False
        if self.phase=='setup':
            allowed=len(data)==2 and ((address,value) in ((44,0),(46,20),(48,self.backup.get(48,0))) or (address==42 and value==self.initial))
        elif self.phase=='enable':allowed=len(data)==1 and address==40 and value==1
        elif self.phase=='move':
            allowed=len(data)==2 and address==42 and self.initial<=value<=self.initial+SPAN and abs(value-self.last_goal)<=2
        elif self.phase=='off':allowed=len(data)==1 and address==40 and value==0
        elif self.phase=='restore':allowed=len(data)==2 and address in (44,46,48) and value==self.backup.get(address)
        if not allowed:raise PermissionError('Probe write outside its fixed phase/range')
        return p

    def open(self):
        if not self.port.openPort():raise OSError('Serial port unavailable')
        import fcntl,termios
        fcntl.ioctl(self.port.ser.fileno(),termios.TIOCEXCL)

    def close(self):
        if self.port.is_open:self.port.closePort()

    def read(self,i,address,size=2):
        value,comm,error=(self.packet.read1ByteTxRx if size==1 else self.packet.read2ByteTxRx)(self.port,i,address)
        if comm or error:raise OSError(f'Motor {i} read {address}: {comm}/{error}')
        return int(value)

    def write(self,address,value,size=2):
        self.permit=(address,int(value).to_bytes(size,'little'))
        try:
            comm,error=(self.packet.write1ByteTxRx if size==1 else self.packet.write2ByteTxRx)(self.port,self.motor_id,address,value)
            if comm or error:raise OSError(f'Motor {self.motor_id} write {address}: {comm}/{error}')
        finally:self.permit=None
        if self.read(self.motor_id,address,size)!=value:raise OSError(f'Motor {self.motor_id} readback mismatch at {address}')

    def positions(self):return [signed_magnitude(self.read(i,56),15) for i in range(1,7)]

    def verify(self,saved):
        actual={}
        for i,n in enumerate(JOINTS,1):
            if self.read(i,3)!=777 or self.read(i,33,1)!=0:raise ValueError('Expected six STS3215 in position mode')
            actual[n]=dict(id=i,range_min=self.read(i,9),range_max=self.read(i,11),homing_offset=signed_magnitude(self.read(i,31),11))
        if compare_calibration(saved,actual):raise ValueError('Calibration EEPROM mismatch')

    def prepare(self,q):
        if self.phase!='read':raise ValueError('Probe cannot be reused')
        if any(abs(a-b)>2 for a,b in zip(self.positions(),q)) or any(self.read(i,40,1) for i in range(1,7)):raise ValueError('Arm moved or torque was already enabled')
        self.initial=q[4];self.last_goal=q[4]
        self.backup={a:self.read(5,a) for a in (44,46,48)}
        if not 1<=self.backup[48]<=1000:raise ValueError('Unexpected wrist torque limit')
        self.cap=min(self.backup[48],self.read(5,16),100)
        if self.cap<=0:raise ValueError('Invalid wrist torque ceiling')
        return dict(sram_before=self.backup,initial=q.copy(),span_counts=SPAN,torque_cap=self.cap)

    def enable(self):
        self.phase='setup'
        self.write(46,20);self.write(44,0)
        # The cap is checked at the packet boundary as well as here.
        original=self.backup[48];self.backup[48]=self.cap
        try:self.write(48,self.cap)
        finally:self.backup[48]=original
        self.write(42,self.initial)
        if abs(self.positions()[4]-self.initial)>2:raise ValueError('Wrist moved before torque enable')
        self.phase='enable';self.may_be_on=True;self.write(40,1,1);self.phase='move'

    def goal(self,value):
        if self.phase!='move' or self.read(self.motor_id,40,1)!=1:raise ValueError('Probe motor torque lost')
        if abs(value-signed_magnitude(self.read(self.motor_id,56),15))>8:raise ValueError('Probe motor did not track the goal')
        self.write(42,value);self.last_goal=value

    def finish(self):
        errors=[]
        if self.phase=='read':return errors
        self.phase='off'
        try:self.write(40,0,1);self.may_be_on=False
        except Exception as exc:errors.append(str(exc))
        # Never restore settings unless torque-off was confirmed by readback.
        if not self.may_be_on and not errors:
            self.phase='restore'
            for address in (44,46,48):
                try:self.write(address,self.backup[address])
                except Exception as exc:errors.append(str(exc))
        self.phase='done';return errors


def run_probe(bus,saved,expected,check_live,save,clock=time.monotonic,sleep=time.sleep,decision=None):
    j=bus.motor_id-1
    report=dict(status='preflight',brain_connected=False,joint_mapping_verified=False,commanded_joint=JOINTS[j],motor_id=bus.motor_id,samples=[],started_wall_time=time.time())
    started=clock();q0=None
    def sample():
        begin=clock();check_live();q=bus.positions()
        if clock()-begin>.15:raise ValueError('Probe observation deadline exceeded')
        for i,n in enumerate(JOINTS):
            c=saved[n]
            margin=0 if n=='gripper' else 20
            if not c['range_min']+margin<=q[i]<=c['range_max']-margin:raise ValueError(f'{n}: outside calibrated margin')
            if bus.read(i+1,33,1)!=0:raise ValueError('Operating mode changed')
            if bus.read(i+1,63,1)>=50 or not 6<=bus.read(i+1,62,1)/10<=13.2:raise ValueError('Temperature or voltage outside preflight limits')
            if i!=j and bool(bus.read(i+1,40,1))!=(bus.body_holding and i<5):raise ValueError('Another motor torque changed')
        if q0 is not None:
            if any(abs(a-b)>3 for i,(a,b) in enumerate(zip(q,q0)) if i!=j):raise ValueError('Another joint moved; stop probe')
            if not q0[j]-3<=q[j]<=q0[j]+SPAN+3:raise ValueError('Joint exceeded probe envelope')
        if clock()-started>5:raise ValueError('Probe time limit exceeded')
        if clock()-begin>.15:raise ValueError('Probe telemetry deadline exceeded')
        report['samples'].append(dict(t=round(clock()-started,4),q=q,goal=bus.last_goal))
        return q
    try:
        bus.open();bus.verify(saved);q0=sample()
        if any(abs(a-b)>3 for a,b in zip(q0,expected)):raise ValueError('Arm changed since reviewed snapshot')
        target=SPAN
        if decision is not None:
            if bus.motor_id!=5 or not bus.body_holding:raise ValueError('Neural pulse requires the already held wrist')
            neural=decision();target=neural['delta_counts']
            if type(target) is not int or not 0<=target<=SPAN:raise ValueError('Neural target outside existing wrist envelope')
            report.update(neural_decision=neural,requested_delta_counts=target,
                          outbound_source='anatomical_vision_readout',return_source='deterministic_safety_return',closed_loop=False)
            if target==0:
                report.update(status='neural_hold',motion_observed=False,measured_peak_counts=0,return_error_counts=0)
                return report
        report.update(bus.prepare(q0));report['status']='prepared';save(report) # durable before ANY write
        sample();bus.enable();sample()
        outbound=list(range(2,target,2))+[target]*5
        returning=list(range(target-2,0,-2))+[0]*5
        for phase,deltas in (('outbound',outbound),('safety_return',returning)):
            report['motion_phase']=phase
            for delta in deltas:
                sample();bus.goal(q0[j]+delta)
                if decision is not None and phase=='outbound' and delta>0:report['brain_connected']=True
                sleep(.075);sample()
        maximum=max(p['q'][j]-q0[j] for p in report['samples'])
        final=report['samples'][-1]['q'];report.update(measured_peak_counts=maximum,final_position=final)
        return_error=final[j]-q0[j]
        report.update(motion_observed=maximum>=5,return_error_counts=return_error)
        report['status']=('no_confirmed_motion' if maximum<5 else
                          'passed' if abs(return_error)<=3 else 'return_outside_tolerance')
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


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan',type=Path,required=True);args=parser.parse_args()
    plan=json.loads(args.plan.read_text())
    kind=plan.get('kind')
    if kind not in ('wrist_probe_v1','held_wrist_probe_v1','held_neural_wrist_v1','held_joint_probe_v1','held_return_v1','hold_current_v1') or plan.get('base_mounted') is not True:raise ValueError('Reviewed fixed commissioning plan required')
    if kind in ('wrist_probe_v1','held_wrist_probe_v1','held_neural_wrist_v1','held_joint_probe_v1','held_return_v1') and plan.get('workspace_clear') is not True:raise ValueError('Clear reviewed joint workspace required')
    if kind=='hold_current_v1' and plan.get('operator_supporting') is not True:raise ValueError('Operator must support the arm during initial hold')
    if kind in ('held_joint_probe_v1','held_return_v1') and (type(plan.get('motor_id')) is not int or plan['motor_id'] not in range(1,5)):raise ValueError('One reviewed body joint 1..4 required')
    if not 0<=time.time()-plan['created']<=20:raise ValueError('Plan expired')
    if not isinstance(plan.get('q'),list) or len(plan['q'])!=6 or any(type(v) is not int for v in plan['q']):raise ValueError('Invalid plan joints')
    cal=calibration(plan['calibration_path'])
    if not cal['valid'] or cal['sha256']!=plan['calibration_sha256']:raise ValueError('Calibration changed')
    from serial.tools import list_ports
    matching=[p for p in list_ports.comports() if p.device==plan['port'] and p.serial_number==plan['serial_number']]
    if len(matching)!=1:raise ValueError('USB identity changed')
    with args.plan.with_suffix('.claimed').open('x') as claim:claim.write('one-shot\n')
    def check_live():
        if hashlib.sha256(Path(plan['calibration_path']).read_bytes()).hexdigest()!=cal['sha256']:raise ValueError('Calibration file changed')
        with urllib.request.urlopen('http://127.0.0.1:8766/api/hardware/state',timeout=.25) as response:state=json.load(response)
        for role in ('wrist','top'):
            camera=state['cameras'][role]
            if not camera.get('fresh') or camera.get('age_ms',10000)>400 or camera.get('session')!=plan['cameras'][role]:raise ValueError('Reviewed camera stream lost or changed')
        if state.get('calibration_session',{}).get('running'):raise ValueError('Calibration process active')
    def cancel(*_):raise RuntimeError('Probe interrupted')
    signal.signal(signal.SIGTERM,cancel);signal.signal(signal.SIGINT,cancel)
    if kind=='hold_current_v1':
        from .pose_hold import HoldBus,hold_current
        runner,bus=hold_current,HoldBus(plan['port'])
    elif kind=='held_return_v1':
        from .pose_hold import RecordedReturnBus,recorded_return_target,return_recorded_pose
        runner,bus=return_recorded_pose,RecordedReturnBus(plan['port'],plan['motor_id'],recorded_return_target(plan))
    elif kind=='held_joint_probe_v1':
        from .pose_hold import HeldJointProbeBus
        runner,bus=run_probe,HeldJointProbeBus(plan['port'],plan['motor_id'])
    elif kind in ('held_wrist_probe_v1','held_neural_wrist_v1'):
        from .pose_hold import HeldWristProbeBus
        runner,bus=run_probe,HeldWristProbeBus(plan['port'])
    else:runner,bus=run_probe,ProbeBus(plan['port'])
    options={}
    if kind=='held_neural_wrist_v1':
        from .neural_wrist import live_decision
        options['decision']=lambda:live_decision(plan)
    report=runner(bus,cal['motors'],plan['q'],check_live,lambda record:atomic_json(args.plan.with_name('result.json'),record),**options)
    printed={k:v for k,v in report.items() if k not in ('neural_decision','samples')} if options else report
    print(json.dumps(printed,ensure_ascii=False));return 0 if report['status'] in ('passed','holding_at_measured_pose','returned_to_reference','neural_hold') else 1


if __name__=='__main__':raise SystemExit(main())
