"""Task observations, bounded actions and independent physical success checks."""
from dataclasses import dataclass
import numpy as np
from .engine import ArmEnv, CONTROL_DT

OBSERVATION_NAMES = [
    *[f"joint_{i}_position" for i in range(1,7)],
    *[f"joint_{i}_velocity" for i in range(1,7)],
    "tcp_x","tcp_y","tcp_z", "cube_minus_tcp_x","cube_minus_tcp_y","cube_minus_tcp_z",
    "goal_minus_cube_x","goal_minus_cube_y","goal_minus_cube_z", "cube_height",
    "bilateral_contact","lifted_once","inside_bin","contact_dwell",
    "last_dx","last_dy","last_dz","last_gripper",
]
OBS_SIZE=len(OBSERVATION_NAMES)
MAX_DELTA=.003


class PickPlaceEnv(ArmEnv):
    step_limit=600
    def reset(self,seed=0,cube=None,goal=None):
        rng=np.random.default_rng(seed)
        if cube is None:
            cube=[rng.uniform(-.012,.037),rng.uniform(-.226,-.186),.015]
        if goal is None:
            goal=[rng.uniform(.125,.16),rng.uniform(-.18,-.135),0]
        super().reset(seed,cube,goal)
        self.initial_cube=self.cube
        self.last_action=np.zeros(4,dtype=np.float32)
        self.lifted=False
        self.reached=False
        self.geometric_reached=False
        self.grasped=False
        self.released=False
        self.contact_dwell=0.
        self.settle_dwell=0.
        self.total_reward=0.
        self.max_height=float(self.cube[2])
        self.best_transport_distance=float(np.linalg.norm(self.cube[:2]-self.goal[:2]))
        self.unsafe=False
        self.success=False
        self.outcome="running"
        self.reward_components={}
        self._rewarded=set()
        return self.observation()

    def sensors(self):
        contacts=set(self.contacts())
        holding={"gripper","moving_jaw_so101_v1"}<=contacts
        cube=self.cube
        # Whole cube footprint must fit in the actual 71.2 mm cavity. The
        # projected half extents account for rotation, including tilted cubes.
        rotation=self.data.xmat[self.cube_id].reshape(3,3)
        extents=.015*np.abs(rotation).sum(axis=1)
        inside=bool(np.all(np.abs(cube[:2]-self.goal[:2])+extents[:2]<.0356))
        return holding,inside,contacts

    def observation(self):
        holding,inside,_=self.sensors()
        q=self.data.qpos[self.qadr]
        qvel=self.data.qvel[self.dadr]
        return np.asarray([
            *(q/np.array([2,2,2,2,3,1])), *np.clip(qvel,-2,2),
            *((self.ee-[.06,-.18,.06])/.15), *((self.cube-self.ee)/.15),
            *((self.goal-self.cube)/.15), self.cube[2]/.15,
            float(holding),float(self.lifted),float(inside), min(self.contact_dwell/.5,1),
            *self.last_action,
        ],dtype=np.float32)

    def step(self,action,action_mode='delta'):
        action=np.asarray(action,dtype=np.float64)
        if action.shape!=(4,) or not np.isfinite(action).all():
            raise ValueError("SO-101 action requires four finite values")
        action=action.clip(-1,1)
        if action_mode not in {'delta','target'}:raise ValueError('Invalid robot action mode')
        before_cube=self.cube
        previous_max_height=self.max_height
        before_distance=np.linalg.norm(self.ee-self.cube)
        if action_mode=='target':
            from .policy import TARGET_CENTER,TARGET_SCALE
            desired=TARGET_CENTER+TARGET_SCALE*action[:3]
            delta=np.clip((desired-self.ee)*.3,-MAX_DELTA,MAX_DELTA)
        else:delta=action[:3]*MAX_DELTA
        target=np.clip(self.ee+delta,[-.04,-.26,.020],[.19,-.105,.135])
        q=self.ik(target,iterations=12)
        q[5]=.08+(action[3]+1)*.41
        self.step_joints(q)
        self.last_action=action.astype(np.float32)
        holding,inside,contacts=self.sensors()
        self.contact_dwell=self.contact_dwell+CONTROL_DT if holding else 0.
        self.geometric_reached |= bool(np.linalg.norm(self.ee[:2]-self.cube[:2])<.004 and self.ee[2]<.024)
        self.grasped |= self.contact_dwell>=.2
        # A maintained bilateral grasp is stronger reach evidence than the
        # approximate fixed TCP's 24 mm height threshold (e.g. corner contact).
        # Keep the original geometric metric separately for comparison.
        self.reached=self.geometric_reached or self.grasped
        self.lifted |= bool(holding and self.cube[2]>.07)
        self.max_height=max(self.max_height,float(self.cube[2]))
        self.released |= bool(self.lifted and inside and "bin" in contacts and not holding)
        settled=bool(self.released and inside and "bin" in contacts and not holding
                     and np.linalg.norm(self.data.qvel[6:])<.03
                     and np.linalg.norm(self.ee-self.cube)>.065)
        self.settle_dwell=self.settle_dwell+CONTROL_DT if settled else 0.
        self.unsafe |= bool(self.data.warning.number.sum()>0 or not np.isfinite(self.data.qpos).all()
                            or self.cube[2]<-.005 or np.linalg.norm(self.cube[:2])>.45
                            or np.any(self.ee<[-.07,-.29,0]) or np.any(self.ee>[.22,-.075,.165]))
        # Forbidden robot/table or robot/bin contacts, excluding the fixed base.
        for c in self.data.contact:
            bodies={int(self.model.geom_bodyid[g]) for g in (c.geom1,c.geom2)}
            if (0 in bodies or self.bin_id in bodies) and any(1<b<self.cube_id for b in bodies):
                if c.dist<-.0005:
                    self.unsafe=True
        self.success=bool(self.settle_dwell>=.5 and not self.unsafe)
        self.outcome="unsafe" if self.unsafe else "success" if self.success else "timeout" if self.steps>=self.step_limit else "running"
        parts={"time":-.002,"motion":-.001*float(np.square(delta/MAX_DELTA).sum())}
        if not self.grasped:
            parts["approach"]=float((before_distance-np.linalg.norm(self.ee-self.cube))*5)
        if holding:
            parts["lift_progress"]=float(max(0,min(self.cube[2],.10)-min(previous_max_height,.10))*10)
            distance=float(np.linalg.norm(self.cube[:2]-self.goal[:2]))
            parts["transport_progress"]=max(0,self.best_transport_distance-distance)*5
            self.best_transport_distance=min(self.best_transport_distance,distance)
        for key,condition,value in [("grasp",self.grasped,1.),("lift",self.lifted,2.),("release",self.released,2.),("success",self.success,10.),("unsafe",self.unsafe,-10.)]:
            if condition and key not in self._rewarded:
                parts[key]=value
                self._rewarded.add(key)
        self.reward_components=parts
        reward=sum(parts.values())
        self.total_reward+=reward
        return self.observation(),reward,self.outcome!="running",self.metrics()

    def metrics(self):
        holding,inside,contacts=self.sensors()
        return dict(seed=self.seed,steps=self.steps,success=self.success,outcome=self.outcome,
            reached=self.reached,geometric_reached=self.geometric_reached,grasped=self.grasped,lifted=self.lifted,released=self.released,
            max_height_m=self.max_height,reward=self.total_reward,unsafe=self.unsafe,
            cube=self.cube.tolist(),goal=self.goal.tolist(),tcp=self.ee.tolist(),
            holding=holding,inside_bin=inside,contacts=list(contacts),
            final_distance_mm=float(np.linalg.norm(self.cube[:2]-self.goal[:2])*1000),
            physics_warnings=int(self.data.warning.number.sum()))


