"""Finite destination and sequential-game camera/physics acceptance suite."""
import argparse
import json
import hashlib
from datetime import datetime,timezone
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tictactoe.scene import GameEnv
from tictactoe.vision import Eyes
from tictactoe.policy import Policy
from tictactoe.motor import Motor,Controller
from tictactoe.rules import turn,winner


def evaluate(path,output,cells=range(9),trace=False):
    path=Path(path);env=GameEnv(token_style='blocks');eyes=Eyes(env);policy=Policy(path);motor=Motor(policy,path);rows=[];games=[]
    checkpoint_sha=hashlib.sha256(path.read_bytes()).hexdigest()
    def run(cell,silenced=False):
        c=Controller(env,eyes,motor,cell,silenced)
        previous=None
        for step in range(1201):
            c.step()
            key=(c.attempt,c.phase)
            if trace and (key!=previous or step%100==0):
                print('TRACE '+json.dumps(dict(cell=cell,token=env.used['X'],step=step,phase=c.phase,attempt=c.attempt,
                    tcp=env.ee.round(4).tolist(),cube=env.cube.round(4).tolist(),seen=c.position.round(4).tolist(),error=c.error)),flush=True)
                previous=key
            if c.done:break
        r=dict(cell=cell,success=c.success,outcome=c.outcome,seconds=c.elapsed,attempts=c.attempt,error=c.error)
        print(json.dumps(r),flush=True);return r
    try:
        for cell in cells:
            env.reset(cell);eyes.close();eyes=Eyes(env)
            rows.append(run(cell))
        # A full self-play game exercises successive source tokens and occupied cells.
        env.reset();eyes.close();eyes=Eyes(env);moves=[]
        while not winner(env.board) and 0 in env.board:
            cell=policy(env.board)
            if turn(env.board)==1:
                r=run(cell);moves.append(r)
                if not r['success']:break
            else:env.virtual_move(cell,-1)
        games.append(dict(board=list(env.board),moves=moves,complete=bool(winner(env.board) or 0 not in env.board)))
        env.reset();eyes.close();eyes=Eyes(env);silenced=run(4,True)
        report=dict(model_sha256=checkpoint_sha,episodes=len(rows),success_count=sum(r['success'] for r in rows),rows=rows,games=games,silenced=silenced,
            acceptance_passed=len(rows)==9 and all(r['success'] for r in rows) and games[0]['complete'] and not silenced['success'],
            sensor='synthetic RGB-D / top + wrist / fixed palette',geometry='30 mm marked training cubes; original 240 mm board',
            scope=f'Simulation only. {len(rows)} single-move destinations, one sequential self-play game and one silenced motor control. No arbitrary disturbance robustness claim.')
        Path(output).write_text(json.dumps(report,indent=2));print('REPORT '+json.dumps({k:v for k,v in report.items() if k not in ('rows','games')}),flush=True)
        return report
    finally:eyes.close();env.close()


def register(path,report):
    """Expose a fitted motor model in the lab only after the full suite passes."""
    path=Path(path);directory=path.parent;sha=hashlib.sha256(path.read_bytes()).hexdigest()
    if not report['acceptance_passed'] or report['model_sha256']!=sha:
        raise ValueError('Motor kabul testi ve model dosyası eşleşmeli; model kaydedilmedi.')
    evaluation=json.loads((directory/'evaluation.json').read_text())
    evaluation.update(motor_evaluation=report,strategy_only=False,checkpoint_sha256=sha)
    (directory/'evaluation.json').write_text(json.dumps(evaluation,indent=2))
    (directory/'motor-evaluation.json').write_text(json.dumps(report,indent=2))
    training=json.loads((directory/'training.json').read_text())
    training.setdefault('strategy_checkpoint_sha256',training['checkpoint_sha256'])
    training.update(checkpoint_sha256=sha,motor_training=json.loads((directory/'motor-training.json').read_text()))
    (directory/'training.json').write_text(json.dumps(training,indent=2))
    meta=dict(id=directory.name,name='Tic-tac-toe · strateji + robot',task='tictactoe',status='complete',
        created=datetime.now(timezone.utc).isoformat(),steps=training['steps'],seed=training['seed'],
        acceptance_passed=evaluation['acceptance_passed'],motor_acceptance_passed=True)
    (directory/'run.json').write_text(json.dumps(meta,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',default='models/lab_runs/local-tictactoe-robot-seed52/trained.npz');p.add_argument('--output',default='artifacts/tictactoe/motor-evaluation.json')
    p.add_argument('--game-only',action='store_true');p.add_argument('--trace',action='store_true')
    p.add_argument('--register',action='store_true',help='Add to UI only if the full motor acceptance suite passes')
    a=p.parse_args();report=evaluate(a.model,a.output,() if a.game_only else range(9),a.trace)
    if a.register:register(a.model,report)
