"""Checkpoint değiştirmeden gerçek fizikten dokümantasyon kaydı üretir.

Seçili davranışın bilimsel Python ortamıyla çalıştırın.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("behavior", choices=["walking", "flight"])
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    home, output = args.home.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sys.path[:0] = [str(home / "flight"), str(home)]
    import numpy as np
    model = home / "models/odor_navigation/trained.npz"
    metadata = dict(behavior=args.behavior, seed=10,
                    model_sha256=hashlib.sha256(model.read_bytes()).hexdigest())
    if args.behavior == "walking":
        from fly_sim import rollout
        from odor_policy import Policy
        metadata.update(goal_mm=[12, 4], playback_speed=0.2, resolution=[640, 480])
        metadata["runs"] = {}
        for name in ["untrained", "trained"]:
            path = model.with_name(name + ".npz")
            result = rollout(Policy(path), seed=10, goal=(12, 4), seconds=3,
                             video=output / f"walking-{name}.mp4")
            result["model_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            metadata["runs"][name] = result
    else:
        import mujoco
        from navigation import BrainFlight
        flight = BrainFlight(model)
        flight.reset(seed=10, goal=(22, 6))
        physics = flight.env.physics
        physics.model.vis.global_.offwidth = 1280
        physics.model.vis.global_.offheight = 720
        physics.model.vis.quality.offsamples = 4
        renderer = mujoco.Renderer(physics.model.ptr, height=720, width=1280)
        camera = mujoco.MjvCamera()
        camera.type = mujoco.mjtCamera.mjCAMERA_FREE
        camera.distance, camera.azimuth, camera.elevation = 1.05, 115, -22
        command = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                   "-s", "1280x720", "-r", "30", "-i", "-", "-an", "-c:v", "libx264",
                   "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                   str(output / "flight.mp4")]
        encoder = subprocess.Popen(command, stdin=subprocess.PIPE)
        records = []
        try:
            for step in range(round(flight.seconds / flight.control_dt)):
                flight.step()
                if step % 5 == 0:
                    camera.lookat[:] = physics.named.data.subtree_com["walker/"]
                    renderer.update_scene(physics.data.ptr, camera=camera)
                    for i in range(renderer.scene.ngeom):
                        geom = renderer.scene.geoms[i]
                        if geom.objid < 0:
                            continue
                        if geom.objtype == mujoco.mjtObj.mjOBJ_SITE:
                            name = mujoco.mj_id2name(physics.model.ptr, geom.objtype, geom.objid) or ""
                            if name != "odor_target":
                                geom.rgba[3] = 0
                        elif geom.objtype == mujoco.mjtObj.mjOBJ_GEOM:
                            name = mujoco.mj_id2name(physics.model.ptr, geom.objtype, geom.objid) or ""
                            if name.startswith("ghost/"):
                                geom.rgba[3] = 0
                    encoder.stdin.write(renderer.render().tobytes())
                    records.append(flight.telemetry())
                if flight.telemetry()["done"]:
                    break
            final = flight.telemetry()
        finally:
            encoder.stdin.close()
            code = encoder.wait()
            renderer.close()
            flight.env.close()
        if code:
            raise RuntimeError("Video encoding failed")
        metadata.update(goal_mm=[22, 6], resolution=[1280, 720], fps=30,
                        physics_seconds_per_frame=0.001, playback_speed=0.03,
                        final=final, frames=records)
    def convert(value):
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        raise TypeError(type(value).__name__)
    (output / f"{args.behavior}-recording.json").write_text(json.dumps(metadata, indent=2, default=convert))
    print(json.dumps({k: v for k, v in metadata.items() if k not in ["runs", "frames", "final"]}))


if __name__ == "__main__":
    main()
