"""Official FlyBody SavedModel inference; CGS physics, millimetre telemetry."""
import os
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
from pathlib import Path
import numpy as np
import tensorflow as tf
tf.config.threading.set_inter_op_parallelism_threads(1)
tf.config.threading.set_intra_op_parallelism_threads(1)
import tensorflow_probability as tfp  # Registers SavedModel distribution types.
from tensorflow.python.framework import type_spec_registry
# The published model uses TFP 0.16's pre-rename Independent TypeSpec name.
# Alias its compatible decoder; the downloaded graph and weights stay intact.
tfp.distributions.Independent
@type_spec_registry.register('tensorflow_probability.python.distributions.independent.Independent_ACTTypeSpec')
class LegacyIndependentSpec(type_spec_registry.lookup('tfp.distributions.Independent_ACTTypeSpec')):
    pass
from flybody.fly_envs import flight_imitation
from flybody.tasks.task_utils import root2com

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "data/flybody"

class Flight:
    def __init__(self, seed=10):
        self.policy = tf.saved_model.load(str(ASSETS / "trained-fly-policies/flight"))
        self.random = np.random.RandomState(seed)
        self.env = flight_imitation(
            ref_path=str(ASSETS / "datasets_flight-imitation/flight-dataset_saccade-evasion_augmented.hdf5"),
            wpg_pattern_path=str(ASSETS / "datasets_flight-imitation/wing_pattern_fmech.npy"),
            randomize_start_step=False, random_state=self.random)
        self.spec = self.env.action_spec()
        self.control_dt = self.env.control_timestep()
        self.action = np.zeros(self.spec.shape)

    def reset(self, seed=10, trajectory=None):
        self.random.seed(seed)
        self.trajectory = seed % self.env.task._traj_generator.num_trajectories if trajectory is None else trajectory
        self.env.task.set_next_trajectory_index(self.trajectory)
        self.ts = self.env.reset()
        return self.ts

    def step(self):
        obs = tf.nest.map_structure(lambda x: tf.convert_to_tensor(x[None], dtype=tf.float32), self.ts.observation)
        canonical = self.policy(obs).mean()[0].numpy()
        if canonical.shape != self.spec.shape or not np.isfinite(canonical).all():
            raise ValueError("Invalid flight policy action")
        # Acme CanonicalSpecWrapper: clip [-1, 1], map to native actuator bounds.
        self.action = self.spec.minimum + (np.clip(canonical, -1, 1) + 1) * .5 * (self.spec.maximum - self.spec.minimum)
        self.ts = self.env.step(self.action.copy())  # Task adds the wing pattern in place.
        return self.ts

    def telemetry(self):
        env, task = self.env, self.env.task
        com = env.physics.named.data.subtree_com['walker/'].copy()
        ghost_pos, ghost_quat = task._ghost.get_pose(env.physics)
        ref = root2com(np.concatenate((ghost_pos, ghost_quat)))
        velocity = task._walker.get_velocity(env.physics)[0]
        return dict(time_s=float(env.physics.time()), position_mm=(com * 10).tolist(),
                    altitude_mm=float(com[2] * 10), speed_mm_s=float(np.linalg.norm(velocity) * 10),
                    tracking_error_mm=float(np.linalg.norm(ref - com) * 10),
                    wing_hz=float(task._wbpg.beat_freqs[task._wbpg._freq_idx]),
                    wing_angles=env.physics.bind(task._wing_joints).qpos.tolist(),
                    reward=float(self.ts.reward or 0), trajectory_id=int(self.trajectory),
                    done=bool(self.ts.last()), success=bool(self.ts.last() and self.ts.discount == 1),
                    physics_dt=float(env.physics.model.opt.timestep))
