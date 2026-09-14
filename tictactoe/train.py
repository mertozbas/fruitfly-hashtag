"""Bounded supervised strategy training and exhaustive finite-game evaluation."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import time
import numpy as np
from .rules import encode,play,reachable,turn,winner
from .teacher import targets
from .policy import Policy,prepare,torch_model


def event(**values):print('LAB_EVENT '+json.dumps(values),flush=True)


def dataset(seed):
    rows={}
    for board in reachable():
        if winner(board) or 0 not in board:continue
        x,p=encode(board);key=tuple(x.astype(int))
        scores=targets(board);y=np.full(9,-2.,np.float32)
        for i,cell in enumerate(p):
            if int(cell) in scores:y[i]=scores[int(cell)]
        rows[key]=(x,y)
    x,y=map(np.stack,zip(*[rows[k] for k in sorted(rows)]))
    indices=np.random.default_rng(seed).permutation(len(x));held=np.zeros(len(x),bool);held[indices[:len(x)//5]]=True
    return x,y,held


def evaluate(path,games=400):
    policy=Policy(path)
    boards=[b for b in reachable() if not winner(b) and 0 in b]
    moves={b:policy(b) for b in boards}
    optimal=sum(targets(b)[moves[b]]==max(targets(b).values()) for b in boards)
    def matches(opponent,silenced=False,seed=731):
        rng=np.random.default_rng(seed);wins=draws=losses=0
        selected={b:policy.activity(b,True)[0] for b in boards} if silenced else moves
        for game in range(games):
            side=1 if game%2==0 else -1;b=(0,)*9
            while not winner(b) and 0 in b:
                if turn(b)==side:cell=selected[b]
                else:
                    choices=[i for i,v in enumerate(b) if not v]
                    if opponent=='minimax':
                        scores=targets(b);choices=[i for i in choices if scores[i]==max(scores.values())]
                    cell=int(rng.choice(choices))
                b=play(b,cell)
            w=winner(b);wins+=w==side;draws+=w==0;losses+=w==-side
        return dict(episodes=games,wins=int(wins),draws=int(draws),losses=int(losses),success_count=int(wins+draws),seed=seed)
    # Explore every legal opponent reply from the empty board, for both roles.
    # This is a finite exhaustive guarantee for the exported strategy, not for robot execution.
    from functools import lru_cache
    @lru_cache(None)
    def worst(b,side):
        w=winner(b)
        if w or 0 not in b:return w*side
        if turn(b)==side:return worst(play(b,moves[b]),side)
        return min(worst(play(b,i),side) for i,v in enumerate(b) if not v)
    random=matches('random');minimax=matches('minimax');silent=matches('random',True)
    return dict(task='tictactoe',strategy_only=True,success_count=minimax['success_count'],episodes=games,
        criterion='Sanal tahtada iki rolde minimax karşısında kaybetmeme; robot yerleştirme ayrı değerlendirilir.',
        reachable_decision_boards=len(boards),optimal_decisions=int(optimal),optimal_fraction=optimal/len(boards),
        random_opponent=random,minimax_opponent=minimax,controls={'silenced':silent},
        worst_case_by_role={'X':worst((0,)*9,1),'O':worst((0,)*9,-1)},
        acceptance_passed=worst((0,)*9,1)>=0 and worst((0,)*9,-1)>=0,
        scope='Final model trained on the complete finite canonical board set. Exhaustive board coverage is not held-out generalization. No teacher in policy inference.')


def train(directory,steps=6000,seed=51):
    import torch
    if not 200<=steps<=10000:raise ValueError('Training steps must be 200..10000')
    directory=Path(directory)
    if (directory/'trained.npz').exists():raise FileExistsError('Yeni bir çıktı dizini seç; mevcut model korunuyor.')
    directory.mkdir(parents=True,exist_ok=True)
    meta=dict(id=directory.name,name='Tic-tac-toe · öğrenilmiş strateji',task='tictactoe',status='training',
              created=datetime.now(timezone.utc).isoformat(),owner_pid=os.getpid(),steps=steps,seed=seed)
    (directory/'run.json').write_text(json.dumps(meta,indent=2))
    try:
        circuit=prepare(directory);x,y,held=dataset(seed)
        np.savez_compressed(directory/'boards.npz',inputs=x,targets=y,heldout=held)
        torch.set_num_threads(2);device=torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
        actor=torch_model(circuit,seed).to(device);actor.save(directory/'untrained.npz')
        tx,ty=torch.from_numpy(x).to(device),torch.from_numpy(y).to(device)
        legal=ty>-2;optimal=ty==ty.max(-1,keepdim=True).values
        optimizer=torch.optim.Adam(actor.parameters(),lr=.002)
        rng=np.random.default_rng(seed);start=time.time();history=[];generalization=None
        split_step=int(steps*.6);best=-1.;best_loss=float('inf')
        def metrics(mask):
            with torch.no_grad():
                logits=actor(tx[mask]).masked_fill(~legal[mask],-1e9)
                chosen=logits.argmax(-1)
                correct=optimal[mask].gather(1,chosen[:,None]).float().mean().item()
                loss=(torch.logsumexp(logits,-1)-torch.logsumexp(logits.masked_fill(~optimal[mask],-1e9),-1)).mean().item()
                return correct,loss
        for step in range(1,steps+1):
            indices=np.flatnonzero(~held) if step<=split_step else np.arange(len(x))
            batch=rng.choice(indices,128)
            logits=actor(tx[batch]);masked=logits.masked_fill(~legal[batch],-1e9)
            set_loss=(torch.logsumexp(masked,-1)-torch.logsumexp(masked.masked_fill(~optimal[batch],-1e9),-1)).mean()
            # Every legal move gets an outcome target, while ties remain free.
            qloss=((logits-ty[batch]).square()*legal[batch]).sum()/legal[batch].sum()
            loss=set_loss+.15*qloss
            optimizer.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(actor.parameters(),2.);optimizer.step()
            if step%100==0 or step in (split_step,steps):
                accuracy,error=metrics(held if step<=split_step else np.ones(len(x),bool))
                history.append([step,error]);event(status='training',step=step,steps=steps,loss=error,accuracy=accuracy,
                    stage='symmetry_disjoint_validation' if step<=split_step else 'complete_board_curriculum',history=history)
                if step<=split_step:
                    if accuracy>best or (accuracy==best and error<best_loss):
                        best,best_loss=accuracy,error;actor.save(directory/'heldout-best.npz')
                else:
                    if accuracy>best or (accuracy==best and error<best_loss):
                        best,best_loss=accuracy,error;actor.save(directory/'trained.npz')
            if step==split_step:
                actor.restore(directory/'heldout-best.npz')
                accuracy,error=metrics(held)
                generalization=dict(optimal_fraction=accuracy,loss=error,train_canonical_boards=int((~held).sum()),
                    heldout_canonical_boards=int(held.sum()),split='Whole D4 symmetry orbits held out; no rotated/reflected board leakage.')
                best=-1.;best_loss=float('inf')
        actor.restore(directory/'trained.npz');saved=Policy(directory/'trained.npz')
        b=next(b for b in reachable() if not winner(b) and 0 in b)
        _,_,d=saved.activity(b);p=np.array(d['permutation'])
        with torch.no_grad():expected=actor(torch.tensor(d['input'],device=device)[None]).cpu().numpy()[0]
        parity=float(np.max(np.abs(expected-np.asarray(d['logits'])[p])))
        if parity>2e-4:raise AssertionError('Torch/NumPy mismatch '+str(parity))
        changes=[int(np.count_nonzero(np.abs(w.toarray()[base.toarray()!=0]/base.toarray()[base.toarray()!=0]-1)>.001)) for w,base in zip(saved.layers,circuit.layers)]
        report=dict(task='tictactoe',method='minimax_supervision',seed=seed,steps=steps,history=history,after_mse=best_loss,
            loss_name='optimal_move_set_loss',changed_existing_synaptic_gains=sum(changes),changed_existing_synaptic_gains_by_layer=changes,
            generalization=generalization,complete_canonical_boards=len(x),elapsed_seconds=time.time()-start,
            teacher_in_rollout=False,torch_numpy_max_error=parity,checkpoint_sha256=hashlib.sha256((directory/'trained.npz').read_bytes()).hexdigest(),
            scope='Learned strategy on anatomical connectivity; independent from the preserved SO-101 motor checkpoint. No biological learning claim.')
        (directory/'training.json').write_text(json.dumps(report,indent=2))
        event(status='evaluating',step=steps,steps=steps)
        result=evaluate(directory/'trained.npz');result['generalization']=generalization
        before=evaluate(directory/'untrained.npz',400)
        result['controls']['untrained']={**before['random_opponent'],'optimal_fraction':before['optimal_fraction']}
        (directory/'evaluation.json').write_text(json.dumps(result,indent=2))
        meta.update(status='complete',acceptance_passed=result['acceptance_passed'])
        event(status='complete',step=steps,steps=steps,message='Strateji eğitildi; sanal tahta değerlendirmesi kaydedildi.',evaluation=result)
        return result
    except BaseException:
        meta['status']='failed';raise
    finally:(directory/'run.json').write_text(json.dumps(meta,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--steps',type=int,default=6000);p.add_argument('--seed',type=int,default=51)
    a=p.parse_args();train(a.output,a.steps,a.seed)
