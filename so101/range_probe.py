"""Explicitly requested, slow single-body-joint range characterization.

Separate from the +8-count microprobe: at most 170 counts (14.94 degrees),
2 counts per goal update, 8-count tracking/return tolerance, and 45 seconds.
No torque/configuration/EEPROM writes; no gripper; no automatic joint sequence.
Coarse range acceptance is not precision calibration or pick/place readiness.
"""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import time
import urllib.request

from .alignment_probe import ProbeBus
from .calibration_contract import atomic_json
from .hardware_contract import JOINTS,assert_read_packet,calibration

MAX_SPAN=170


class RangeBus(ProbeBus):
    body_holding=True

    def __init__(self,port,motor_id,span,direction=1):
        if type(motor_id) is not int or motor_id not in range(1,6):raise ValueError('One body motor 1..5 required')
        if type(span) is not int or not 1<=span<=MAX_SPAN:raise ValueError('Requested range must be 1..170 counts')
        if type(direction) is not int or direction not in (-1,1):raise ValueError('Invalid range direction')
        super().__init__(port);self.motor_id=motor_id;self.span=span;self.direction=direction;self.may_be_on=True

    def envelope(self):return sorted((self.initial,self.initial+self.direction*self.span))

    def guard(self,packet):
        p=bytes(packet)
        if len(p)>4 and p[4] in (1,2):return assert_read_packet(p)
        if len(p)!=9 or p[:2]!=b'\xff\xff' or p[2]!=self.motor_id or p[3]!=5 or p[4]!=3 or p[5]!=42 or sum(p[2:])&255!=255:
            raise PermissionError('Range test may write only selected joint Goal_Position')
        data=p[6:-1];v=int.from_bytes(data,'little')
        if self.permit!=(42,data):raise PermissionError('Missing one-packet range permit')
        self.permit=None
        low,high=self.envelope()
        if self.phase=='move':valid=low<=v<=high and abs(v-self.last_goal)<=2
        elif self.phase=='hold':valid=v==self.stop_position and low-8<=v<=high+8 and abs(v-self.last_goal)<=16
        else:valid=False
        if not valid:raise PermissionError('Range goal outside explicit span/step/phase')
        return p

    def prepare(self,q,saved):
        if self.phase!='read' or any(abs(a-b)>2 for a,b in zip(self.positions(),q)):raise ValueError('Arm moved before range test')
        for i in range(1,6):
            if self.read(i,40,1)!=1 or self.read(i,46)!=20 or self.read(i,44)!=0 or not 1<=self.read(i,48)<=500:
                raise ValueError('Expected unchanged limited pose hold')
            if abs(self.read(i,42)-q[i-1])>8:raise ValueError('Existing holding error exceeds 8 counts')
        if self.read(6,40,1):raise ValueError('Gripper must remain off')
        self.initial=self.last_goal=self.read(self.motor_id,42)
        c=saved[JOINTS[self.motor_id-1]]
        low,high=self.envelope()
        if not c['range_min']+20<=low or high>c['range_max']-20:
            raise ValueError('Requested stroke outside calibrated margin')
        return dict(initial_position=q.copy(),initial_native_goal=self.initial,span_counts=self.span,
                    max_tracking_error_counts=8,return_tolerance_counts=8,native_velocity=20,
                    note='Coarse explicitly requested motor test; not a precision calibration pass')

    def finish(self):
        if self.phase in ('read','returned'):return []
        try:
            self.stop_position=self.positions()[self.motor_id-1];self.phase='hold'
            self.write(42,self.stop_position);self.phase='done';return []
        except Exception as exc:return [str(exc)]


