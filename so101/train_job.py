"""UI training job: finite curriculum, explicit gates and preserved candidates."""
import argparse
import json
from pathlib import Path
import shutil
import hashlib
import os
from datetime import datetime,timezone
from .policy import prepare
from .train import train,event
from .demonstrations import collect as demonstrations
from .dagger import collect as corrections
from .evaluate import evaluate
from .audit import manifest
from .fit_readout import fit as fit_readout
from .target_demonstrations import convert
from .reinforce import refine as reward_refine


def refinement(directory,dataset,steps,seed,initial):
    """Refine a copy; retain the prior controller unless paired tests improve."""
    baseline=directory/'untrained.npz';shutil.copy2(initial,baseline)
    development_seed=4000+(seed%10)*12
    for stage in ('reach','lift'):
        gate=evaluate(baseline,episodes=12,start_seed=development_seed,stage=stage,
            output=directory/f'baseline-{stage}.json',event=event)
        if gate['unsafe_count'] or gate['success_count']<11:
            raise RuntimeError(f'Existing model failed {stage} preflight; original model preserved')
    train(directory,dataset,steps=steps,seed=seed,stage='place',resume=baseline,
          learning_rate=.0001,position_loss_weight=1.)
    shutil.copy2(directory/'trained.npz',directory/'bc-candidate.npz')
    fit_readout(directory/'bc-candidate.npz',dataset,ridges=(1e-4,))
    paths=[baseline,directory/'bc-candidate.npz',directory/'place-last.npz',directory/'readout-0.0001.npz']
    scored=[]
    for index,path in enumerate(paths):
        result=evaluate(path,episodes=12,start_seed=development_seed,output=directory/f'candidate-{index}.json',event=event)
        scored.append((result,path))
    # Preserve the baseline on ties; reward alone must not replace a controller.
    best,path=max(scored,key=lambda item:(-item[0]['unsafe_count'],item[0]['success_count']))
    shutil.copy2(path,directory/'reward-start.npz')
    reward_candidate=reward_refine(directory/'reward-start.npz',dataset,iterations=3,episodes=4,seed=seed)
    result=evaluate(reward_candidate,episodes=12,start_seed=development_seed,output=directory/'reward-gate.json',event=event)
    if (-result['unsafe_count'],result['success_count'])>(-best['unsafe_count'],best['success_count']):
        best,path=result,reward_candidate
    shutil.copy2(path,directory/'trained.npz')
    test_seed=10000+seed*100
    evaluation=evaluate(directory/'trained.npz',episodes=100,start_seed=test_seed,event=event)
    evaluation['controls']={
        'untrained':evaluate(baseline,episodes=100,start_seed=test_seed,event=event),
        'silenced':evaluate(directory/'trained.npz',episodes=100,start_seed=test_seed,variant='silenced',event=event)}
    evaluation.update(acceptance_passed=evaluation['success_count']>=90 and evaluation['unsafe_count']==0,
        baseline_kind='previous trained model',selected_candidate=path.name,
        selected_model_changed=hashlib.sha256((directory/'trained.npz').read_bytes()).hexdigest()!=hashlib.sha256(baseline.read_bytes()).hexdigest())
    (directory/'evaluation.json').write_text(json.dumps(evaluation,indent=2))
    training=json.loads((directory/'training.json').read_text())
    training.update(selected_candidate=path.name,selected_model_changed=evaluation['selected_model_changed'],
        candidate_checkpoint_sha256=training['checkpoint_sha256'],checkpoint_sha256=evaluation['checkpoint_sha256'],method='BC + ridge readout + bounded PPO; paired physical candidate selection')
    (directory/'training.json').write_text(json.dumps(training,indent=2))
    event(status='evaluating',stage='complete',evaluated=100,evaluation_total=100,
        success_count=evaluation['success_count'],acceptance_passed=evaluation['acceptance_passed'],selected_model_changed=evaluation['selected_model_changed'])
    return evaluation


