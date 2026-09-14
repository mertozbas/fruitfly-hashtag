"""Hash the actual local physical assets and record simulator assumptions."""
import hashlib
import json
from pathlib import Path
import platform
import mujoco
from .engine import ROBOT_SOURCE,ACCESSORIES,scene_xml,DT,CONTROL_DT


def manifest(output):
    files=[ROBOT_SOURCE/'so101_new_calib.xml',*sorted((ROBOT_SOURCE/'assets').glob('*.stl')),
           *[ACCESSORIES/'stl'/f'{n}.stl' for n in ('cube_red_red','cube_red_black','sort_bin_black','sort_bin_white')]]
    report=dict(python=platform.python_version(),mujoco=mujoco.__version__,physics_dt=DT,control_dt=CONTROL_DT,
        solver='PGS',iterations=100,cone='elliptic',cube_mass_kg=.012,finger_friction=.9,gripper_force_limit_nm=.25,
        grasp='physical mesh contacts only; no weld, attachment or object pose writes outside reset',
        collision_approximation='slab convex hulls of original finger meshes; separate bin walls',
        hardware_enabled=False,scene_sha256=hashlib.sha256(scene_xml().encode()).hexdigest(),
        files=[dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files])
    Path(output).write_text(json.dumps(report,indent=2));return report

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',default='artifacts/so101/assets-manifest.json');a=p.parse_args();manifest(a.output)
