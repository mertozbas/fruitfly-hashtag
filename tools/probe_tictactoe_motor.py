"""Bounded camera/contact rollout of the experimental block motor readout."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tictactoe.scene import GameEnv
from tictactoe.vision import Eyes
from tictactoe.policy import Policy
from tictactoe.motor import Motor,Controller,PHASES


def probe(path,cell,output,silenced=False):
    env=GameEnv(token_style='blocks');eyes=Eyes(env);policy=Policy(path)
    controller=Controller(env,eyes,Motor(policy,path),cell,silenced);last=None;records=[]
    try:
        for step in range(1201):
            controller.step()
            if controller.phase!=last or step%100==0:
                row=dict(step=step,phase=PHASES[controller.phase],attempt=controller.attempt,tcp=env.ee.round(4).tolist(),
                    cube=env.cube.round(4).tolist(),seen=controller.position.round(4).tolist(),error=controller.error,
                    verification=controller.verification)
                records.append(row);print(json.dumps(row),flush=True);last=controller.phase
                if controller.phase==8:
                    import base64
                    Path(output).with_name(Path(output).stem+f'-park-{step}.jpg').write_bytes(base64.b64decode(eyes.images['top']))
            if controller.done:break
        report=dict(cell=cell,outcome=controller.outcome,success=controller.success,error=controller.error,
                    seconds=controller.elapsed,attempts=controller.attempt,trace=records,silenced=silenced,
                    sensor='top/wrist synthetic RGB-D; no object pose in observation',token_geometry='30 mm marked training blocks',verification=controller.verification)
        Path(output).write_text(json.dumps(report,indent=2));print('RESULT '+json.dumps({k:v for k,v in report.items() if k!='trace'}),flush=True)
        return report
    finally:eyes.close();env.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',default='models/lab_runs/local-tictactoe-robot-seed52/trained.npz');p.add_argument('--cell',type=int,default=4);p.add_argument('--output',default='artifacts/tictactoe/motor-probe.json');p.add_argument('--silenced',action='store_true');a=p.parse_args();probe(a.model,a.cell,a.output,a.silenced)
