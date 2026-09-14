"""Collect measured RGB-D demonstrations, including recovery in the same scene.

The feedback teacher supplies labels only during collection. Deployment uses
Policy.activity and the explicitly reported bounded retry supervisor.
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from .task import PickPlaceEnv,Demonstrator
from .perception import CameraObservation
from .policy import Policy,PHASES,TARGET_CENTER,TARGET_SCALE
from .recovery import RetrySupervisor
from .camera_mount import PROFILE


def collect(output,episodes=24,start_seed=3500,learner=None,append_source=None,camera_name='wrist',wide=False):
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    profile=PROFILE if camera_name=='wrist' else 'front-v1'
    original=None
    if append_source:
        with np.load(append_source,allow_pickle=False) as d:
            source_camera=str(d['camera_name']) if 'camera_name' in d else 'front'
            if source_camera!=camera_name:raise ValueError('Cannot append demonstrations from a different camera mount')
            source_profile=str(d['camera_profile']) if 'camera_profile' in d else ('legacy-wrist' if source_camera=='wrist' else 'front-v1')
            if source_profile!=profile:raise ValueError('Cannot append demonstrations from a different camera calibration profile')
            original={k:d[k].copy() for k in ('observations','actions','phases','episode_ids','memory')}
        if np.intersect1d(original['episode_ids'],np.arange(start_seed,start_seed+episodes)).size:
            raise ValueError('Correction episode IDs overlap the source dataset')
    env=PickPlaceEnv();env.step_limit=1200
    camera=CameraObservation(env,camera=camera_name);records=[];rows=[]
    policy=Policy(learner) if learner else None
    try:
        for i in range(episodes):
            env.reset(start_seed+i)
            if wide:
                rng=np.random.default_rng(start_seed+i)
                for _ in range(100):
                    cube=np.array([rng.uniform(-.025,.11),rng.uniform(-.245,-.17),.015])
                    if np.any(np.abs(cube[:2]-env.goal[:2])>.058):break
                env.reset(start_seed+i,cube=cube,goal=env.goal-[0,0,.0174])
            camera.reset();teacher=Demonstrator();retry=RetrySupervisor(3)
            memory=0;triggered=False;remaining=0;frames=[]
            if policy:policy.reset()
            rollin=policy is not None
            def restart():
                nonlocal memory
                teacher.phase='approach';teacher.anchor=None;memory=0
                if policy:policy.reset()
            for step in range(env.step_limit):
                try:obs=camera.observation()
                except RuntimeError:
                    record=env.metrics();record['outcome']='sensor_stale';break
                retry.observe(obs,float(env.data.time),SimpleNamespace(reset=restart),camera)
                if retry.exhausted:
                    record=env.metrics();record['outcome']='retry_exhausted';break
                holding=bool(obs[22]);inside=bool(obs[24]);contacts=set(env.contacts())
                sensed=SimpleNamespace(cube=np.asarray(camera.last['estimated_cube']),ee=env.ee,goal=env.goal,
                    grasped=env.contact_dwell>=.2,lifted=bool(obs[23]),
                    released=bool(obs[23] and inside and 'bin' in contacts and not holding),
                    contact_dwell=env.contact_dwell,data=env.data,qadr=env.qadr,
                    sensors=lambda:(holding,inside,contacts))
                teacher(sensed)
                action=np.r_[np.clip((teacher.target-TARGET_CENTER)/TARGET_SCALE,-1,1),
                    1. if teacher.phase in {'approach','lower','release','retreat'} else -1.].astype(np.float32)
                feedback=policy.memory.copy() if rollin else np.eye(8,dtype=np.float32)[memory]
                frames.append((obs.copy(),action.copy(),teacher.phase,feedback))
                memory=PHASES.index(teacher.phase)
                if i%2 and not triggered and env.lifted:
                    triggered=True;remaining=12
                applied=policy(obs) if rollin else action.copy()
                if remaining:applied[3]=1.;remaining-=1
                _,_,done,record=env.step(applied,action_mode='target')
                if rollin and ((triggered and remaining==0) or step>=250):rollin=False
                if done:break
            record.update(disturbance_triggered=triggered,recovery=retry.status(),learner_rollin=learner,wide_workspace=wide)
            records.append(record)
            if record['success']:rows.extend((start_seed+i,*frame) for frame in frames)
            print(json.dumps(dict(episode=i,success=record['success'],outcome=record['outcome'],steps=record['steps'],retries=retry.status()['retries'])),flush=True)
            (output.with_suffix('.json')).write_text(json.dumps(dict(episodes=len(records),
                success_count=sum(r['success'] for r in records),unsafe_count=sum(r['unsafe'] for r in records),
                appended_source=str(append_source) if append_source else None,camera_name=camera_name,
                camera_profile=profile,
                source='RGB-D observations; feedback teacher labels; optional learner roll-in then teacher correction; forced release in alternate episodes; no object resets within a task',results=records),indent=2))
        if not rows:raise RuntimeError('No successful visual demonstrations')
        ids,obs,actions,phases,memory=zip(*rows)
        values=dict(observations=np.asarray(obs),actions=np.asarray(actions),phases=np.asarray(phases),
            memory=np.asarray(memory),episode_ids=np.asarray(ids))
        if original:values={k:np.concatenate([original[k],values[k]]) for k in values}
        np.savez_compressed(output,**values,action_mode='target',camera_name=camera_name,camera_profile=profile)
        return output
    finally:camera.close();env.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--episodes',type=int,default=24)
    p.add_argument('--start-seed',type=int,default=3400)
    p.add_argument('--learner')
    p.add_argument('--append-source')
    p.add_argument('--camera',choices=['wrist','front'],default='wrist')
    p.add_argument('--wide',action='store_true',help='Collect displaced cube starts throughout the reachable recovery workspace')
    a=p.parse_args();collect(a.output,a.episodes,a.start_seed,a.learner,a.append_source,a.camera,a.wide)
