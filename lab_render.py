"""Detailed render-only model. Physics remains on the validated low-poly model."""
import hashlib
import json
from pathlib import Path
import mujoco
import numpy as np
from flygym.compose.fly.neuromechfly import lazy_load_asset_dir, NEUROMECHFLY_FULLSIZE_MESH_DIR

def detailed_model(env):
    source = lazy_load_asset_dir(NEUROMECHFLY_FULLSIZE_MESH_DIR)
    spec = env.sim.world.mjcf_root.copy()
    files = set()
    for mesh in spec.meshes:
        if "simplified_max2000faces" in mesh.file:
            path = source / Path(mesh.file).name
            if not path.is_file():
                raise FileNotFoundError(f"Missing detailed render mesh: {path.name}")
            mesh.file = str(path)
            files.add(path)
    render = spec.compile()
    physics = env.sim.mj_model
    if (render.nq, render.nv, render.nbody, render.ngeom) != (physics.nq, physics.nv, physics.nbody, physics.ngeom):
        raise ValueError("Render and physics body layouts differ")
    for kind, count in [(mujoco.mjtObj.mjOBJ_BODY, physics.nbody), (mujoco.mjtObj.mjOBJ_GEOM, physics.ngeom), (mujoco.mjtObj.mjOBJ_JOINT, physics.njnt)]:
        for i in range(count):
            if mujoco.mj_id2name(render,kind,i) != mujoco.mj_id2name(physics,kind,i):
                raise ValueError("Render and physics naming/order mismatch")
    if not (np.allclose(render.body_pos, physics.body_pos) and np.allclose(render.body_quat, physics.body_quat)):
        raise ValueError("Render model changed body frames")
    # The detailed model is never stepped; all qpos come from the original simulator.
    record = dict(asset=NEUROMECHFLY_FULLSIZE_MESH_DIR, physics_faces=int(physics.mesh_facenum.sum()),
                  render_faces=int(render.mesh_facenum.sum()), purpose="render only; original physics and checkpoint unchanged",
                  files=[dict(file=p.name, bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(files)])
    target = Path(__file__).resolve().parent / "artifacts/lab/render-assets.json"
    target.write_text(json.dumps(record,indent=2))
    return render, mujoco.MjData(render), record

def sync_render(env, model, data):
    data.qpos[:] = env.sim.mj_data.qpos
    data.time = env.sim.mj_data.time
    model.geom_pos[env.goal_geom] = env.sim.mj_model.geom_pos[env.goal_geom]
    mujoco.mj_kinematics(model, data)
    mujoco.mj_camlight(model, data)
