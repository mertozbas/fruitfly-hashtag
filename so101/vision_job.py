"""Camera-specific refinement and independent visual/recovery acceptance gates."""
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np
from .train import train,event
from .fit_readout import fit
from .evaluate import evaluate


def refine(directory,dataset,steps,seed,initial,camera_name='wrist'):
    with np.load(dataset,allow_pickle=False) as data:
        source_camera=str(data['camera_name']) if 'camera_name' in data else 'front'
    if source_camera!=camera_name:raise ValueError('Training camera differs from the evaluation camera; collect matching demonstrations')
    directory=Path(directory);baseline=directory/'untrained.npz'
    shutil.copy2(initial,baseline)
    train(directory,dataset,steps=steps,seed=seed,resume=baseline,learning_rate=.0001,
          position_loss_weight=1.,transition_fraction=.25)
    candidate_report=json.loads((directory/'training.json').read_text())
    (directory/'candidate-training.json').write_text(json.dumps(candidate_report,indent=2))
    bc=directory/'bc-candidate.npz';shutil.copy2(directory/'trained.npz',bc)
    fit(bc,dataset,ridges=(1e-4,))
    scored=[];development_seed=5000+(seed%10)*20
    for index,path in enumerate((baseline,bc,directory/'readout-0.0001.npz')):
        normal=evaluate(path,episodes=8,start_seed=development_seed,sensor='camera',camera_name=camera_name,max_attempts=3,
            output=directory/f'visual-gate-{index}.json',event=event)
        recovery=evaluate(path,episodes=8,start_seed=development_seed,sensor='camera',camera_name=camera_name,max_attempts=3,
            disturbance='forced_release',output=directory/f'recovery-gate-{index}.json',event=event)
        scored.append((normal,recovery,path))
    # Keep the previous model on ties. Recovery must not hide a normal-task regression.
    reference=scored[0]
    eligible=[r for r in scored if r[0]['unsafe_count']+r[1]['unsafe_count']==0
              and r[0]['success_count']>=reference[0]['success_count']
              and r[1]['success_count']>=reference[1]['success_count']]
    selected=max(eligible,key=lambda r:r[0]['success_count']+r[1]['success_count']) if eligible else reference
    shutil.copy2(selected[2],directory/'trained.npz')
    start_seed=20000+seed*100
    normal=evaluate(directory/'trained.npz',episodes=40,start_seed=start_seed,sensor='camera',camera_name=camera_name,max_attempts=3,event=event)
    recovery=evaluate(directory/'trained.npz',episodes=24,start_seed=start_seed+40,sensor='camera',camera_name=camera_name,max_attempts=3,
        disturbance='forced_release',event=event)
    silenced=evaluate(directory/'trained.npz',episodes=8,start_seed=start_seed,sensor='camera',camera_name=camera_name,max_attempts=3,
        variant='silenced',event=event)
    normal.update(controls={'silenced':silenced,'untrained':reference[0]},recovery_evaluation=recovery,
        acceptance_passed=normal['success_count']>=36 and recovery['success_count']>=18
            and normal['unsafe_count']==0 and recovery['unsafe_count']==0,
        baseline_kind='previous trained model; development seeds, see visual-gate-0.json',
        selected_candidate=selected[2].name,
        selected_model_changed=hashlib.sha256((directory/'trained.npz').read_bytes()).digest()!=hashlib.sha256(baseline.read_bytes()).digest())
    (directory/'evaluation.json').write_text(json.dumps(normal,indent=2))
    if selected[2]==baseline:
        original_report=Path(initial).parent/'training.json'
        report=json.loads(original_report.read_text()) if original_report.exists() else {}
    else:report=candidate_report.copy()
    report.update(method=('Previous model retained after visual/recovery gates' if selected[2]==baseline else
        'Visual behavior cloning + ridge readout; camera and forced-release gates'),
        selected_candidate=selected[2].name,selected_model_changed=normal['selected_model_changed'],
        candidate_checkpoint_sha256=candidate_report['checkpoint_sha256'],checkpoint_sha256=normal['checkpoint_sha256'],
        attempted_training_report='candidate-training.json',
        sensor='camera',training_camera=source_camera,evaluation_camera=camera_name,
        recovery_scope='Up to 3 attempts in one unchanged scene; engineered retry supervisor resets learned memory')
    (directory/'training.json').write_text(json.dumps(report,indent=2))
    return normal
