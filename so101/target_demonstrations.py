"""Recover teacher targets from recorded state; verify against every old action.

This transforms supervised labels only. Live inference never imports this file.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from .policy import TARGET_CENTER,TARGET_SCALE


def convert(source,output):
    with np.load(source,allow_pickle=False) as data:
        values={k:data[k].copy() for k in data.files}
    if str(values.get('action_mode','delta'))!='delta':raise ValueError('Expected delta-action demonstrations')
    targets=[];anchor=None;last_id=None;last_phase=None;errors=[]
    for obs,action,phase,episode in zip(values['observations'],values['actions'],values['phases'],values['episode_ids']):
        ee=obs[12:15]*.15+[.06,-.18,.06]
        cube=ee+obs[15:18]*.15;goal=cube+obs[18:21]*.15
        if episode!=last_id:anchor=None;last_phase=None
        if phase=='close' and last_phase!='close':anchor=ee.copy()
        if phase in {'close','lift'} and anchor is None:raise ValueError('Missing demonstrated grasp anchor')
        target={'approach':cube+[0,0,.065],'lower':cube+[0,0,.005],
            'close':anchor,'lift':np.r_[anchor[:2] if anchor is not None else cube[:2],.11],
            'transport':np.r_[goal[:2],.11],'place':np.r_[goal[:2],.043],
            'release':np.r_[goal[:2],.043],'retreat':np.r_[goal[:2],.115]}[phase]
        errors.append(float(np.max(np.abs(np.clip((target-ee)*100,-1,1)-action[:3]))))
        targets.append(np.r_[(target-TARGET_CENTER)/TARGET_SCALE,action[3]])
        last_id=episode;last_phase=phase
    if max(errors)>2e-4:raise ValueError(f'Teacher target reconstruction mismatch: {max(errors)}')
    values['actions']=np.asarray(targets,dtype=np.float32)
    if np.max(np.abs(values['actions']))>1:raise ValueError('Target outside output range')
    values['action_mode']=np.array('target')
    np.savez_compressed(output,**values)
    report=dict(source=str(source),source_sha256=hashlib.sha256(Path(source).read_bytes()).hexdigest(),
        frames=len(targets),maximum_original_action_error=max(errors),method='Verified teacher-target label transformation; no live teacher')
    Path(output).with_suffix('.json').write_text(json.dumps(report,indent=2))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('output');a=p.parse_args();print(convert(a.source,a.output))
