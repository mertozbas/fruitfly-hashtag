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
    import mujoco
    import numpy as np
    from PIL import Image
    from engine import Flight, ROOT
    sys.path.insert(0, str(ROOT))
    from lab_flight import metadata
    threading.Thread(target=receive, daemon=True).start()
    flight = Flight()
    policy_sha = metadata()['sha256']
    routes, route_index, seed = [18, 57, 20], 0, 10
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
        return flight.env.task._ref_qpos[min(len(flight.env.task._ref_qpos)-1, flight.env.task._traj_timesteps//2), :3].copy()
    def reset():
        nonlocal renderer, episode, hold, history, trajectory, frame_steps, last_step
        if renderer:
            renderer.close()
        flight.reset(seed, routes[route_index])
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
                    restart = True
                elif op == 'next':
                    route_index = (route_index + 1) % len(routes)
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
                if not restart:
                    route_index = (route_index + 1) % len(routes)
                reset()
            now = time.monotonic()
            if not paused and not idle and not hold and now - last_step >= flight.control_dt / playback:
                flight.step()
                frame_steps += 1
                last_step = now
                if flight.ts.last():
                    completed += 1
                    successes += int(flight.ts.discount == 1)
                    falls += int(flight.ts.discount == 0)
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
                if camera == 'body' and geom.objtype == mujoco.mjtObj.mjOBJ_SITE:
                    geom.rgba[3] = 0
                if geom.objtype == mujoco.mjtObj.mjOBJ_GEOM and geom.objid >= 0:
                    name = mujoco.mj_id2name(flight.env.physics.model.ptr, mujoco.mjtObj.mjOBJ_GEOM, geom.objid) or ''
                    if name.startswith('ghost/'):
                        geom.rgba[3] = 0
            pixels = renderer.render()
            jpeg = io.BytesIO()
            Image.fromarray(pixels).save(jpeg, format='JPEG', quality=96, subsampling=0)
            history.append([t['time_s'], t['altitude_mm'], t['tracking_error_mm'], t['wing_hz'], t['reward']])
            history = history[-120:]
            trajectory.append(t['position_mm'])
            trajectory = trajectory[-350:]
            seq += 1
            packet = dict(**t, seq=seq, wall_time=time.time(), behavior='flight',
                image=base64.b64encode(jpeg.getvalue()).decode(), model='flight-pretrained',
                model_sha256=policy_sha, circuit_identity=None, activity=None, layer_means=[],
                neural=dict(source='FlyBody pretrained motor policy', kind='not_connected_to_MaleCNS', cpg_drive=None),
                paused=paused, idle=idle, camera=camera, episode=episode, seed=seed,
                camera_pose=dict(azimuth=float(cam.azimuth), elevation=float(cam.elevation), distance=float(cam.distance),
                                 lookat=cam.lookat.tolist(), offset=offsets[camera].tolist()),
                render=dict(width=width, height=height, msaa=4, jpeg_quality=96, mesh='FlyBody official',
                            mesh_faces=int(flight.env.physics.model.mesh_facenum.sum())),
                distance_mm=t['tracking_error_mm'], goal_mm=None, odor=[], steering=None,
                outcome='success' if t['success'] else 'fallen' if t['done'] else 'running',
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
