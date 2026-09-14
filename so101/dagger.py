"""Corrective demonstrations on learner-visited states, with explicit interventions."""
import argparse
import json
from pathlib import Path
import numpy as np
from .task import PickPlaceEnv,Demonstrator
from .policy import Policy,PHASES,MEMORY_SIZE,TARGET_CENTER,TARGET_SCALE


def collect(model,source,output,episodes=20,start_seed=3000,stage="reach",beta=.35):
    original=np.load(source,allow_pickle=False)
    values={k:[original[k]] for k in ("observations","actions","phases","episode_ids")}
    policy=Policy(model);env=PickPlaceEnv();records=[]
    if policy.has_memory:
        targets=np.array([PHASES.index(p) for p in original['phases']])
        previous=np.r_[0,targets[:-1]];ids=original['episode_ids']
        previous[np.r_[True,ids[1:]!=ids[:-1]]]=0
        values['memory']=[original['memory'] if 'memory' in original else np.eye(MEMORY_SIZE,dtype=np.float32)[previous]]
    allowed={"reach":{"approach","lower"},"lift":{"approach","lower","close","lift"},"place":None}[stage]
    try:
        for i in range(episodes):
            seed=start_seed+i;rng=np.random.default_rng(seed);obs=env.reset(seed);teacher=Demonstrator()
            policy.reset()
            x,y,phases,memories=[],[],[],[];interventions=0
            for _ in range(600):
                expert=teacher(env)
                if policy.action_mode=='target':expert=np.r_[(teacher.target-TARGET_CENTER)/TARGET_SCALE,expert[3]].astype(np.float32)
                if allowed is not None and teacher.phase not in allowed:break
                holding,inside,_=env.sensors()
                # The teacher has no recovery controller. Do not label a
                # dropped-object state with the obsolete transport waypoint.
                if env.lifted and not holding and env.cube[2]<.025 and not inside:
                    break
                if policy.has_memory:memories.append(policy.memory.copy())
                predicted=policy(obs)
                x.append(obs);y.append(expert);phases.append(teacher.phase)
                intervene=bool(rng.random()<beta)
                action=expert if intervene else predicted
                interventions+=int(intervene)
                obs,_,done,record=env.step(action,action_mode=policy.action_mode)
                if done:break
            if x:
                for key,items in dict(observations=np.array(x),actions=np.array(y),phases=np.array(phases),episode_ids=np.full(len(x),seed)).items():
                    values[key].append(items)
                if policy.has_memory:values['memory'].append(np.asarray(memories))
            records.append(dict(seed=seed,samples=len(x),interventions=interventions,**{k:v for k,v in env.metrics().items() if k!="seed"}))
            print(json.dumps(records[-1]),flush=True)
        np.savez_compressed(output,action_mode=policy.action_mode,**{k:np.concatenate(v) for k,v in values.items()})
        Path(output).with_suffix('.json').write_text(json.dumps(dict(stage=stage,beta=beta,source=str(source),policy=str(model),results=records),indent=2))
    finally:env.close()

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--source',required=True);p.add_argument('--output',required=True);p.add_argument('--episodes',type=int,default=20);p.add_argument('--start-seed',type=int,default=3000);p.add_argument('--stage',choices=['reach','lift','place'],default='reach');p.add_argument('--beta',type=float,default=.35)
    a=p.parse_args();collect(a.model,a.source,a.output,a.episodes,a.start_seed,a.stage,a.beta)
