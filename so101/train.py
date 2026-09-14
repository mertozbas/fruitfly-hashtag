"""Bounded supervised curriculum for the connectome robot actor."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import torch
from .policy import prepare,torch_model,Policy,OBS_SIZE,PHASES,MEMORY_SIZE
from odor_policy import Circuit


def event(**values):
    print("LAB_EVENT "+json.dumps(values),flush=True)


def train(directory,dataset,steps=3000,seed=42,stage="place",resume=None,frozen_core=False,learning_rate=.001,memory=False,skill_heads=False,transition_fraction=0.,all_core=False,task_features=False,position_loss_weight=None):
    directory=Path(directory)
    c=Circuit(directory) if (directory/"circuit.json").exists() else prepare(directory)
    data=np.load(dataset,allow_pickle=False)
    action_mode=str(data['action_mode']) if 'action_mode' in data else 'delta'
    if action_mode=='target':task_features=True
    if position_loss_weight is None:position_loss_weight=10. if action_mode=='target' else 1.
    if not 0<position_loss_weight<=100:raise ValueError('Position loss weight must be positive and at most 100')
    phases=data["phases"]
    allowed={"reach":{"approach","lower"},"lift":{"approach","lower","close","lift"},"place":set(phases)}[stage]
    selected=np.isin(phases,list(allowed))
    ids=data["episode_ids"]
    # Entire episodes are held out, not neighbouring frames from one trajectory.
    train_mask=selected & (ids%5!=0)
    val_mask=selected & (ids%5==0)
    x,y=data["observations"].astype(np.float32),data["actions"].astype(np.float32)
    if resume:
        previous_policy=Policy(resume);memory=previous_policy.has_memory;skill_heads=previous_policy.motor_heads>1;all_core=all_core or previous_policy.all_core
        if previous_policy.action_mode!=action_mode:raise ValueError('Resume and demonstration action modes differ')
    if skill_heads:memory=True
    if x.shape[1]!=OBS_SIZE or not val_mask.any() or not train_mask.any():
        raise ValueError("Missing episode-disjoint training/validation data")
    phase_targets=np.asarray([PHASES.index(p) for p in phases])
    if memory:
        previous=np.r_[0,phase_targets[:-1]]
        previous[np.r_[True,ids[1:]!=ids[:-1]]]=0
        feedback=data['memory'] if 'memory' in data else np.eye(MEMORY_SIZE,dtype=np.float32)[previous]
        x=np.concatenate([x,feedback],axis=1)
    mean=x[train_mask].mean(0)
    scale=np.maximum(x[train_mask].std(0),.08)
    if memory:mean[OBS_SIZE:]=0;scale[OBS_SIZE:]=1
    torch.set_num_threads(2)
    device=torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    actor=torch_model(c,mean,scale,seed,frozen_core,motor_heads=MEMORY_SIZE if skill_heads else 1,all_core=all_core,task_features=task_features,action_mode=action_mode).to(device)
    if resume:
        actor.restore(resume)
        # New stages activate previously constant sensors (contact duration,
        # lift state, gripper position). Keeping reach-only scales would clip
        # distinct grasp states to the same input. Reparameterize the encoder
        # so its un-clipped affine function is preserved under the new scales.
        with torch.no_grad():
            new_mean=torch.as_tensor(mean,device=device)
            new_scale=torch.as_tensor(scale,device=device)
            old_weight=actor.encoder.weight.clone()
            actor.encoder.bias.add_(old_weight@((new_mean-actor.input_mean)/actor.input_scale*actor.input_mask))
            actor.encoder.weight.mul_(new_scale/actor.input_scale)
            actor.input_mean.copy_(new_mean);actor.input_scale.copy_(new_scale)
    else:
        actor.save(directory/"untrained.npz")
    tx,ty=torch.from_numpy(x).to(device),torch.from_numpy(y).to(device)
    tp=torch.as_tensor(phase_targets,dtype=torch.long,device=device)
    val_indices=np.flatnonzero(val_mask)[::max(1,int(val_mask.sum()/2048))]
    vx,vy=tx[val_indices],ty[val_indices]
    rng=np.random.default_rng(seed)
    phase_indices=[np.flatnonzero(train_mask & (phases==p)) for p in sorted(allowed)]
    changed=np.r_[False,(phase_targets[1:]!=phase_targets[:-1]) & (ids[1:]==ids[:-1])]
    transitions=[np.flatnonzero(train_mask & (phases==p) & changed) for p in sorted(allowed)]
    corrections=[np.flatnonzero(train_mask & (phases==p) & (ids>=3000) & (ids<4000)) for p in sorted(allowed)]
    optimizer=torch.optim.Adam(actor.parameters(),lr=learning_rate)
    schedule=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=steps,eta_min=learning_rate*.05)
    def score():
        with torch.no_grad():
            return float(torch.mean((actor(vx)-vy)**2).item())
    before=score();history=[];best=float("inf");started=time.time()
    event(status="training",step=0,steps=steps,stage=stage,loss=before)
    for step in range(1,steps+1):
        indices=[]
        for phase_index in rng.integers(len(phase_indices),size=128):
            group=phase_indices[phase_index]
            if len(corrections[phase_index]) and rng.random()<.5:
                group=corrections[phase_index]
            if len(transitions[phase_index]) and rng.random()<transition_fraction:
                group=transitions[phase_index]
            indices.append(rng.choice(group))
        logits,layers,_=actor(tx[indices],details=True,phase=tp[indices] if skill_heads else None)
        predicted=torch.tanh(logits)
        loss=position_loss_weight*(predicted[:,:3]-ty[indices,:3]).square().mean()
        loss=loss+.2*torch.nn.functional.binary_cross_entropy_with_logits(2*logits[:,3],(ty[indices,3]+1)/2)
        loss=loss+1e-5*actor.raw_gain.square().mean()
        if memory:loss=loss+.2*torch.nn.functional.cross_entropy(actor.memory_decoder(layers[-1]),tp[indices])
        optimizer.zero_grad(set_to_none=True);loss.backward()
        torch.nn.utils.clip_grad_norm_(actor.parameters(),1.)
        optimizer.step()
        schedule.step()
        if step%100==0 or step==steps:
            validation=score()
            history.append(dict(step=step,validation_mse=validation))
            if validation<best:
                best=validation;actor.save(directory/f"{stage}.npz")
            event(status="training",step=step,steps=steps,stage=stage,loss=validation,
                  history=[[r["step"],r["validation_mse"]] for r in history])
        if step%1000==0:
            actor.save(directory/f'{stage}-step{step}.npz')
    actor.save(directory/f"{stage}-last.npz")
    actor.restore(directory/f"{stage}.npz")
    actor.save(directory/"trained.npz")
    saved=Policy(directory/"trained.npz")
    base=c.layers[2].toarray();mask=base!=0
    report=dict(task="so101",stage=stage,method="behavior_cloning",seed=seed,steps=steps,
        before_mse=before,after_mse=best,history=history,elapsed_seconds=time.time()-started,
        changed_existing_synaptic_gains=int(np.count_nonzero(np.abs(saved.weight[mask]/base[mask]-1)>.001)),
        frozen_core=frozen_core,all_core=all_core,learned_phase_memory=memory,learned_motor_heads=actor.motor_heads,transition_sampling_fraction=transition_fraction,train_episodes=sorted(set(ids[train_mask].tolist())),validation_episodes=sorted(set(ids[val_mask].tolist())),
        sensor_adapter="30 robot features; learned encoder",motor_adapter="continuous TCP deltas + gripper; fixed IK and bounded position servos",
        scope="Artificial supervised neural controller on MaleCNS anatomical topology. Physical success is evaluated separately from validation MSE.")
    report.update(dataset=str(dataset),dataset_sha256=hashlib.sha256(Path(dataset).read_bytes()).hexdigest(),
        action_mode=action_mode,
        position_loss_weight=position_loss_weight,
        checkpoint_sha256=hashlib.sha256((directory/'trained.npz').read_bytes()).hexdigest())
    report['changed_existing_synaptic_gains_by_layer']=[int(np.count_nonzero(np.abs(w.toarray()[b.toarray()!=0]/b.toarray()[b.toarray()!=0]-1)>.001)) for w,b in zip(saved.layers,c.layers)]
    report['changed_existing_synaptic_gains']=sum(report['changed_existing_synaptic_gains_by_layer'])
    if memory:
        with torch.no_grad():
            _,validation_layers,_=actor(vx,details=True)
            predicted_phase=actor.memory_decoder(validation_layers[-1]).argmax(-1)
            report['phase_accuracy']=float((predicted_phase==tp[val_indices]).float().mean().cpu())
    snapshots=directory/'training-history';snapshots.mkdir(exist_ok=True)
    import shutil
    for name in ('circuit.json','body_ids.npz','layer0.npz','layer1.npz','layer2.npz'):
        if not (snapshots/name).exists():shutil.copy2(directory/name,snapshots/name)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'-'+stage
    actor.save(snapshots/(stamp+'.npz'))
    (snapshots/(stamp+'.json')).write_text(json.dumps(report,indent=2))
    report['cumulative_steps']=sum(json.loads(p.read_text()).get('steps',0) for p in snapshots.glob('20*-*.json'))
    (directory/f"training-{stage}.json").write_text(json.dumps(report,indent=2))
    (directory/"training.json").write_text(json.dumps(report,indent=2))
    # Verify exported NumPy/SciPy activity and Torch training use the same path.
    with torch.no_grad():
        expected=actor(tx[val_indices[:8]]).cpu().numpy()
    actual=np.stack([saved(x[i]) for i in val_indices[:8]])
    if not np.allclose(expected,actual,atol=5e-4):
        raise AssertionError(f"Torch/NumPy mismatch: {np.max(np.abs(expected-actual))}")
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);p.add_argument("--dataset",default="artifacts/so101/demonstrations/demonstrations.npz");p.add_argument("--steps",type=int,default=3000);p.add_argument("--seed",type=int,default=42);p.add_argument("--stage",choices=["reach","lift","place"],default="place");p.add_argument("--resume");p.add_argument("--frozen-core",action="store_true")
    p.add_argument('--learning-rate',type=float,default=.001)
    p.add_argument('--memory',action='store_true')
    p.add_argument('--skill-heads',action='store_true')
    p.add_argument('--transition-fraction',type=float,default=0.)
    p.add_argument('--all-core',action='store_true')
    p.add_argument('--task-features',action='store_true')
    p.add_argument('--position-loss-weight',type=float)
    a=p.parse_args();train(a.output,a.dataset,a.steps,a.seed,a.stage,a.resume,a.frozen_core,a.learning_rate,a.memory,a.skill_heads,a.transition_fraction,a.all_core,a.task_features,a.position_loss_weight)
