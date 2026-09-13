"""MuJoCo body and an explicit, synthetic bilateral odor-navigation task.

Body/controller: FlyGym 2.1, Apache-2.0, NeLy-EPFL.
https://neuromechfly.org/tutorials/4d_turning_controller/
The low-level walking controller is a CPG, not a MaleCNS VNC emulation.
"""

import argparse
import json
from pathlib import Path
import time

import gymnasium as gym
import mujoco
import numpy as np
from flygym import Simulation
from flygym.anatomy import BodySegment, ContactBodiesPreset
from flygym.compose import FlatGroundWorld
from flygym.utils.math import Rotation3D
from flygym_demo.complex_terrain import (
    HybridControllerObservation, HybridTurningController, LocomotionAction,
    PreprogrammedSteps, apply_locomotion_action, make_locomotion_fly,
)

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "artifacts" / "simulation"


class OdorNavigationEnv(gym.Env):
    """One action = signed steering; two observations = antenna concentrations.

    Synthetic static odor field: 1 / (1 + (distance_mm / 5)**2).
    Actions do not receive goal position, distance, or the teacher's output.
    """

    metadata = {"render_modes": ["rgb_array"], "render_fps": 30}

    def __init__(self, *, record=False, episode_seconds=3.0, control_dt=0.01):
        super().__init__()
        self.observation_space = gym.spaces.Box(0, 1, (2,), dtype=np.float32)
        self.action_space = gym.spaces.Box(-1, 1, (1,), dtype=np.float32)
        self.control_dt = float(control_dt)
        self.episode_seconds = float(episode_seconds)
        self.fly = make_locomotion_fly(name="hashtag_fly", add_adhesion=True, colorize=False)
        camera = self.fly.add_tracking_camera(
            name="body_camera", pos_offset=(-0.5, -8.5, 2.8),
            rotation=Rotation3D("euler", (1.25, 0, 0)), fovy=38,
        )
        world = FlatGroundWorld(half_size=100)
        arena_camera = world.mjcf_root.worldbody.add_camera(
            name="arena_camera", pos=[11, 0, 23], quat=[1, 0, 0, 0], fovy=55)
        self.video_cameras = [camera, arena_camera]
        world.mjcf_root.worldbody.add_geom(
            name="odor_target", type=mujoco.mjtGeom.mjGEOM_SPHERE,
            pos=[12, 4, .3], size=[.45, 0, 0], rgba=[.95, .38, .12, 1],
            contype=0, conaffinity=0,
        )
        world.add_fly(self.fly, [0, 0, .8], Rotation3D("quat", [1, 0, 0, 0]),
                      bodysegs_with_ground_contact=ContactBodiesPreset.TIBIA_TARSUS_ONLY,
                      add_ground_contact_sensors=False)
        self.sim = Simulation(world)
        self.substeps = round(self.control_dt / self.sim.timestep)
        if not np.isclose(self.substeps * self.sim.timestep, self.control_dt):
            raise ValueError("control_dt must be an integer multiple of physics timestep")
        self.steps_pattern = PreprogrammedSteps()
        self.dofs = self.fly.get_actuated_jointdofs_order("position")
        self.controller = HybridTurningController(timestep=self.sim.timestep,
                          preprogrammed_steps=self.steps_pattern, output_dof_order=self.dofs)
        order = self.fly.get_bodysegs_order()
        self.thorax = order.index(BodySegment("c_thorax"))
        self.antennae = [order.index(BodySegment("l_funiculus")), order.index(BodySegment("r_funiculus"))]
        self.goal_geom = mujoco.mj_name2id(self.sim.mj_model, mujoco.mjtObj.mjOBJ_GEOM, "odor_target")
        if record:
            self.sim.set_renderer(self.video_cameras, camera_res=(480, 640), output_fps=30, playback_speed=.2)
        self.elapsed = 0.0
        self.goal = np.array([12., 4.])

    @property
    def position(self):
        return self.sim.get_body_positions(self.fly.name)[self.thorax].copy()

    def observe(self):
        sensor_xy = self.sim.get_body_positions(self.fly.name)[self.antennae, :2]
        d = np.linalg.norm(sensor_xy - self.goal, axis=1)
        return (1 / (1 + (d / 5)**2)).astype(np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        options = options or {}
        self.goal = np.asarray(options.get("goal", [12., self.np_random.choice([-1, 1]) * self.np_random.uniform(3, 6)]), dtype=float)
        if self.goal.shape != (2,) or not np.isfinite(self.goal).all():
            raise ValueError("goal must be two finite coordinates in mm")
        self.sim.reset()
        self.sim.mj_model.geom_pos[self.goal_geom, :2] = self.goal
        self.controller.reset(seed=0 if seed is None else int(seed))
        apply_locomotion_action(self.sim, self.fly.name, LocomotionAction(
            joint_angles=self.steps_pattern.default_pose_by_dof_order(self.dofs),
            adhesion_onoff=np.ones(6, dtype=bool)))
        self.sim.warmup()
        self.elapsed = 0.0
        self.previous_distance = np.linalg.norm(self.position[:2] - self.goal)
        return self.observe(), {"goal_mm": self.goal.copy()}

    def step(self, action):
        a = np.asarray(action, dtype=float).reshape(-1)
        if a.shape != (1,) or not np.isfinite(a).all():
            raise ValueError("Action must contain one finite steering value")
        turn = float(np.clip(a[0], -1, 1))
        descending = np.array([.9 - .55 * turn, .9 + .55 * turn])
        for _ in range(self.substeps):
            feedback = HybridControllerObservation.from_sim(self.sim, self.fly.name)
            motor = self.controller.step(descending, feedback)
            apply_locomotion_action(self.sim, self.fly.name, motor)
            self.sim.step()
            if self.sim.renderer is not None:
                self.sim.render_as_needed()
        self.elapsed += self.control_dt
        pos = self.position
        if not np.isfinite(self.sim.mj_data.qpos).all():
            raise FloatingPointError("Non-finite physics state")
        distance = float(np.linalg.norm(pos[:2] - self.goal))
        success = distance < 1.5
        fallen = bool(pos[2] < .15 or pos[2] > 2.0)
        reward = (self.previous_distance - distance) - .005 + (5 if success else 0) - (5 if fallen else 0)
        self.previous_distance = distance
        return self.observe(), float(reward), bool(success or fallen), bool(self.elapsed >= self.episode_seconds), dict(
            distance_mm=distance, goal_mm=self.goal.copy(), position_mm=pos,
            success=success, fallen=fallen, steering=turn, time_s=self.elapsed,
        )

    def close(self):
        self.sim.close()


def teacher(odor):
    """Hand-designed steering labels for imitation; not a biological learning rule."""
    x = np.asarray(odor)
    return np.tanh(25 * (x[..., 0] - x[..., 1]) / (x[..., 0] + x[..., 1] + 1e-6))


def rollout(policy, *, seed=10, goal=(12, 4), seconds=3, video=None):
    env = OdorNavigationEnv(record=video is not None, episode_seconds=seconds)
    try:
        obs, _ = env.reset(seed=seed, options={"goal": goal})
        start = env.position.copy()
        trace = []
        for _ in range(round(seconds / env.control_dt)):
            turn = float(policy(obs))
            obs, reward, done, truncated, info = env.step([turn])
            trace.append({**info, "reward": reward, "odor": obs.copy()})
            if done or truncated:
                break
        if video:
            video = Path(video)
            env.sim.renderer.save_video({env.video_cameras[0]: video,
                                         env.video_cameras[1]: video.with_stem(video.stem + "-arena")})
        return dict(start_mm=start, goal_mm=np.asarray(goal), initial_distance_mm=float(np.linalg.norm(start[:2] - goal)),
                    final_distance_mm=info["distance_mm"], success=info["success"], fallen=info["fallen"], trace=trace)
    finally:
        env.close()


def live(policy, *, max_wall_seconds=600):
    import mujoco.viewer
    env = OdorNavigationEnv(episode_seconds=4)
    keys = {"pause": False, "reset": False}
    def key_callback(key):
        if key == 32:
            keys["pause"] = not keys["pause"]
        elif key in (82, 114):
            keys["reset"] = True
    obs, _ = env.reset(seed=10)
    deadline = time.monotonic() + max_wall_seconds
    try:
        with mujoco.viewer.launch_passive(env.sim.mj_model, env.sim.mj_data, key_callback=key_callback,
                                         show_left_ui=False, show_right_ui=False) as viewer:
            viewer.cam.distance = 13
            viewer.cam.azimuth = 125
            viewer.cam.elevation = -35
            print("Live MuJoCo: Space=pause, R=reset, close window=stop. Maximum 10 minutes.", flush=True)
            episode = 10
            while viewer.is_running() and time.monotonic() < deadline:
                if not keys["pause"]:
                    obs, _, done, truncated, _ = env.step([float(policy(obs))])
                    if done or truncated or keys["reset"]:
                        episode += 1
                        obs, _ = env.reset(seed=episode)
                        keys["reset"] = False
                else:
                    time.sleep(.02)
                with viewer.lock():
                    viewer.cam.lookat[:] = env.position
                viewer.sync()
    finally:
        env.close()


def json_default(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--policy", choices=["straight", "teacher", "trained", "untrained"], default="teacher")
    p.add_argument("--live", action="store_true")
    p.add_argument("--seconds", type=float, default=2)
    p.add_argument("--goal", nargs=2, type=float, default=[12, 4])
    args = p.parse_args()
    if not 0 < args.seconds <= 30:
        p.error("seconds must be in (0, 30]")
    if args.policy in ("trained", "untrained"):
        from odor_brain import load_policy
        policy = load_policy(args.policy)
    else:
        policy = teacher if args.policy == "teacher" else lambda obs: 0.
    if args.live:
        live(policy)
    else:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        result = rollout(policy, goal=args.goal, seconds=args.seconds, video=OUTPUT / f"{args.policy}.mp4")
        (OUTPUT / f"{args.policy}.json").write_text(json.dumps(result, default=json_default, indent=2) + "\n")
        print(json.dumps({k: v for k, v in result.items() if k != "trace"}, default=json_default), flush=True)


if __name__ == "__main__":
    main()
