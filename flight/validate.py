"""Bounded real flight rollout and render check, no training or external inference."""
import json
import time
from pathlib import Path
import numpy as np
import mujoco
from PIL import Image
from engine import Flight, ROOT

start = time.monotonic()
flight = Flight()
records = []
out = ROOT / "artifacts/lab/flight"
out.mkdir(parents=True, exist_ok=True)
for trajectory in [18, 57, 20]:
    flight.reset(10, trajectory)
    heights, errors, rewards, wings = [], [], [], []
    for step in range(3001):
        flight.step()
        t = flight.telemetry()
        heights.append(t['altitude_mm'])
        errors.append(t['tracking_error_mm'])
        rewards.append(t['reward'])
        wings.append(t['wing_angles'])
        assert np.isfinite(flight.env.physics.data.qpos).all()
        if step == 200 and trajectory == 18:
            model, data = flight.env.physics.model.ptr, flight.env.physics.data.ptr
            model.vis.global_.offwidth, model.vis.global_.offheight = 1920, 1080
            model.vis.quality.offsamples = 4
            camera = mujoco.MjvCamera()
            camera.lookat[:] = np.array(t['position_mm']) / 10
            camera.distance, camera.azimuth, camera.elevation = 1.1, 115, -20
            with mujoco.Renderer(model, height=1080, width=1920) as renderer:
                renderer.update_scene(data, camera=camera)
                pixels = renderer.render()
                assert pixels.std() > 10
                Image.fromarray(pixels).save(out / 'flight.jpg', quality=96)
        if t['done']:
            break
    record = dict(trajectory=trajectory, steps=step+1, duration_s=t['time_s'], success=t['success'],
                  min_altitude_mm=min(heights), max_tracking_error_mm=max(errors),
                  mean_tracking_error_mm=float(np.mean(errors)), mean_reward=float(np.mean(rewards)),
                  wing_ranges_rad=np.ptp(wings, axis=0).tolist())
    records.append(record)
    print(json.dumps(record), flush=True)
report = dict(source='TuragaLab/flybody pretrained flight policy', commit='d015e9bfe441bd90ae431bac24c55cb74bdbce26',
              mujoco=mujoco.__version__, physics_dt=flight.env.physics.model.opt.timestep,
              control_dt=flight.control_dt, elapsed_s=time.monotonic()-start, records=records)
(out / 'validation.json').write_text(json.dumps(report, indent=2))
assert all(r['success'] and r['min_altitude_mm'] > 2 and min(r['wing_ranges_rad']) > .1 for r in records), records