def run(output,steps=3000,seed=42,dataset=None,resume=None):
    directory=Path(output);directory.mkdir(parents=True,exist_ok=True)
    if not (directory/'circuit.json').exists():prepare(directory)
    manifest(directory/'assets-manifest.json')
    if dataset is None:
        default=Path(__file__).resolve().parents[1]/'artifacts/so101/target-demonstrations.npz'
        dataset=default if default.exists() else directory/'demonstrations/demonstrations.npz'
    dataset=Path(dataset)
    if not dataset.exists():
        event(status='training',stage='demonstrations',step=0,steps=steps)
        teacher=demonstrations(dataset.parent,episodes=160,start_seed=2200,action_noise=.3)
        if teacher['unsafe_count'] or teacher['success_count']<144:
            raise RuntimeError('Contact-physics teacher gate failed; inspect demonstrations.json')
    import numpy as np
    with np.load(dataset,allow_pickle=False) as data:mode=str(data['action_mode']) if 'action_mode' in data else 'delta'
    if mode!='target':
        target_dataset=directory/'target-demonstrations.npz';convert(dataset,target_dataset);dataset=target_dataset
    if resume:return refinement(directory,dataset,steps,seed,resume)
    gates=[];resume=None
    for stage_index,stage in enumerate(('reach','lift','place')):
        passed=False
        for round_index in range(4):
            if round_index:
                corrected=directory/f'corrections-{stage}-{round_index}.npz'
                event(status='training',stage=f'{stage}: corrective demonstrations',step=0,steps=steps)
                corrections(resume,dataset,corrected,episodes=20,
                    start_seed=3000+stage_index*200+round_index*30,stage=stage,beta=.2 if round_index==1 else 0.)
                dataset=corrected
            train(directory,dataset,steps=steps,seed=seed,stage=stage,resume=resume,
                  learning_rate=.001 if round_index==0 else .0003,memory=True,all_core=True,task_features=True,position_loss_weight=1.)
            resume=directory/'trained.npz'
            candidates=[resume,directory/f'{stage}-last.npz']
            if stage=='place':
                fit_readout(resume,dataset,ridges=(1e-4,));candidates.append(directory/'readout-0.0001.npz')
            scored=[]
            for index,path in enumerate(candidates):
                report=evaluate(path,episodes=12,start_seed=4000,stage=stage,
                    output=directory/f'gate-{stage}-{round_index}-{index}.json',event=event)
                scored.append((report,path))
            report,path=max(scored,key=lambda item:(-item[0]['unsafe_count'],item[0]['success_count'],item[0]['mean_reward']))
            if path!=resume:shutil.copy2(path,resume)
            gates.append(dict(stage=stage,round=round_index,success_count=report['success_count'],
                episodes=12,unsafe_count=report['unsafe_count'],checkpoint_sha256=report['checkpoint_sha256']))
            (directory/'curriculum.json').write_text(json.dumps(gates,indent=2))
            if report['success_count']>=11 and report['unsafe_count']==0:
                passed=True;break
        if not passed:
            raise RuntimeError(f'{stage} gate not reached after four bounded attempts; candidate and logs retained')
    # A completed training process and a held-out acceptance result are distinct.
    evaluation=evaluate(resume,episodes=100,start_seed=8000,event=event)
    evaluation['controls']={}
    for variant,path in [('untrained',directory/'untrained.npz'),('silenced',resume)]:
        evaluation['controls'][variant]=evaluate(path,episodes=100,start_seed=8000,
            variant='silenced' if variant=='silenced' else 'trained',event=event)
    evaluation['acceptance_passed']=evaluation['success_count']>=90 and evaluation['unsafe_count']==0
    (directory/'evaluation.json').write_text(json.dumps(evaluation,indent=2))
    event(status='evaluating',stage='complete',evaluated=100,evaluation_total=100,
        success_count=evaluation['success_count'],acceptance_passed=evaluation['acceptance_passed'])
    return evaluation

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--steps',type=int,default=3000)
    p.add_argument('--seed',type=int,default=42);p.add_argument('--dataset');p.add_argument('--resume');a=p.parse_args()
    if not 200<=a.steps<=10000:p.error('steps must be 200..10000 per stage')
    directory=Path(a.output);directory.mkdir(parents=True,exist_ok=True)
    owns_metadata=not (directory/'run.json').exists()
    meta=dict(id=directory.name,status='training',created=datetime.now(timezone.utc).isoformat(),task='so101',steps=a.steps,seed=a.seed,owner_pid=os.getpid())
    if owns_metadata:(directory/'run.json').write_text(json.dumps(meta,indent=2))
    try:
        result=run(a.output,a.steps,a.seed,a.dataset,a.resume)
        meta.update(status='complete',acceptance_passed=result['acceptance_passed'])
    except BaseException:
        meta['status']='failed'
        raise
    finally:
        if owns_metadata:(directory/'run.json').write_text(json.dumps(meta,indent=2))
