"""Bounded physics-only teacher probe; does not import any hardware driver."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from .engine import ArmEnv


def main():
    output=Path("artifacts/so101/physics-probe")
    output.mkdir(parents=True,exist_ok=True)
    env=ArmEnv()
    records=[]
    def save(name):
        row=dict(phase=name,ee=env.ee.tolist(),cube=env.cube.tolist(),q=env.data.qpos[env.qadr].tolist(),contacts=env.contacts())
        records.append(row)
        print(json.dumps(row),flush=True)
        Image.fromarray(env.render()).save(output/(name+".png"))
    try:
        save("start")
        cube=env.cube.copy()
        for name, target, grip, steps in [
            ("above",cube+[0,0,.065],.9,40),
            ("lower",cube+[0,0,.005],.9,50),
            ("close",cube+[0,0,.005],.08,90),
            ("lift",cube+[0,0,.10],.08,60),
            ("transport",env.goal+[0,0,.10],.08,80),
            ("place",env.goal+[0,0,.025],.08,60),
            ("release",env.goal+[0,0,.025],.9,90),
            ("retreat",env.goal+[0,0,.10],.9,40),
        ]:
            env.move(target,grip,steps)
            save(name)
        (output/"report.json").write_text(json.dumps(records,indent=2))
    finally:
        env.close()

if __name__=="__main__":
    main()
