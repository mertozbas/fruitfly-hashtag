"""Single-owner live aerodynamic simulation, controlled by private JSON pipes."""
import base64
import io
import json
import queue
import sys
import threading
import time
import traceback
from pathlib import Path

commands = queue.Queue(32)
def receive():
    for line in sys.stdin:
        commands.put(json.loads(line))
    commands.put({'op': 'shutdown'})

def main():
    import argparse
    import mujoco
    import numpy as np
    from PIL import Image
    from navigation import BrainFlight, ROOT
    sys.path.insert(0, str(ROOT))
    from lab_flight import metadata
    parser = argparse.ArgumentParser()
    parser.add_argument('--model',type=Path,default=ROOT/'models/odor_navigation/trained.npz')
    parser.add_argument('--model-id',default='trained')
    args = parser.parse_args()
    threading.Thread(target=receive, daemon=True).start()
    flight = BrainFlight(args.model)
    model_id = args.model_id
    policy_sha = metadata()['sha256']
    goals, goal_index, seed = [(25.,8.),(25.,-8.),(22.,6.),(22.,-6.)], 0, 10
    goal = goals[0]
    width, height, playback = 1920, 1080, .01
    camera, paused, episode = 'body', False, 0
    successes = completed = falls = 0
    seq, hold, last_poll = 0, 0., time.monotonic()
    last_frame = last_step = time.monotonic()
    frame_steps, history, trajectory = 0, [], []
    renderer = None
    cameras = {name: mujoco.MjvCamera() for name in ('body', 'arena')}
    offsets = {name: np.zeros(3) for name in cameras}
    def home(name):
        c = cameras[name]
        c.type = mujoco.mjtCamera.mjCAMERA_FREE
        c.distance, c.azimuth, c.elevation = (1.05, 115, -22) if name == 'body' else (6, 100, -50)
        offsets[name][:] = 0
    for name in cameras:
        home(name)
    def origin(name):
        if name == 'body':
            return flight.env.physics.named.data.subtree_com['walker/'].copy()
        return np.r_[np.asarray(goal)/20,1.]
    def reset():
        nonlocal renderer, episode, hold, history, trajectory, frame_steps, last_step
        if renderer:
            renderer.close()
        flight.reset(seed, goal)
        model = flight.env.physics.model.ptr
        model.vis.global_.offwidth, model.vis.global_.offheight = width, height
        model.vis.quality.offsamples = 4
        # Hide only reference ghost geometry. The real fly and its fluid geoms
        # retain their original physics; reference sites remain visible in arena.
        for i in range(model.ngeom):
            name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, i) or ''
            if name.startswith('ghost/'):
                model.geom_rgba[i, 3] = 0
                model.geom_group[i] = 5  # Excluded from default render and shadows.
        renderer = mujoco.Renderer(model, height=height, width=width)
        episode += 1
        hold, history, trajectory, frame_steps = 0., [], [], 0
        last_step = time.monotonic()
    reset()
    try:
        while True:
            restart = False
            while True:
                try:
                    command = commands.get_nowait()
                except queue.Empty:
                    break
                op = command['op']
                if op == 'shutdown':
                    return
                if op == 'heartbeat':
                    last_poll = time.monotonic()
                elif op == 'pause':
                    paused = command['paused']
                elif op == 'reset':
                    seed = command.get('seed', seed)
                    goal = command.get('goal', goal)
                    restart = True
                elif op == 'next':
                    goal_index = (goal_index + 1) % len(goals)
                    goal = goals[goal_index]
                    restart = True
                elif op == 'model':
                    flight.load_brain(command['path'])
                    model_id = command['id']
                    successes = completed = falls = 0
                    restart = True
                elif op == 'camera':
                    camera = command['camera']
                    cam = cameras[camera]
                    cam.lookat[:] = origin(camera) + offsets[camera]
                    if command.get('reset_view'):
                        home(camera)
                        cam.lookat[:] = origin(camera)
                    else:
                        cam.azimuth += command.get('orbit', 0)
                        cam.distance += command.get('zoom', 0) * .12
                        if command.get('gesture'):
                            renderer.update_scene(flight.env.physics.data.ptr, camera=cam)
                            actions = {'rotate': mujoco.mjtMouse.mjMOUSE_ROTATE_V, 'pan': mujoco.mjtMouse.mjMOUSE_MOVE_V, 'zoom': mujoco.mjtMouse.mjMOUSE_ZOOM}
                            mujoco.mjv_moveCamera(flight.env.physics.model.ptr, actions[command['gesture']], command['dx'], command['dy'], cam)
                        cam.distance = float(np.clip(cam.distance, .35, 20))
                        cam.elevation = float(np.clip(cam.elevation, -89, 80))
                        offsets[camera][:] = np.clip(cam.lookat - origin(camera), -15, 15)
            idle = time.monotonic() - last_poll > 30
            if restart or (hold and not paused and not idle and time.monotonic() >= hold):
                reset()
            now = time.monotonic()
            if not paused and not idle and not hold and now - last_step >= flight.control_dt / playback:
                flight.step()
                frame_steps += 1
                last_step = now
                if flight.success or flight.ts.last():
                    completed += 1
                    successes += int(flight.success)
                    falls += int(flight.ts.last() and flight.ts.discount == 0)
                    hold = now + 1.2
            if now - last_frame < (1 if idle else .065):
                time.sleep(.002)
                continue
            t = flight.telemetry()
            cam = cameras[camera]
            cam.lookat[:] = origin(camera) + offsets[camera]
            renderer.update_scene(flight.env.physics.data.ptr, camera=cam)
            # Track/crosshair sites distract from the close body view.
            for i in range(renderer.scene.ngeom):
                geom = renderer.scene.geoms[i]
                if geom.objtype == mujoco.mjtObj.mjOBJ_SITE and geom.objid >= 0:
                    name = mujoco.mj_id2name(flight.env.physics.model.ptr, mujoco.mjtObj.mjOBJ_SITE, geom.objid) or ''
                    if name != 'odor_target':
                        geom.rgba[3] = 0
                if geom.objtype == mujoco.mjtObj.mjOBJ_GEOM and geom.objid >= 0:
                    name = mujoco.mj_id2name(flight.env.physics.model.ptr, mujoco.mjtObj.mjOBJ_GEOM, geom.objid) or ''
                    if name.startswith('ghost/'):
                        geom.rgba[3] = 0
            pixels = renderer.render()
            jpeg = io.BytesIO()
            Image.fromarray(pixels).save(jpeg, format='JPEG', quality=96, subsampling=0)
            history.append([t['time_s'], *t['odor'], t['steering'], t['reward']])
            history = history[-120:]
            trajectory.append(t['position_mm'])
            trajectory = trajectory[-350:]
            seq += 1
            packet = dict(**t, seq=seq, wall_time=time.time(), behavior='flight',
                image=base64.b64encode(jpeg.getvalue()).decode(), model=model_id,
                model_sha256=flight.brain_sha, circuit_identity=flight.brain.circuit.identity,
                activity=np.concatenate(flight.layers).round(5).tolist(),layer_means=[float(a.mean()) for a in flight.layers],
                neural=dict(source='Policy.activity', kind='continuous_forward_response', sample_time_s=flight.brain_sample_time,
                    applied_steering=flight.applied_turn if flight.step_count else None,
                    applied_to_physics=flight.step_count>0,raw_steering=flight.turn,neutral_steering=flight.neutral_turn,
                    yaw_rate_rad_s=flight.yaw_rate, yaw_gain=flight.yaw_gain,max_yaw_rate_rad_s=8.,
                    brain_dt=flight.brain_dt,control_dt=flight.control_dt,cpg_drive=None,
                    adapter='trimmed MBON readout -> bounded yaw-rate reference -> FlyBody wing policy',
                    motor_model_sha256=policy_sha,sensor_positions_mm=flight.sensor_positions.tolist(),
                    motor_action=flight.action.tolist(),brain_connected=True),
                paused=paused, idle=idle, camera=camera, episode=episode, seed=seed,
                camera_pose=dict(azimuth=float(cam.azimuth), elevation=float(cam.elevation), distance=float(cam.distance),
                                 lookat=cam.lookat.tolist(), offset=offsets[camera].tolist()),
                render=dict(width=width, height=height, msaa=4, jpeg_quality=96, mesh='FlyBody official',
                            mesh_faces=int(flight.env.physics.model.mesh_facenum.sum())),
                outcome='success' if t['success'] else 'fallen' if flight.ts.last() and flight.ts.discount==0 else 'timeout' if t['done'] else 'running',
                successes=successes, completed=completed, falls=falls,
                rtf=frame_steps*flight.control_dt/(now-last_frame), playback_target=playback,
                trajectory=trajectory, history=history, contacts=int(flight.env.physics.data.ncon))
            print(json.dumps(packet, allow_nan=False), flush=True)
            last_frame, frame_steps = now, 0
    finally:
        if renderer:
            renderer.close()
        flight.env.close()

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps(dict(error=f'{type(exc).__name__}: {exc}', behavior='flight', wall_time=time.time())), flush=True)
        sys.exit(1)
