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


def fit(model,dataset,ridges=(1e-6,1e-5,1e-4,1e-3),phase_heads=False,
        motor_phase_feedback=False,progress_supervision=False,planar_heights=False):
    model=Path(model);p=Policy(model)
    if p.action_mode!='target':raise ValueError('Requires a target readout')
    if phase_heads and not p.has_memory:raise ValueError('Phase heads require learned phase memory')
    feedback=bool(motor_phase_feedback or p.motor_phase_feedback)
    supervised=bool(progress_supervision or p.progress_supervision)
    if (feedback or supervised or planar_heights) and not (phase_heads or p.motor_heads==MEMORY_SIZE):
        raise ValueError('Supervised motor skills require eight phase heads')
    with np.load(dataset,allow_pickle=False) as d:data={k:d[k].copy() for k in d.files}
    phases=np.asarray([PHASES.index(v) for v in data['phases']]);ids=data['episode_ids']
    x=data['observations'].astype(np.float32)
    if p.has_memory:
        previous=np.r_[0,phases[:-1]];previous[np.r_[True,ids[1:]!=ids[:-1]]]=0
        context=np.eye(MEMORY_SIZE,dtype=np.float32)[phases] if feedback else data['memory'] if 'memory' in data else np.eye(MEMORY_SIZE,dtype=np.float32)[previous]
        x=np.c_[x,context]
    torch.set_num_threads(2);device=torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    actor=torch_model(p.circuit,p.input_mean,p.input_scale,motor_heads=p.motor_heads,all_core=p.all_core).to(device);actor.restore(model)
    features=[]
    with torch.no_grad():
        for start in range(0,len(x),512):
            phase=torch.as_tensor(phases[start:start+512],device=device) if p.motor_phase_feedback else None
            _,layers,_=actor(torch.from_numpy(x[start:start+512]).to(device),details=True,phase=phase)
            features.append(layers[-1].cpu().numpy())
    h=np.c_[np.concatenate(features),np.ones(len(x))].astype(np.float64)
    train=ids%5!=0;val=~train
    y=np.arctanh(np.clip(data['actions'][:,:3],-.999,.999)).astype(np.float64)
    heads=MEMORY_SIZE if phase_heads else p.motor_heads
    systems=[]
    for head in range(heads):
        selected=train & (phases==head) if heads>1 else train
        if not selected.any():raise ValueError(f'Missing training examples for motor head {head}')
        counts=np.bincount(phases[selected],minlength=MEMORY_SIZE)
        weights=1/np.maximum(counts[phases[selected]],1);weights/=weights.sum()
        a=h[selected];b=y[selected]
        systems.append((a.T@(a*weights[:,None]),a.T@(b*weights[:,None]),selected))
    with np.load(model,allow_pickle=False) as d:state={k:d[k].copy() for k in d.files}
    reports=[]
    for ridge in ridges:
        penalty=np.eye(h.shape[1])*ridge;penalty[-1,-1]=ridge*.01
        candidate={k:v.copy() for k,v in state.items()}
        candidate.update(progress_supervision=np.array(supervised),motor_phase_feedback=np.array(feedback))
        if phase_heads and p.motor_heads==1:
            candidate['decoder']=np.tile(candidate['decoder'],(1,heads))
            candidate['bias']=np.tile(candidate['bias'],heads)
            candidate['motor_heads']=np.array(heads)
        predictions=np.zeros((val.sum(),3))
        for head,(covariance,cross,selected) in enumerate(systems):
            beta=np.linalg.solve(covariance+penalty,cross)
            candidate['decoder'][:,head*4:head*4+3]=beta[:-1];candidate['bias'][head*4:head*4+3]=beta[-1]
            rows=phases[val]==head if heads>1 else np.ones(val.sum(),dtype=bool)
            predictions[rows]=np.tanh(h[val][rows]@beta)
            if phase_heads:
                # Empirical gripper label for this learned phase, not a live
                # teacher. Phase selection still comes through neural activity.
                candidate['decoder'][:,head*4+3]=0
                candidate['bias'][head*4+3]=np.arctanh(np.clip(data['actions'][selected,3].mean(),-.999,.999))
            if planar_heights:
                height=float(np.median(data['actions'][selected,2]))
                candidate['decoder'][:,head*4+2]=0
                candidate['bias'][head*4+2]=np.arctanh(np.clip(height,-.999,.999))
                predictions[rows,2]=height
        output=model.parent/f'{"phase-" if phase_heads else ""}readout-{ridge:g}.npz';np.savez_compressed(output,**candidate)
        error=predictions-data['actions'][val,:3]
        reports.append(dict(path=str(output),ridge=ridge,validation_xyz_mse=float(np.square(error).mean()),
            checkpoint_sha256=hashlib.sha256(output.read_bytes()).hexdigest()))
    report=dict(method='per-phase ridge XYZ and empirical gripper labels; neural core and phase classifier frozen' if phase_heads else 'phase-balanced ridge XYZ readout fit; core, memory and gripper frozen',
        motor_heads=heads,validation_xyz_uses_teacher_phase=heads>1,
        motor_phase_feedback=feedback,progress_supervision=supervised,planar_heights_from_training_medians=planar_heights,
        model_sha256=hashlib.sha256(model.read_bytes()).hexdigest(),dataset_sha256=hashlib.sha256(Path(dataset).read_bytes()).hexdigest(),
        train_episodes=np.unique(ids[train]).tolist(),validation_episodes=np.unique(ids[val]).tolist(),candidates=reports)
    (model.parent/'readout-fit.json').write_text(json.dumps(report,indent=2))
    return reports

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('model');p.add_argument('--dataset',required=True);p.add_argument('--phase-heads',action='store_true')
    p.add_argument('--supervised-skills',action='store_true',help='Eight learned phase heads, motor context pass, progress checks and data-fitted flat-table heights')
    a=p.parse_args();print(json.dumps(fit(a.model,a.dataset,phase_heads=a.phase_heads or a.supervised_skills,
        motor_phase_feedback=a.supervised_skills,progress_supervision=a.supervised_skills,planar_heights=a.supervised_skills)))
