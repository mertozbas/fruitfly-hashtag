"""Collect contact-only demonstrations and retain failures for audit."""
import argparse
import json
from pathlib import Path
import numpy as np
from .task import PickPlaceEnv, Demonstrator, OBSERVATION_NAMES


def collect(output,episodes=100,start_seed=1000,action_noise=0.):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    observations,actions,phases,episode_ids=[],[],[],[]
    records=[]
    env=PickPlaceEnv()
    try:
        for episode in range(episodes):
            obs=env.reset(start_seed+episode)
            rng=np.random.default_rng(start_seed+episode)
            teacher=Demonstrator()
            ox,ay,ps=[],[],[]
            for step in range(600):
                action=teacher(env)
                ox.append(obs)
                ay.append(action)
                ps.append(teacher.phase)
                applied=action.copy()
                applied[:3]=np.clip(applied[:3]+rng.normal(0,action_noise,3),-1,1)
                obs,_,done,record=env.step(applied)
                if done:
                    break
            records.append(record)
            if record["success"]:
                observations.extend(ox); actions.extend(ay); phases.extend(ps)
                episode_ids.extend([start_seed+episode]*len(ox))
            print(json.dumps(dict(episode=episode,**record)),flush=True)
        if observations:
            np.savez_compressed(output/"demonstrations.npz",observations=np.asarray(observations),actions=np.asarray(actions),phases=phases,episode_ids=episode_ids)
        summary=dict(episodes=episodes,success_count=sum(r["success"] for r in records),
                     unsafe_count=sum(r["unsafe"] for r in records),observations=OBSERVATION_NAMES,
                     action_noise_std=action_noise,
                     source="feedback teacher; contacts and friction only; no object pose writes after reset",results=records)
        (output/"demonstrations.json").write_text(json.dumps(summary,indent=2))
        return summary
    finally:
        env.close()

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--output",default="artifacts/so101/demonstrations");p.add_argument("--episodes",type=int,default=100);p.add_argument("--start-seed",type=int,default=1000)
    p.add_argument('--action-noise',type=float,default=0.)
    a=p.parse_args();collect(a.output,a.episodes,a.start_seed,a.action_noise)
