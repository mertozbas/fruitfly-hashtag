"""Single-owner MuJoCo rendering process. No simulation state is shared across threads."""
import base64
import io
import queue
import time
from pathlib import Path

def simulate(commands, states):
    # Pending JPEGs can be discarded at shutdown; never wait for a full pipe.
    states.cancel_join_thread()
    import mujoco
    import numpy as np
    from PIL import Image
    from fly_sim import OdorNavigationEnv
    from odor_brain import Policy, MODEL
    from lab_render import detailed_model, sync_render
    env = None
    renderer = None
    try:
        env = OdorNavigationEnv(episode_seconds=3)
        model, render_data, render_assets = detailed_model(env)
        width, height = 1920, 1080
        model.vis.global_.offwidth = width
        model.vis.global_.offheight = height
        model.vis.quality.offsamples = 4
        renderer = mujoco.Renderer(model, height=height, width=width)
        cameras = {name: mujoco.MjvCamera() for name in ("body", "arena")}
        offsets = {name: np.zeros(3) for name in cameras}
        def camera_home(name):
            c = cameras[name]
            c.type = mujoco.mjtCamera.mjCAMERA_FREE
            c.distance, c.azimuth, c.elevation = (9, 115, -24) if name == "body" else (23, 90, -89)
            offsets[name][:] = 0
        def camera_origin(name):
            return env.position if name == "body" else np.array([11., 0., 0.])
        for name in cameras:
            camera_home(name)
        policy = Policy(MODEL / "trained.npz")
        model_id, camera, paused = "trained", "body", False
        goal, seed, episode = [12., 4.], 10, 1
        obs, _ = env.reset(seed=seed, options={"goal": goal})
        distance, reward, outcome = env.previous_distance, 0., "running"
        last_position = env.position
        speed, successes, completed, falls = 0., 0, 0, 0
        trajectory, history = [], []
        seq, last_frame, last_poll, hold = 0, time.monotonic(), time.monotonic(), 0.
        frame_steps = 0
        def send(payload):
            try:
                states.put_nowait(payload)
            except queue.Full:
                try:
                    states.get_nowait()
                except queue.Empty:
                    pass
                try:
                    states.put_nowait(payload)
                except queue.Full:
                    pass
        while True:
            reset = False
            while True:
                try:
                    command = commands.get_nowait()
                except queue.Empty:
                    break
                op = command["op"]
                if op == "shutdown":
                    return
                if op == "heartbeat":
                    last_poll = time.monotonic()
                elif op == "pause":
                    paused = command["paused"]
                elif op == "reset":
                    goal = command.get("goal", goal)
                    seed = command.get("seed", seed)
                    reset = True
                elif op == "model":
                    policy = Policy(Path(command["path"]))
                    model_id = command["id"]
                    successes = completed = falls = 0
                    reset = True
                elif op == "camera":
                    camera = command["camera"]
                    cam = cameras[camera]
                    origin = camera_origin(camera)
                    cam.lookat[:] = origin + offsets[camera]
                    if command.get("reset_view"):
                        camera_home(camera)
                        cam.lookat[:] = origin
                    else:
                        cam.azimuth += command.get("orbit", 0)
                        cam.distance += command.get("zoom", 0)
                        gesture = command.get("gesture")
                        if gesture:
                            sync_render(env, model, render_data)
                            renderer.update_scene(render_data, camera=cam)
                            actions = {"rotate": mujoco.mjtMouse.mjMOUSE_ROTATE_V,
                                       "pan": mujoco.mjtMouse.mjMOUSE_MOVE_V,
                                       "zoom": mujoco.mjtMouse.mjMOUSE_ZOOM}
                            mujoco.mjv_moveCamera(model, actions[gesture], command["dx"], command["dy"], renderer.scene, cam)
                        cam.distance = float(np.clip(cam.distance, 2.5, 65))
                        cam.elevation = float(np.clip(cam.elevation, -89, 80))
                        offsets[camera][:] = np.clip(cam.lookat - origin, -60, 60)
            if reset or (hold and time.monotonic() >= hold):
                obs, _ = env.reset(seed=seed, options={"goal": goal})
                distance, reward, outcome = env.previous_distance, 0., "running"
                hold, trajectory, history = 0., [], []
                last_position, speed = env.position, 0.
                episode += 1
            idle = time.monotonic() - last_poll > 30
            if not paused and not idle and not hold:
                turn = policy(obs)
                obs, reward, done, truncated, info = env.step([turn])
                speed = float(np.linalg.norm(env.position[:2] - last_position[:2]) / env.control_dt)
                last_position = env.position
                distance = info["distance_mm"]
                trajectory.append(env.position[:2].round(3).tolist())
                if done or truncated:
                    completed += 1
                    successes += int(info["success"])
                    falls += int(info["fallen"])
                    outcome = "success" if info["success"] else "fallen" if info["fallen"] else "timeout"
                    hold = time.monotonic() + 1.2
                frame_steps += 1
            else:
                time.sleep(.02)
            now = time.monotonic()
            if now - last_frame < (1.0 if idle else .09):
                continue
            turn, layers = policy.activity(obs)
            cam = cameras[camera]
            cam.lookat[:] = camera_origin(camera) + offsets[camera]
            sync_render(env, model, render_data)
            renderer.update_scene(render_data, camera=cam)
            rgb = renderer.render()
            jpeg = io.BytesIO()
            Image.fromarray(rgb).save(jpeg, format="JPEG", quality=96, subsampling=0)
            history.append([round(env.elapsed, 3), float(obs[0]), float(obs[1]), turn])
            history = history[-120:]
            seq += 1
            payload = dict(seq=seq, wall_time=time.time(), image=base64.b64encode(jpeg.getvalue()).decode(),
                model=model_id, paused=paused, idle=idle, camera=camera, episode=episode,
                render=dict(width=width, height=height, jpeg_quality=96, msaa=4,
                            mesh="fullsize", mesh_faces=render_assets["render_faces"]),
                camera_pose=dict(azimuth=float(cam.azimuth), elevation=float(cam.elevation), distance=float(cam.distance),
                                 lookat=cam.lookat.tolist(), offset=offsets[camera].tolist()),
                time_s=round(env.elapsed, 3), distance_mm=float(distance), goal_mm=goal,
                position_mm=env.position.tolist(), speed_mm_s=speed, reward=float(reward),
                odor=obs.tolist(), steering=turn, outcome=outcome,
                successes=successes, completed=completed, falls=falls,
                rtf=frame_steps * env.control_dt / (now - last_frame),
                activity=np.concatenate(layers).round(5).tolist(),
                layer_means=[float(a.mean()) for a in layers],
                trajectory=trajectory[-350:], history=history,
                contacts=int(env.sim.mj_data.ncon), physics_dt=env.sim.timestep)
            send(payload)
            last_frame, frame_steps = now, 0
    except Exception as exc:
        import traceback
        traceback.print_exc()
        states.put(dict(error=f"{type(exc).__name__}: {exc}", wall_time=time.time()))
    finally:
        if renderer:
            renderer.close()
        if env:
            env.close()