class Demonstrator:
    """A feedback teacher for data collection ONLY; never used by learned rollout."""
    def __init__(self):
        self.phase="approach"
        self.anchor=None

    def __call__(self,env):
        cube,ee,goal=env.cube,env.ee,env.goal
        holding,inside,contacts=env.sensors()
        # DAgger can enter after a learner has already grasped above the
        # teacher's nominal approach height. Synchronise from achieved physical
        # progress; otherwise stale `lower` labels would open a lifted cube.
        if holding and env.grasped and self.phase in {'approach','lower'}:
            self.phase='close';self.anchor=ee.copy()
        if holding and env.lifted and self.phase in {'approach','lower','close'}:
            self.phase='lift';self.anchor=ee.copy()
        if env.released and inside and self.phase in {'lift','transport','place'}:
            self.phase='release'
        if self.phase=="approach" and np.linalg.norm(ee[:2]-cube[:2])<.002 and ee[2]<.083:
            self.phase="lower"
        if self.phase=="lower" and np.linalg.norm(ee[:2]-cube[:2])<.003 and ee[2]<.022:
            self.phase="close"
            self.anchor=ee.copy()
        if self.phase=="close" and env.contact_dwell>=.35:
            self.phase="lift"
        if self.phase=="lift" and ee[2]>.106:
            self.phase="transport"
        if self.phase=="transport" and np.linalg.norm(ee[:2]-goal[:2])<.0025:
            self.phase="place"
        if self.phase=="place" and ee[2]<.045:
            self.phase="release"
        if self.phase=="release" and env.data.qpos[env.qadr[5]]>.75 and inside and "bin" in contacts:
            self.phase="retreat"
        phase=self.phase
        target=({"approach":cube+[0,0,.065],"lower":cube+[0,0,.005],
                 "close":self.anchor,"lift":np.r_[self.anchor[:2] if self.anchor is not None else cube[:2],.11],
                 "transport":np.r_[goal[:2],.11],"place":np.r_[goal[:2],.043],
                 "release":np.r_[goal[:2],.043],"retreat":np.r_[goal[:2],.115]})[phase]
        grip=1. if phase in {"approach","lower","release","retreat"} else -1.
        self.target=target.copy()
        return np.r_[np.clip((target-ee)*.3/MAX_DELTA,-1,1),grip].astype(np.float32)
