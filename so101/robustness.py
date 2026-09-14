"""Explicit disturbance experiments; never part of the live controller."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from .policy import Policy
from .task import PickPlaceEnv


def evaluate(model,output,episodes=12,start_seed=4200,disturbance='pregrasp_push'):
    if disturbance not in {'pregrasp_push','forced_release'}:raise ValueError('Unknown disturbance')
    policy=Policy(model);env=PickPlaceEnv();records=[]
    try:
        for i in range(episodes):
            obs=env.reset(start_seed+i);policy.reset();triggered=False;remaining=0
            for step in range(600):
                action=policy(obs)
                if not triggered and ((disturbance=='pregrasp_push' and step==8) or (disturbance=='forced_release' and env.lifted)):
                    triggered=True;remaining=1 if disturbance=='pregrasp_push' else 12
                if remaining:
                    if disturbance=='pregrasp_push':env.data.xfrc_applied[env.cube_id,0]=.15*(1 if i%2 else -1)
                    else:action[3]=1. # Explicit adversarial gripper intervention.
                    remaining-=1
                obs,_,done,record=env.step(action,action_mode=policy.action_mode)
                env.data.xfrc_applied[:]=0
                if done:break
            record['disturbance_triggered']=triggered;records.append(record)
            print(i,record['success'],record['unsafe'],flush=True)
        report=dict(disturbance=disturbance,episodes=episodes,success_count=sum(r['success'] and r['disturbance_triggered'] for r in records),
            unsafe_count=sum(r['unsafe'] for r in records),triggered=sum(r['disturbance_triggered'] for r in records),
            checkpoint_sha256=hashlib.sha256(Path(model).read_bytes()).hexdigest(),
            intervention='150 mN horizontal cube push for 50 ms before grasp' if disturbance=='pregrasp_push' else 'Force gripper open for 600 ms after lift, then restore neural commands',results=records)
        Path(output).write_text(json.dumps(report,indent=2));return report
    finally:env.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('model');p.add_argument('--output',required=True);p.add_argument('--disturbance',choices=['pregrasp_push','forced_release'],default='pregrasp_push')
    a=p.parse_args();evaluate(a.model,a.output,disturbance=a.disturbance)
