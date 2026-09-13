"""MaleCNS odor readout -> bounded heading reference -> FlyBody wing policy.

Only references are written online. The simulated fly's qpos/qvel are never
overwritten after reset. No target-direction controller bypasses the brain.
"""
import hashlib
import sys
from pathlib import Path
import numpy as np
from dm_control import composer
from dm_control.locomotion.arenas import floors
from flybody.fruitfly import fruitfly
from flybody.tasks.flight_imitation import FlightImitationWBPG
from flybody.tasks.pattern_generators import WingBeatPatternGenerator
from flybody.tasks.trajectory_loaders import InferenceFlightTrajectoryLoader
from flybody.tasks.synthetic_trajectories import constant_speed_trajectory
from flybody.tasks.task_utils import com2root
from engine import Flight, ROOT, ASSETS, tf

sys.path.insert(0, str(ROOT))
from odor_policy import Policy

class BrainFlight(Flight):
    def __init__(self, model_path, *, seconds=.45, speed_cm_s=10., yaw_gain=60.):
        self.policy = tf.saved_model.load(str(ASSETS / 'trained-fly-policies/flight'))
        self.random = np.random.RandomState(10)
        self.seconds, self.speed, self.yaw_gain = seconds, speed_cm_s, yaw_gain
        self.brain_dt = .01
        loader = InferenceFlightTrajectoryLoader()
        n = int(seconds/.0002)+20
        self.base_qpos, self.base_qvel = constant_speed_trajectory(n, speed=self.speed,
            init_pos=(0,0,1), body_rot_angle_y=-47.5, control_timestep=.0002)
        loader.set_next_trajectory(self.base_qpos, self.base_qvel)
        task = FlightImitationWBPG(walker=fruitfly.FruitFly, arena=floors.Floor(),
            wbpg=WingBeatPatternGenerator(base_pattern_path=str(ASSETS / 'datasets_flight-imitation/wing_pattern_fmech.npy')),
            traj_generator=loader, time_limit=seconds, initialize_qvel=True,
            force_actuators=False, disable_legs=True, joint_filter=0., future_steps=5,
            terminal_com_dist=2., trajectory_sites=False)
        self.target_site = task.root_entity.mjcf_model.worldbody.add('site', name='odor_target',
            type='sphere', size=(.075,), rgba=(.3,.95,.8,.8), group=2, pos=(2.5,.8,1.))
        self.env = composer.Environment(task=task, time_limit=seconds, random_state=self.random,
                                       strip_singleton_obs_buffer_dim=True)
        self.spec, self.control_dt = self.env.action_spec(), self.env.control_timestep()
        self.action = np.zeros(self.spec.shape)
        self.load_brain(model_path)

    def load_brain(self, path):
        self.brain = Policy(Path(path))
        self.brain_sha = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        # Trim the readout's learned neutral bias; equal antennal input must
        # request straight flight. This calibration never uses target bearing.
        self.neutral_turn = self.brain.activity([.1,.1])[0]

    def reset(self, seed=10, goal=(25.,8.), ablation='connected'):
        if ablation not in ['connected', 'zero', 'reverse']:
            raise ValueError('Unknown brain intervention')
        self.goal = np.asarray(goal, dtype=float)
        if self.goal.shape != (2,) or not np.isfinite(self.goal).all() or (np.abs(self.goal)>30).any():
            raise ValueError('Expected finite target XY in mm')
        self.ablation = ablation
        self.random.seed(seed)
        self.target_site.pos = np.r_[self.goal/10,1.]
        self.env.task._traj_generator.set_next_trajectory(self.base_qpos, self.base_qvel.copy())
        self.ts = self.env.reset()
        self.trajectory = -1
        self.ref_position = self.base_qpos[0,:3].copy()
        self.heading = 0.
        self.step_count = 0
        self.brain_sample_time = 0.
        self.yaw_rate = 0.
        self.success = False
        self._sample_brain()
        self._reference()
        # reset() produced its observation before the new online reference.
        self._refresh_reference_observation()
        return self.ts

    def observe(self):
        physics = self.env.physics
        sensors = np.stack([physics.named.data.xpos['walker/antenna_'+side] for side in ['left','right']]) * 10
        self.sensor_positions = sensors.copy()
        target = np.r_[self.goal, 10.]
        distance = np.linalg.norm(sensors-target,axis=1)
        return (1/(1+(distance/5)**2)).astype(np.float32)

    def _sample_brain(self):
        self.odor = self.observe()
        self.turn, self.layers = self.brain.activity(self.odor)
        calibrated = float(np.clip(self.turn-self.neutral_turn,-1,1))
        self.applied_turn = 0. if self.ablation=='zero' else -calibrated if self.ablation=='reverse' else calibrated
        self.yaw_rate = float(np.clip(self.yaw_gain*self.applied_turn, -8., 8.))
        self.brain_sample_time = float(self.env.physics.time())

    def _reference(self):
        task = self.env.task
        start = self.step_count
        end = min(start+int(self.brain_dt/self.control_dt)+task._future_steps+2, len(task._ref_qpos))
        dt = np.arange(end-start)*self.control_dt
        theta = self.heading+self.yaw_rate*dt
        velocity = self.speed*np.stack([np.cos(theta),np.sin(theta),np.zeros_like(theta)],axis=1)
        positions = np.repeat(self.ref_position[None], len(dt), axis=0)
        if len(dt)>1:positions[1:]+=np.cumsum(velocity[:-1]*self.control_dt,axis=0)
        # Z-yaw composed with the original body pitch quaternion.
        pitch = self.base_qpos[0,3:]
        c,s=np.cos(theta/2),np.sin(theta/2)
        quat=np.stack([c*pitch[0],-s*pitch[2],c*pitch[2],s*pitch[0]],axis=1)
        task._ref_qpos[start:end,:3]=com2root(positions,quat)
        task._ref_qpos[start:end,3:]=quat
        task._ref_qvel[start:end,:3]=velocity
        task._ref_qvel[start:end,3:]=[0,0,self.yaw_rate]

    def _refresh_reference_observation(self):
        # Read the exact task observables, not a manufactured motor action.
        obs=dict(self.ts.observation)
        for key in ['walker/ref_displacement','walker/ref_root_quat']:
            obs[key]=np.asarray(self.env.task.observables[key](self.env.physics))
        self.ts=self.ts._replace(observation=obs)

    def step(self):
        if self.success or self.ts.last():
            raise RuntimeError('Reset the completed flight episode before stepping')
        if self.step_count % round(self.brain_dt/self.control_dt)==0:
            self._sample_brain()
            self._reference()
            self._refresh_reference_observation()
        super().step()
        self.ref_position[:2] += self.speed*np.array([np.cos(self.heading),np.sin(self.heading)])*self.control_dt
        self.heading += self.yaw_rate*self.control_dt
        self.step_count += 1
        distance = np.linalg.norm(self.env.physics.named.data.subtree_com['walker/'][:2]*10-self.goal)
        self.success = bool(distance<2. and self.env.physics.named.data.subtree_com['walker/'][2]>.2
                            and not (self.ts.last() and self.ts.discount==0))
        return self.ts

    def telemetry(self):
        t=super().telemetry()
        t.update(goal_mm=self.goal.tolist(),distance_mm=float(np.linalg.norm(np.array(t['position_mm'])[:2]-self.goal)),
                 success=self.success,done=self.success or t['done'],
                 odor=self.odor.tolist(),steering=self.turn,yaw_rate_rad_s=self.yaw_rate,
                 brain_sample_time_s=self.brain_sample_time,applied_steering=self.applied_turn,
                 neutral_steering=self.neutral_turn,brain_step=self.step_count,
                 desired_heading_rad=self.heading,reference_position_mm=(self.ref_position*10).tolist())
        return t
