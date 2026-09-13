"""Fixed held-out physics conditions, plus optional causal interventions."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from navigation import BrainFlight, ROOT

CONDITIONS = [(22.,6.),(22.,-6.),(28.,9.),(28.,-9.),(24.,10.),(24.,-10.)]

def evaluate(flight, *, mode='connected', conditions=CONDITIONS, events=False):
    records=[]
    for i, goal in enumerate(conditions):
        flight.reset(seed=101+i,goal=goal,ablation=mode)
        t=flight.telemetry(); initial=t['distance_mm']; minimum=initial
        min_alt=t['altitude_mm']; max_tracking=0.; commands=[]; snapshots=[]
        start=time.monotonic()
        for step in range(round(flight.seconds/flight.control_dt)+1):
            flight.step();t=flight.telemetry()
            assert np.isfinite(flight.env.physics.data.qpos).all()
            assert not np.any(flight.env.physics.data.xfrc_applied)
            minimum=min(minimum,t['distance_mm']);min_alt=min(min_alt,t['altitude_mm'])
            max_tracking=max(max_tracking,t['tracking_error_mm'])
            if step%50==0:
                commands.append(t['yaw_rate_rad_s'])
                snapshots.append(dict(time_s=t['time_s'],odor=t['odor'],readout=t['steering'],applied=t['applied_steering'],yaw_rate=t['yaw_rate_rad_s'],position=t['position_mm']))
            if t['done']:break
        record=dict(goal_mm=list(goal),seed=101+i,intervention=mode,success=t['success'],
            fallen=bool(flight.ts.last() and flight.ts.discount==0),time_s=t['time_s'],
            initial_distance_mm=initial,final_distance_mm=t['distance_mm'],closest_distance_mm=minimum,
            position_mm=t['position_mm'],min_altitude_mm=min_alt,max_tracking_error_mm=max_tracking,
            yaw_range_rad_s=[min(commands),max(commands)],wall_seconds=time.monotonic()-start,trace=snapshots)
        records.append(record)
        if events:print('LAB_EVENT '+json.dumps(dict(status='evaluating',evaluated=i+1,evaluation_total=len(conditions),success_count=sum(r['success'] for r in records))),flush=True)
        else:print(json.dumps({k:v for k,v in record.items() if k!='trace'}),flush=True)
    return dict(task='flight',episodes=len(records),success_count=sum(r['success'] for r in records),
        falls=sum(r['fallen'] for r in records),mean_final_distance_mm=float(np.mean([r['final_distance_mm'] for r in records])),results=records)

def main():
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--output',type=Path);p.add_argument('--causal',action='store_true');p.add_argument('--events',action='store_true');args=p.parse_args()
    flight=BrainFlight(args.model)
    report=evaluate(flight,events=args.events)
    report.update(model_sha256=flight.brain_sha,circuit_identity=flight.brain.circuit.identity,
                  controller=dict(yaw_gain=flight.yaw_gain,max_yaw_rate_rad_s=8.,speed_cm_s=flight.speed,brain_dt=flight.brain_dt),
                  motor='FlyBody pretrained wing controller',scope='Synthetic odor navigation via a MaleCNS-derived subgraph and artificial motor adapter')
    if args.causal:
        report['interventions']={mode:evaluate(flight,mode=mode,conditions=CONDITIONS[:2]) for mode in ['zero','reverse']}
        # Same seeds, goals, wing phase and physics. A zero or reversed readout
        # must fail these targets while the connected brain reaches them.
        assert all(r['success'] for r in report['results'][:2])
        assert all(v['success_count']==0 for v in report['interventions'].values())
        report['causal_check_passed']=True
    output=args.output or ROOT/'artifacts/lab/flight/checkpoints'/f'{flight.brain_sha}.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ['results','interventions']},indent=2),flush=True)
    flight.env.close()

if __name__=='__main__':main()
