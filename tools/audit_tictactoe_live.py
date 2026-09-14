"""Replay live neural telemetry and observe one bounded robot game over HTTP."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from tictactoe.policy import Policy
from tictactoe.motor import Motor


def audit(base,model,output,timeout=720):
    model=Path(model);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    policy=Policy(model);motor=Motor(policy,model);sha=hashlib.sha256(model.read_bytes()).hexdigest()
    def api(path,body=None):
        request=urllib.request.Request(base+'/api/'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=15) as r:return json.load(r)
    def state():return api('state')['simulation']
    api('control',dict(op='model',model=model.parent.name))
    end=time.monotonic()+30
    while time.monotonic()<end:
        s=state()
        if s.get('model_sha256')==sha:break
        time.sleep(.2)
    else:raise AssertionError('Model did not load')
    api('tictactoe/settings',dict(opponent='self',agent=1,execution='robot'))
    checks={};replays=[];phases=set();paused_test=False;start=time.monotonic();last_move=-1
    while time.monotonic()-start<timeout:
        s=state();g=s.get('game',{})
        if g.get('execution')!='robot':time.sleep(.2);continue
        if g.get('error') and s.get('paused'):raise AssertionError(g['error'])
        if s.get('model_sha256')!=sha:raise AssertionError('Checkpoint changed')
        if s.get('neural',{}).get('displayed_pass')=='motor' and g.get('motor'):
            m=g['motor'];action,layers,inputs=motor.activity(m['coordinates'],m['phase_index'])
            activity_error=float(np.max(np.abs(np.concatenate(layers)-s['activity'])))
            action_error=float(np.max(np.abs(action-m['action'])))
            if activity_error>1e-6 or action_error>1e-7:raise AssertionError('Live neural replay mismatch')
            if s['neural']['decision_applied']:
                np.testing.assert_allclose(s['neural']['applied_action'],action,atol=1e-7)
            if m['phase'] not in phases:
                replays.append(dict(phase=m['phase'],activity_max_error=activity_error,action_max_error=action_error,frame_id=s['neural']['sensor_frame_id']))
                phases.add(m['phase']);print('PHASE '+m['phase'],flush=True)
            if not paused_test and m['elapsed_s']>8:
                api('control',dict(op='pause',paused=True))
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    a=state()
                    if a.get('paused'):break
                    time.sleep(.1)
                else:raise AssertionError('Pause not acknowledged')
                time.sleep(.8);b=state()
                checks['pause_freezes_arm_and_neural_sample']=a['position_mm']==b['position_mm'] and a['activity']==b['activity'] and a['neural']['sensor_frame_id']==b['neural']['sensor_frame_id']
                (output/'motor-packet.json').write_text(json.dumps({k:b[k] for k in ('model','model_sha256','activity','neural','game','position_mm')},indent=2))
                (output/'motor-wrist.jpg').write_bytes(base64.b64decode(b['eyes']['rgb']))
                api('control',dict(op='pause',paused=False));paused_test=True
        if len(g.get('move_log',[]))!=last_move:
            last_move=len(g.get('move_log',[]));print('MOVES '+str(last_move)+' '+str(g.get('board')),flush=True)
        if s.get('outcome')=='draw':
            checks['complete_nine_move_game']=len(g['move_log'])==9
            checks['five_robot_contact_placements']=sum(m['source']=='connectome_motor_contact_physics' for m in g['move_log'])==5
            checks['four_virtual_opponent_moves']=sum(m['source']=='connectome_strategy' for m in g['move_log'])==4
            checks['camera_confirms_final_board']=g['observed']['valid'] and g['observed']['board']==g['board']
            episode=s['episode'];break
        time.sleep(.25)
    else:raise AssertionError('Live robot game exceeded bounded timeout')
    deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        next_state=state()
        if next_state.get('episode',0)>episode:break
        time.sleep(.2)
    checks['automatic_robot_loop']=next_state['episode']>episode
    checks['all_motor_phases_replayed']=len(phases)==9
    report=dict(passed=all(checks.values()),checks=checks,replays=replays,model_sha256=sha,wall_seconds=time.monotonic()-start,
                final_board=g['board'],moves=g['move_log'],scope='HTTP worker telemetry and simulated contact physics; no hardware')
    (output/'live-audit.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    api('control',dict(op='pause',paused=True))
    if not report['passed']:raise AssertionError('Live audit failed')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:8772');p.add_argument('--model',required=True)
    p.add_argument('--output',default='artifacts/tictactoe/live');p.add_argument('--timeout',type=int,default=720)
    a=p.parse_args();audit(a.base,a.model,a.output,a.timeout)