def run_range(bus,saved,expected,check_live,save,decision,clock=time.monotonic,sleep=time.sleep,recovery_target=None):
    report=dict(status='preflight',motor_id=bus.motor_id,commanded_joint=JOINTS[bus.motor_id-1],
                brain_connected=False,closed_loop=False,joint_mapping_verified=False,samples=[],started_wall_time=time.time(),
                outbound_source='anatomical_vision_readout_magnitude',return_source='original_native_holding_goal')
    started=clock();q0=None;j=bus.motor_id-1
    def sample():
        begin=clock();check_live();q=bus.positions();telemetry=[]
        for i,n in enumerate(JOINTS):
            c=saved[n];margin=0 if i==5 else 20
            if not c['range_min']+margin<=q[i]<=c['range_max']-margin:raise ValueError('Joint outside calibrated margin')
            if bus.read(i+1,33,1)!=0 or bool(bus.read(i+1,40,1))!=(i<5):raise ValueError('Operating/torque state changed')
            temperature=bus.read(i+1,63,1);voltage=bus.read(i+1,62,1)/10
            reading=dict(id=i+1,temperature_c=temperature,voltage_v=voltage)
            telemetry.append(reading)
            if temperature>=50 or not 6<=voltage<=13.2:
                report['fault_observation']=dict(t=round(clock()-started,4),q=q,motor=reading)
                raise ValueError(f'Motor {i+1} temperature/voltage limit: {temperature} C, {voltage} V')
        if q0 is not None:
            if any(abs(a-b)>8 for i,(a,b) in enumerate(zip(q,q0)) if i!=j):raise ValueError('Other joint moved beyond coarse holding tolerance')
            if bus.initial is not None:
                low,high=bus.envelope()
                if not low-8<=q[j]<=high+8:raise ValueError('Measured joint exceeded stroke envelope')
        if clock()-started>45 or clock()-begin>.15:raise ValueError('Range test timing limit exceeded')
        report['samples'].append(dict(t=round(clock()-started,4),q=q,goal=bus.last_goal,telemetry=telemetry,phase=report.get('motion_phase','preflight')))
        return q
    try:
        bus.open();bus.verify(saved);q0=sample()
        if any(abs(a-b)>3 for a,b in zip(q0,expected)):raise ValueError('Arm changed since reviewed snapshot')
        neural=decision() if recovery_target is None else {'bias_free_drive':1.}
        drive=neural['bias_free_drive']
        if type(drive) not in (int,float) or not -1<=drive<=1:raise ValueError('Invalid neural drive')
        target=round(bus.span*abs(drive))
        # Keep the original microprobe readout as provenance, but explicitly
        # distinguish its 8-count adapter from this reviewed range adapter.
        report.update(neural_decision=neural,requested_delta_counts=target,
                      motor_adapter=f'round({bus.span} * abs(bias_free_drive)) positive encoder counts on motor {bus.motor_id}',
                      neural_readout_microprobe_delta_counts=neural.get('delta_counts'),
                      directional_mapping=False,silenced_range_delta_counts=0,
                      scope='Single explicitly reviewed joint range test; no grasp attempt or learned six-joint control')
        if target==0:
            report.update(status='neural_hold',motion_observed=False);return report
        report.update(bus.prepare(q0,saved))
        if recovery_target is not None:
            if type(recovery_target) is not int or recovery_target!=bus.initial+bus.direction*bus.span:
                raise ValueError('Recorded return target does not match bounded stroke')
            report.update(neural_decision=None,outbound_source='recorded_test_return',return_source=None,
                          recovery_target_counts=recovery_target,
                          motor_adapter='Return within previously observed range to its original native holding goal',
                          neural_readout_microprobe_delta_counts=None,scope='Deterministic recovery, not a neural action')
        report['status']='prepared';save(report)
        bus.phase='move'
        def go(goal):
            # Wait for existing goal to track; do not increase the permitted lead.
            wait_until=clock()+1
            while True:
                q=sample()
                if abs(goal-q[j])<=8:break
                # A two-count step may cross the lead limit by one count.
                # Try its one-count intermediate ONLY within the same limit.
                intermediate=bus.last_goal+(1 if goal>bus.last_goal else -1)
                if abs(goal-bus.last_goal)==2 and abs(intermediate-q[j])<=8:
                    bus.goal(intermediate)
                    if report['motion_phase']=='outbound' and recovery_target is None:report['brain_connected']=True
                    sleep(.05);continue
                if clock()>=wait_until:raise ValueError('Motor did not track; stroke stopped without enlargement')
                sleep(.05)
            bus.goal(goal)
            if report['motion_phase']=='outbound' and recovery_target is None:report['brain_connected']=True
            sleep(.1);sample()
        report['motion_phase']='outbound'
        for delta in list(range(2,target,2))+[target]:go(bus.initial+bus.direction*delta)
        for _ in range(5):sleep(.1);sample()
        peak=sample()[j];report['outbound_position']=peak
        if abs(peak-(bus.initial+bus.direction*target))>8:raise ValueError('Outbound target not reached within coarse tolerance')
        if recovery_target is not None:
            report.update(status='returned_recorded_range',final_position=sample(),return_error_counts=peak-recovery_target,
                          motion_observed=bus.direction*(peak-q0[j])>=max(1,target-8))
            bus.phase='returned';return report
        report['motion_phase']='safety_return'
        for delta in list(range(target-2,0,-2))+[0]:go(bus.initial+bus.direction*delta)
        for _ in range(10):sleep(.1);sample()
        final=sample();error=final[j]-q0[j]
        report.update(final_position=final,return_error_counts=error,motion_observed=bus.direction*(peak-q0[j])>=max(1,target-8))
        report['status']=('no_confirmed_motion' if not report['motion_observed'] else
                          'passed_coarse_range' if abs(error)<=8 else 'return_outside_tolerance')
        if report['status']=='passed_coarse_range':bus.phase='returned'
    except Exception as exc:report.update(status='failed',error=str(exc))
    finally:
        errors=bus.finish()
        if errors:report.update(status='failed',cleanup_errors=errors)
        try:
            if q0 is not None:
                report['post_cleanup_position']=bus.positions()
                report['measured_peak_counts']=max(bus.direction*(s['q'][j]-q0[j]) for s in report['samples'])
                bus.verify(saved);report['calibration_preserved']=True
        except Exception as exc:report.update(status='failed',verification_error=str(exc))
        report['duration_s']=round(clock()-started,4)
        bus.close();save(report)
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);args=p.parse_args();plan=json.loads(args.plan.read_text())
    if (plan.get('kind') not in ('explicit_neural_range_v1','recorded_range_return_v1') or plan.get('explicit_range_request') is not True
            or plan.get('base_mounted') is not True or plan.get('workspace_clear') is not True):
        raise ValueError('Explicitly requested and visually reviewed range plan required')
    if not 0<=time.time()-plan['created']<=20:raise ValueError('Plan expired')
    if not isinstance(plan.get('q'),list) or len(plan['q'])!=6 or any(type(v) is not int for v in plan['q']):raise ValueError('Invalid reviewed joint state')
    recovery_target=None
    if plan['kind']=='recorded_range_return_v1':
        raw=Path(plan['source_result_path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=plan['source_result_sha256']:raise ValueError('Source motion record changed')
        source=json.loads(raw)
        if source.get('status')!='failed' or source.get('motor_id')!=plan['motor_id'] or source.get('calibration_preserved') is not True:
            raise ValueError('Not a failed, calibration-preserving range record')
        recovery_target=source['initial_native_goal']
        q=plan['q'][plan['motor_id']-1]
        native=plan.get('start_native_goal')
        if (type(native) is not int or abs(q-native)>3 or not recovery_target<native<=recovery_target+source['span_counts']
                or plan['span_counts']!=native-recovery_target):
            raise ValueError('Return must stay inside the previously reviewed positive stroke')
    bus=RangeBus(plan['port'],plan['motor_id'],plan['span_counts'],-1 if recovery_target is not None else 1)
    cal=calibration(plan['calibration_path'])
    if not cal['valid'] or cal['sha256']!=plan['calibration_sha256']:raise ValueError('Calibration changed')
    from serial.tools import list_ports
    if len([x for x in list_ports.comports() if x.device==plan['port'] and x.serial_number==plan['serial_number']])!=1:raise ValueError('USB identity changed')
    with args.plan.with_suffix('.claimed').open('x') as f:f.write('one-shot\n')
    def check_live():
        if hashlib.sha256(Path(plan['calibration_path']).read_bytes()).hexdigest()!=cal['sha256']:raise ValueError('Calibration file changed')
        with urllib.request.urlopen('http://127.0.0.1:8766/api/hardware/state',timeout=.25) as response:s=json.load(response)
        for role in ('wrist','top'):
            c=s['cameras'][role]
            if not c.get('fresh') or c.get('age_ms',10000)>400 or c.get('session')!=plan['cameras'][role]:raise ValueError('Reviewed camera lost or changed')
        if s.get('calibration_session',{}).get('running'):raise ValueError('Calibration active')
    def cancel(*_):raise RuntimeError('Range test interrupted')
    signal.signal(signal.SIGTERM,cancel);signal.signal(signal.SIGINT,cancel)
    from .neural_wrist import live_decision
    report=run_range(bus,cal['motors'],plan['q'],check_live,lambda r:atomic_json(args.plan.with_name('result.json'),r),lambda:live_decision(plan),recovery_target=recovery_target)
    print(json.dumps({k:v for k,v in report.items() if k not in ('samples','neural_decision')}))
    return 0 if report['status'] in ('passed_coarse_range','neural_hold','returned_recorded_range') else 1


if __name__=='__main__':raise SystemExit(main())
