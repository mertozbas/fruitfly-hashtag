"""Bounded PPO refinement from physical rewards, anchored to demonstrations.

The teacher is never called during reward rollouts. Candidate selection is a
separate paired physics evaluation; an RL update is not proof of improvement.
"""
import argparse
import json
from pathlib import Path
import time
import numpy as np
import torch
from .policy import Policy,torch_model,PHASES,MEMORY_SIZE
from .task import PickPlaceEnv
from .train import event


def refine(model,dataset,iterations=6,episodes=4,seed=42):
    model=Path(model);directory=model.parent
    initial=Policy(model)
    torch.set_num_threads(2)
    device=torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    actor=torch_model(initial.circuit,initial.input_mean,initial.input_scale,seed,motor_heads=initial.motor_heads,all_core=initial.all_core).to(device)
    actor.restore(model)
    with torch.no_grad():actor.log_std.fill_(-3.)
    actor.save(directory/'rl-before.npz')
    data=np.load(dataset,allow_pickle=False)
    train=(data['episode_ids']%5!=0)
    features=data['observations'].astype(np.float32)
    phases=np.array([PHASES.index(p) for p in data['phases']])
    if initial.has_memory:
        previous=np.r_[0,phases[:-1]];ids=data['episode_ids']
        previous[np.r_[True,ids[1:]!=ids[:-1]]]=0
        memory=data['memory'] if 'memory' in data else np.eye(MEMORY_SIZE,dtype=np.float32)[previous]
        features=np.concatenate([features,memory],axis=1)
    bx=torch.from_numpy(features[train]).to(device)
    by=torch.from_numpy(data['actions'][train].astype(np.float32)).to(device)
    bp=torch.as_tensor(phases[train],dtype=torch.long,device=device)
    optimizer=torch.optim.Adam(actor.parameters(),lr=1e-5)
    rng=np.random.default_rng(seed);env=PickPlaceEnv();history=[];start=time.time()
    candidate=directory/'rl-candidate.npz'
    try:
        for iteration in range(iterations):
            actor.save(candidate);portable=Policy(candidate)
            std=np.exp(actor.log_std.detach().cpu().numpy())
            observations=[];latents=[];old_probs=[];rewards=[];ends=[];records=[];memory_actions=[]
            for episode in range(episodes):
                obs=env.reset(6000+iteration*episodes+episode)
                portable.reset()
                for step in range(600):
                    augmented=portable.augmented(obs)
                    _,layers=portable.activity(obs)
                    memory_action=0
                    memory_logp=0.
                    if portable.has_memory:
                        logits=portable.phase_logits(layers[-1],augmented[30:])
                        probabilities=np.exp(logits-logits.max());probabilities/=probabilities.sum()
                        memory_action=int(rng.choice(MEMORY_SIZE,p=probabilities))
                        portable.memory=np.eye(MEMORY_SIZE,dtype=np.float32)[memory_action]
                        memory_actions.append(memory_action);memory_logp=float(np.log(probabilities[memory_action]))
                    mu=portable.motor_logits(layers[-1],memory_action)
                    z=mu+rng.normal(size=4)*std
                    logp=float(np.sum(-.5*((z-mu)/std)**2-np.log(std)-.5*np.log(2*np.pi)))
                    logp+=memory_logp
                    observations.append(augmented);latents.append(z);old_probs.append(logp)
                    obs,reward,done,record=env.step(np.tanh(z),action_mode=portable.action_mode)
                    rewards.append(reward);ends.append(done)
                    if done:break
                records.append(record)
            x=torch.as_tensor(np.asarray(observations),dtype=torch.float32,device=device)
            z=torch.as_tensor(np.asarray(latents),dtype=torch.float32,device=device)
            old_logp=torch.as_tensor(old_probs,dtype=torch.float32,device=device)
            memory_actions=torch.as_tensor(memory_actions,dtype=torch.long,device=device)
            with torch.no_grad():
                _,_,values=actor(x,details=True)
                v=values.cpu().numpy()
            adv=np.zeros(len(rewards),np.float32);gae=0.
            for t in range(len(rewards)-1,-1,-1):
                continuation=0. if ends[t] else 1.
                next_value=v[t+1] if t+1<len(v) else 0.
                delta=rewards[t]+.99*next_value*continuation-v[t]
                gae=delta+.99*.95*continuation*gae;adv[t]=gae
            returns=torch.as_tensor(adv+v,device=device)
            advantage=torch.as_tensor((adv-adv.mean())/(adv.std()+1e-6),device=device)
            losses=[]
            for epoch in range(4):
                for indices in np.array_split(rng.permutation(len(x)),max(1,len(x)//256)):
                    logits,layers,value=actor(x[indices],details=True,phase=memory_actions[indices] if actor.motor_heads>1 else None)
                    dist=torch.distributions.Normal(logits,actor.log_std.exp())
                    logp=dist.log_prob(z[indices]).sum(-1)
                    if actor.has_memory:
                        memory_dist=torch.distributions.Categorical(logits=actor.phase_logits(layers[-1],x[indices,30:]))
                        logp=logp+memory_dist.log_prob(memory_actions[indices])
                    ratio=(logp-old_logp[indices]).exp()
                    policy_loss=-torch.minimum(ratio*advantage[indices],ratio.clamp(.8,1.2)*advantage[indices]).mean()
                    bi=rng.integers(len(bx),size=128)
                    anchor_logits,anchor_layers,_=actor(bx[bi],details=True,phase=bp[bi] if actor.motor_heads>1 else None)
                    anchor=(torch.tanh(anchor_logits)-by[bi]).square().mean()
                    if actor.has_memory:
                        anchor=anchor+.2*torch.nn.functional.cross_entropy(actor.memory_decoder(actor.last_phase_features),bp[bi])
                    loss=policy_loss+.01*(value-returns[indices]).square().mean()+.5*anchor-1e-4*dist.entropy().sum(-1).mean()
                    optimizer.zero_grad(set_to_none=True);loss.backward()
                    torch.nn.utils.clip_grad_norm_(actor.parameters(),.5);optimizer.step()
                    with torch.no_grad():actor.log_std.clamp_(-4.,-2.5)
                    losses.append(float(loss.detach().cpu()))
            row=dict(iteration=iteration+1,transitions=len(rewards),success_count=sum(r['success'] for r in records),
                episodes=episodes,unsafe_count=sum(r['unsafe'] for r in records),mean_reward=float(np.mean([r['reward'] for r in records])),
                loss=float(np.mean(losses)),results=records)
            history.append(row);actor.save(candidate)
            actor.save(directory/f'rl-iteration{iteration+1}.npz')
            (directory/'reinforcement.json').write_text(json.dumps(dict(method='PPO with BC anchor',seed=seed,iterations=iteration+1,
                teacher_in_rollout=False,elapsed_seconds=time.time()-start,history=history),indent=2))
            event(status='training',stage='reward',step=iteration+1,steps=iterations,loss=row['loss'],reward=row['mean_reward'])
        return candidate
    finally:env.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('model');p.add_argument('--dataset',required=True);p.add_argument('--iterations',type=int,default=6);p.add_argument('--episodes',type=int,default=4);p.add_argument('--seed',type=int,default=42)
    a=p.parse_args()
    if not (1<=a.iterations<=30 and 1<=a.episodes<=12):p.error('bounded budget: 1..30 iterations, 1..12 episodes')
    refine(a.model,a.dataset,a.iterations,a.episodes,a.seed)
