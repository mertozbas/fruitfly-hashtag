"""Seed-paired evaluation with the actual robot policy and contact physics."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from .policy import Policy
from .task import PickPlaceEnv


def evaluate(path,episodes=12,start_seed=4000,stage="place",variant="trained",output=None,event=None,sensor="state",max_attempts=1,disturbance=None,camera_name='wrist'):
    if disturbance not in {None,'forced_release','pregrasp_push'}:raise ValueError('Unknown disturbance')
    from .recovery import RetrySupervisor
    recovery=RetrySupervisor(max_attempts)
    if variant=='mlp':
        from .reference import MLP
        policy=MLP(path)
    else:policy=Policy(path)
    env=PickPlaceEnv()
    if max_attempts>1:env.step_limit=1200
    camera=None
    if sensor=='camera':
        from .perception import CameraObservation
        camera=CameraObservation(env,camera=camera_name)
    records=[]
    try:
        for i in range(episodes):
            obs=env.reset(start_seed+i)
            if hasattr(policy,'reset'):policy.reset()
            transitions=[];last_phase=None
            recovery.reset();triggered=False;remaining=0;max_error=0.;visible_frames=0;frames=0
            if camera:camera.reset()
            for step in range(env.step_limit):
                if camera:
                    try:obs=camera.observation()
                    except RuntimeError as exc:
                        record=env.metrics();record.update(outcome='sensor_stale',sensor_error=str(exc));passed=False;break
                    max_error=max(max_error,float(np.linalg.norm(np.asarray(camera.last['estimated_cube'])-env.cube)))
                    visible_frames+=int(camera.last['visible']);frames+=1
                if max_attempts>1:
                    recovery.observe(obs,float(env.data.time),policy,camera)
                    if recovery.exhausted:
                        record=env.metrics();record.update(outcome='retry_exhausted');passed=False;break
                action=policy(obs) if variant!="silenced" else policy.activity(obs,advance=True,silenced=True)[0]
                if getattr(policy,'has_memory',False):
                    from .policy import PHASES
                    current=PHASES[int(np.argmax(policy.memory))]
                    if current!=last_phase:transitions.append(dict(step=step,phase=current));last_phase=current
                if not triggered and ((disturbance=='forced_release' and env.lifted) or (disturbance=='pregrasp_push' and step==8)):
                    triggered=True;remaining=12 if disturbance=='forced_release' else 1
                if remaining:
                    if disturbance=='forced_release':action[3]=1.
                    else:env.data.xfrc_applied[env.cube_id,0]=.15*(1 if i%2 else -1)
                    remaining-=1
                obs,reward,done,record=env.step(action,action_mode=policy.action_mode)
                env.data.xfrc_applied[:]=0
                passed=record["reached"] if stage=="reach" else record["lifted"] if stage=="lift" else record["success"]
                if passed or done:
                    break
            record["stage_success"]=bool(passed and not record["unsafe"])
            record.update(recovery=recovery.status(),disturbance_triggered=triggered)
            if camera:record.update(vision_frames=frames,visible_frames=visible_frames,max_estimation_error_mm=max_error*1000)
            if transitions:record['learned_phase_transitions']=transitions
            records.append(record)
            if event:
                event(status="evaluating",evaluated=i+1,evaluation_total=episodes,variant=variant,success_count=sum(r["stage_success"] for r in records))
            else:
                print(json.dumps(dict(episode=i,variant=variant,stage=stage,**record)),flush=True)
        summary=dict(stage=stage,variant=variant,sensor=sensor,camera_name=camera_name if camera else None,episodes=episodes,success_count=sum(r["stage_success"] for r in records),
            max_attempts=max_attempts,disturbance=disturbance,disturbance_triggered_count=sum(r['disturbance_triggered'] for r in records),
            recovered_successes=sum(r['stage_success'] and r['recovery']['retries']>0 for r in records),
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
    p.add_argument('--max-attempts',type=int,default=1);p.add_argument('--disturbance',choices=['forced_release','pregrasp_push'])
    p.add_argument('--camera',choices=['wrist','front'],default='wrist')
    a=p.parse_args();evaluate(a.model,a.episodes,a.start_seed,a.stage,a.variant,a.output,sensor=a.sensor,max_attempts=a.max_attempts,disturbance=a.disturbance,camera_name=a.camera)
