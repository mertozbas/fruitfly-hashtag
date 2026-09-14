"""Plain MLP reference on identical observations and demonstration episodes.

This model is an evaluation control, never presented as the MaleCNS brain.
"""
import argparse
from pathlib import Path
import numpy as np
from .policy import OBS_SIZE,MEMORY_SIZE,PHASES,task_feature_mask


class MLP:
    def __init__(self,path):
        with np.load(path,allow_pickle=False) as data:
            self.parameters={k:data[k].copy() for k in data.files}
        self.has_memory='memory_weight' in self.parameters
        self.action_mode=str(self.parameters.get('action_mode','delta'))
        self.reset()

    def reset(self):self.memory=np.eye(MEMORY_SIZE,dtype=np.float32)[0]

    def __call__(self,x):
        p=self.parameters;x=np.asarray(x)
        if self.has_memory and x.shape==(OBS_SIZE,):x=np.r_[x,self.memory]
        x=np.clip((x-p['mean'])/p['scale'],-6,6)*p.get('input_mask',1)
        for i in range(2):x=np.tanh(x@p[f'w{i}']+p[f'b{i}'])
        if self.has_memory:self.memory=np.eye(MEMORY_SIZE,dtype=np.float32)[np.argmax(x@p['memory_weight']+p['memory_bias'])]
        return np.tanh(x@p['w2']+p['b2']).astype(np.float32)


def train(dataset,output,steps=8000,seed=42,stage='place',memory=False,task_features=False):
    import torch
    from torch import nn
    torch.set_num_threads(2);torch.manual_seed(seed)
    data=np.load(dataset,allow_pickle=False);rng=np.random.default_rng(seed)
    allowed={'reach':['approach','lower'],'lift':['approach','lower','close','lift'],'place':np.unique(data['phases'])}[stage]
    selected=np.isin(data['phases'],allowed);mask=selected&(data['episode_ids']%5!=0);val=selected&(data['episode_ids']%5==0)
    observations=data['observations'].astype(np.float32)
    targets=np.asarray([PHASES.index(p) for p in data['phases']])
    if memory:
        previous=np.r_[0,targets[:-1]];ids=data['episode_ids'];previous[np.r_[True,ids[1:]!=ids[:-1]]]=0
        observations=np.c_[observations,data['memory'] if 'memory' in data else np.eye(MEMORY_SIZE,dtype=np.float32)[previous]]
    mean=observations[mask].mean(0);scale=np.maximum(observations[mask].std(0),.08)
    if memory:mean[OBS_SIZE:]=0;scale[OBS_SIZE:]=1
    input_mask=task_feature_mask(len(mean)) if task_features else np.ones(len(mean),np.float32)
    x=torch.from_numpy((np.clip((observations-mean)/scale,-6,6)*input_mask).astype(np.float32));y=torch.from_numpy(data['actions'].astype(np.float32))
    model=nn.Sequential(nn.Linear(len(mean),128),nn.Tanh(),nn.Linear(128,128),nn.Tanh(),nn.Linear(128,4))
    memory_head=nn.Linear(128,MEMORY_SIZE)
    tp=torch.as_tensor(targets,dtype=torch.long)
    optimizer=torch.optim.Adam([*model.parameters(),*memory_head.parameters()] if memory else model.parameters(),lr=.001)
    schedule=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,steps,eta_min=.00005)
    groups=[np.flatnonzero(mask&(data['phases']==p)) for p in allowed]
    best=float('inf');history=[]
    for step in range(1,steps+1):
        ids=[rng.choice(groups[g]) for g in rng.integers(len(groups),size=128)]
        h=model[:4](x[ids]);logits=model[4](h);predicted=torch.tanh(logits)
        loss=(predicted[:,:3]-y[ids,:3]).square().mean()+.2*nn.functional.binary_cross_entropy_with_logits(2*logits[:,3],(y[ids,3]+1)/2)
        if memory:loss=loss+.2*nn.functional.cross_entropy(memory_head(h),tp[ids])
        optimizer.zero_grad(set_to_none=True);loss.backward();optimizer.step();schedule.step()
        if step%100==0:
            with torch.no_grad():score=float((torch.tanh(model(x[val]))-y[val]).square().mean())
            history.append([step,score])
            if score<best:
                best=score;params=dict(mean=mean,scale=scale,input_mask=input_mask,action_mode=str(data['action_mode']) if 'action_mode' in data else 'delta')
                if memory:params.update(memory_weight=memory_head.weight.detach().numpy().T.copy(),memory_bias=memory_head.bias.detach().numpy().copy())
                for i,layer in enumerate((model[0],model[2],model[4])):
                    params[f'w{i}']=layer.weight.detach().numpy().T.copy();params[f'b{i}']=layer.bias.detach().numpy().copy()
                np.savez_compressed(output,**params)
    import json
    Path(output).with_suffix('.json').write_text(json.dumps(dict(method='MLP reference',stage=stage,seed=seed,steps=steps,learned_memory=memory,task_features=task_features,dataset=str(dataset),best_validation_mse=best,history=history),indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',required=True);p.add_argument('--output',required=True);p.add_argument('--steps',type=int,default=8000);p.add_argument('--stage',choices=['reach','lift','place'],default='place')
    p.add_argument('--memory',action='store_true');p.add_argument('--task-features',action='store_true')
    a=p.parse_args();train(a.dataset,a.output,a.steps,stage=a.stage,memory=a.memory,task_features=a.task_features)
