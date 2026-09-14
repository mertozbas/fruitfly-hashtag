"""Seed-paired evaluation with the actual robot policy and contact physics."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from .policy import Policy
from .task import PickPlaceEnv


def evaluate(path,episodes=12,start_seed=4000,stage="place",variant="trained",output=None,event=None,sensor="state"):
    if variant=='mlp':
        from .reference import MLP
        policy=MLP(path)
    else:policy=Policy(path)
    env=PickPlaceEnv()
    camera=None
    if sensor=='camera':
        from .perception import CameraObservation
        camera=CameraObservation(env)
    records=[]
    try:
        for i in range(episodes):
            obs=env.reset(start_seed+i)
            if hasattr(policy,'reset'):policy.reset()
            transitions=[];last_phase=None
            if camera:camera.reset()
            for step in range(600):
                if camera:
                    try:obs=camera.observation()
                    except RuntimeError as exc:
                        record=env.metrics();record.update(outcome='sensor_stale',sensor_error=str(exc));passed=False;break
                action=policy(obs) if variant!="silenced" else policy.activity(obs,advance=True,silenced=True)[0]
                if getattr(policy,'has_memory',False):
                    from .policy import PHASES
                    current=PHASES[int(np.argmax(policy.memory))]
                    if current!=last_phase:transitions.append(dict(step=step,phase=current));last_phase=current
                obs,reward,done,record=env.step(action,action_mode=policy.action_mode)
                passed=record["reached"] if stage=="reach" else record["lifted"] if stage=="lift" else record["success"]
                if passed or done:
                    break
            record["stage_success"]=bool(passed and not record["unsafe"])
            if transitions:record['learned_phase_transitions']=transitions
            records.append(record)
            if event:
                event(status="evaluating",evaluated=i+1,evaluation_total=episodes,variant=variant,success_count=sum(r["stage_success"] for r in records))
            else:
                print(json.dumps(dict(episode=i,variant=variant,stage=stage,**record)),flush=True)
        summary=dict(stage=stage,variant=variant,sensor=sensor,episodes=episodes,success_count=sum(r["stage_success"] for r in records),
            action_mode=policy.action_mode,
            ablation='All four neural activity layers clamped to zero; learned decoder and memory biases, IK and servos retained' if variant=='silenced' else None,
            unsafe_count=sum(r["unsafe"] for r in records),falls=sum(r["lifted"] and not r["inside_bin"] and r["cube"][2]<.025 for r in records),
            reached=sum(r["reached"] for r in records),grasped=sum(r["grasped"] for r in records),lifted=sum(r["lifted"] for r in records),
            released=sum(r["released"] for r in records),mean_reward=float(np.mean([r["reward"] for r in records])),
            checkpoint_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            criterion={"reach":"TCP within 4 mm horizontally and below 24 mm, OR maintained bilateral grasp for 0.2 s; original geometric_reached reported separately; no unsafe contact or physics warning", "lift":"Cube above 70 mm with bilateral finger contact; no unsafe contact or physics warning", "place":"Cube completely inside 71.2 mm cavity, released, at rest, TCP >65 mm away for 0.5 s; no unsafe contact or physics warning"}[stage],
            results=records)
        if output:
            Path(output).write_text(json.dumps(summary,indent=2))
        return summary
    finally:
        if camera:camera.close()
        env.close()

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("model");p.add_argument("--episodes",type=int,default=12);p.add_argument("--start-seed",type=int,default=4000);p.add_argument("--stage",choices=["reach","lift","place"],default="place");p.add_argument("--variant",choices=["trained","silenced","mlp"],default="trained");p.add_argument("--output")
    p.add_argument('--sensor',choices=['state','camera'],default='state')
    a=p.parse_args();evaluate(a.model,a.episodes,a.start_seed,a.stage,a.variant,a.output,sensor=a.sensor)
