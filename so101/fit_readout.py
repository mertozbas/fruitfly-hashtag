"""Ridge calibration of learned XYZ readout, using training episodes only.

The anatomical core, phase classifier and gripper readout remain frozen.
Targets are learned from demonstrations, never calculated in a live rollout.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import torch
from .policy import Policy,torch_model,OBS_SIZE,MEMORY_SIZE,PHASES


def fit(model,dataset,ridges=(1e-6,1e-5,1e-4,1e-3)):
    model=Path(model);p=Policy(model)
    if p.action_mode!='target' or p.motor_heads!=1:raise ValueError('Requires one target readout')
    with np.load(dataset,allow_pickle=False) as d:data={k:d[k].copy() for k in d.files}
    phases=np.asarray([PHASES.index(v) for v in data['phases']]);ids=data['episode_ids']
    x=data['observations'].astype(np.float32)
    if p.has_memory:
        previous=np.r_[0,phases[:-1]];previous[np.r_[True,ids[1:]!=ids[:-1]]]=0
        x=np.c_[x,data['memory'] if 'memory' in data else np.eye(MEMORY_SIZE,dtype=np.float32)[previous]]
    torch.set_num_threads(2);device=torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    actor=torch_model(p.circuit,p.input_mean,p.input_scale,motor_heads=p.motor_heads,all_core=p.all_core).to(device);actor.restore(model)
    features=[]
    with torch.no_grad():
        for start in range(0,len(x),512):
            _,layers,_=actor(torch.from_numpy(x[start:start+512]).to(device),details=True)
            features.append(layers[-1].cpu().numpy())
    h=np.c_[np.concatenate(features),np.ones(len(x))].astype(np.float64)
    train=ids%5!=0;val=~train
    y=np.arctanh(np.clip(data['actions'][:,:3],-.999,.999)).astype(np.float64)
    counts=np.bincount(phases[train],minlength=MEMORY_SIZE)
    weights=1/np.maximum(counts[phases[train]],1)
    weights/=weights.sum()
    a=h[train];b=y[train]
    covariance=a.T@(a*weights[:,None]);cross=a.T@(b*weights[:,None])
    with np.load(model,allow_pickle=False) as d:state={k:d[k].copy() for k in d.files}
    reports=[]
    for ridge in ridges:
        penalty=np.eye(h.shape[1])*ridge;penalty[-1,-1]=ridge*.01
        beta=np.linalg.solve(covariance+penalty,cross)
        candidate={k:v.copy() for k,v in state.items()}
        candidate['decoder'][:,:3]=beta[:-1];candidate['bias'][:3]=beta[-1]
        output=model.parent/f'readout-{ridge:g}.npz';np.savez_compressed(output,**candidate)
        error=np.tanh(h[val]@beta)-data['actions'][val,:3]
        reports.append(dict(path=str(output),ridge=ridge,validation_xyz_mse=float(np.square(error).mean()),
            checkpoint_sha256=hashlib.sha256(output.read_bytes()).hexdigest()))
    report=dict(method='phase-balanced ridge XYZ readout fit; core, memory and gripper frozen',
        model_sha256=hashlib.sha256(model.read_bytes()).hexdigest(),dataset_sha256=hashlib.sha256(Path(dataset).read_bytes()).hexdigest(),
        train_episodes=np.unique(ids[train]).tolist(),validation_episodes=np.unique(ids[val]).tolist(),candidates=reports)
    (model.parent/'readout-fit.json').write_text(json.dumps(report,indent=2))
    return reports

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('model');p.add_argument('--dataset',required=True);a=p.parse_args();print(json.dumps(fit(a.model,a.dataset)))
