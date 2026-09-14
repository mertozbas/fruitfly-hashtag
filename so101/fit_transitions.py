"""Learn a task-transition support graph from training demonstration labels.

This is an engineered, data-fitted task prior, separate from MaleCNS anatomy.
It contains no waypoints, joint commands, timings or hand-coded phase order.
The neural phase logits choose among transitions observed in training episodes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from .policy import Policy,PHASES,MEMORY_SIZE


def fit(model,dataset,output):
    policy=Policy(model)
    if not policy.has_memory:raise ValueError('A learned-memory checkpoint is required')
    data=np.load(dataset,allow_pickle=False);ids=data['episode_ids'];labels=data['phases']
    counts=np.zeros((MEMORY_SIZE,MEMORY_SIZE),np.float32);starts=np.zeros(MEMORY_SIZE,np.float32)
    episodes=[]
    for episode in np.unique(ids):
        if episode%5==0:continue # same episode-disjoint training split as BC
        sequence=[PHASES.index(p) for p in labels[ids==episode]]
        if not sequence:continue
        episodes.append(int(episode));starts[sequence[0]]+=1
        for before,after in zip([sequence[0],*sequence[:-1]],sequence):counts[before,after]+=1
    if not episodes:raise ValueError('No training demonstration episodes')
    with np.load(model,allow_pickle=False) as source:weights={k:source[k].copy() for k in source.files}
    weights.update(transition_counts=counts,start_counts=starts)
    np.savez_compressed(output,**weights)
    result=dict(method='empirical transition support from training demonstrations',source=str(dataset),
        dataset_sha256=hashlib.sha256(Path(dataset).read_bytes()).hexdigest(),train_episodes=episodes,
        phase_names=PHASES,counts=counts.tolist(),start_counts=starts.tolist(),
        neural_motor_weights_unchanged=True,scope='Artificial learned task prior, not an anatomical brain connection')
    Path(output).with_suffix('.transitions.json').write_text(json.dumps(result,indent=2))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('model');p.add_argument('--dataset',required=True);p.add_argument('--output',required=True);a=p.parse_args();fit(a.model,a.dataset,a.output)
