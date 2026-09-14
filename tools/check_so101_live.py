"""Replay one exact live robot decision and audit displayed connection gains."""
import argparse
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
import numpy as np
from so101.policy import Policy


def check(base,model,output):
    def request(path,body=None):
        data=None if body is None else json.dumps(body).encode()
        req=urllib.request.Request(base+path,data=data,headers={'Content-Type':'application/json','Origin':base})
        with urllib.request.urlopen(req,timeout=20) as r:return json.load(r)
    def wait(predicate,seconds=20):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            s=request('/api/state')['simulation']
            if predicate(s):return s
            time.sleep(.1)
        raise AssertionError('Live state timeout')
    request('/api/control',dict(op='pause',paused=False))
    s=wait(lambda s:s.get('behavior')=='so101' and s.get('neural',{}).get('decision_applied'))
    p=Policy(model);x=np.asarray(s['robot']['decision_observation'],np.float32)
    if p.has_memory:x=np.r_[x,s['robot']['learned_memory']]
    action,layers=p.activity(x)
    np.testing.assert_allclose(action,s['neural']['applied_action'],atol=2e-6)
    activity=np.concatenate(layers)
    np.testing.assert_array_equal(activity.round(6),np.asarray(s['activity'],np.float32))
    if s['robot'].get('sensor_mode')=='camera':
        perception=s['robot']['perception']
        assert s['neural']['sensor_frame_id']==perception['frame_id']
        assert s['neural']['sample_time_s']==perception['sample_time_s']
        assert perception['camera_name']==s['neural']['sensor_camera']=='wrist'
        assert perception['camera_mount']=='gripper'
        assert set(s['eyes'])=={'rgb','depth','detection'}
    details=request('/api/model/'+s['model'])
    assert details['sha256']==s['model_sha256']
    for expected,actual in zip(p.input_sums,details['input_sums']):np.testing.assert_allclose(expected,actual,rtol=1e-6)
    graph=request('/api/graph?model='+s['model'])
    with np.load(Path(model).parent/'body_ids.npz') as data:body_ids={g:data[g].copy() for g in p.circuit.groups}
    for level in range(3):
        row,col=p.circuit.layers[level].nonzero();row,col=int(row[0]),int(col[0])
        source,target=int(body_ids[p.circuit.groups[level]][row]),int(body_ids[p.circuit.groups[level+1]][col])
        data=request(f'/api/connection/{source}/{target}?model='+s['model'])['model']
        assert data['trainable']
        np.testing.assert_allclose(data['current_weight'],p.layers[level][row,col],rtol=1e-6)
    rejected=[]
    for body in [dict(op='reset',goal=[99999,-155]),dict(op='sensor',sensor='unknown')]:
        try:request('/api/control',body)
        except urllib.error.HTTPError as exc:
            assert exc.code in (400,422);rejected.append(exc.code)
        else:raise AssertionError('Invalid robot control accepted')
    request('/api/control',dict(op='behavior',behavior='odor'))
    old=wait(lambda x:x.get('behavior')=='odor' and bool(x.get('activity')) and bool(x.get('image')),seconds=45)
    assert not old.get('error')
    request('/api/control',dict(op='behavior',behavior='so101'))
    wait(lambda x:x.get('behavior')=='so101' and x.get('model_sha256')==s['model_sha256'])
    report=dict(model=s['model'],checkpoint_sha256=s['model_sha256'],neurons=len(activity),
        maximum_activity_replay_error=float(np.max(np.abs(activity-s['activity']))),
        camera_frame_matches_neural_decision=s['robot'].get('sensor_mode')=='camera',
        exact_motor_replay=True,all_layer_connection_weights=True,located_neurons=len(graph['nodes']),located_connections=len(graph['edges']),invalid_controls_rejected=rejected,odor_round_trip=True)
    Path(output).write_text(json.dumps(report,indent=2));return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:8772');p.add_argument('--model',default='models/lab_runs/local-so101-validated-seed42/trained.npz');p.add_argument('--output',default='artifacts/so101/live-replay.json')
    a=p.parse_args();print(json.dumps(check(a.base,a.model,a.output),indent=2))
