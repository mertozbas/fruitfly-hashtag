"""Learned geometric motor readout through the strategy's anatomical core.

The nine-phase supervisor is engineered. All Cartesian targets pass through the
neural core and learned readout; fixed IK/servo bounds execute those targets.
Training labels are synthetic calibrated pick/place examples, not RL discovery.
"""
import json
from pathlib import Path
import numpy as np
from scipy.special import expit
from .scene import CELLS,SUPPLY

PHASES=('approach','lower','close','lift','transport','place','release','retreat','park')
PARK=np.array([.17,0,.13])
MEAN=np.tile([0.,-.18],3);SCALE=np.tile([.2,.18],3)


class Motor:
    def __init__(self,policy,path):
        self.policy=policy
        with np.load(path,allow_pickle=False) as s:
            self.encoder=s['motor_encoder'].copy();self.decoder=s['motor_decoder'].copy();self.bias=s['motor_bias'].copy()
        shapes=[(self.encoder,(15,policy.circuit.layers[0].shape[0])),(self.decoder,(9,policy.circuit.layers[2].shape[1],4)),(self.bias,(9,4))]
        if any(a.shape!=shape or not np.isfinite(a).all() for a,shape in shapes):raise ValueError('Invalid motor readout')

    def activity(self,coordinates,phase,silenced=False):
        coordinates=np.asarray(coordinates,float)
        if coordinates.shape!=(6,) or not np.isfinite(coordinates).all() or phase not in range(9):raise ValueError('Invalid motor observation')
        x=np.r_[(coordinates-MEAN)/SCALE,np.eye(9)[phase]]
        h=expit(x@self.encoder);layers=[h]
        if silenced:h=np.zeros_like(h);layers=[h]
        from .policy import RESPONSE_GAINS
        for w,total,gain in zip(self.policy.layers,self.policy.sums,RESPONSE_GAINS):
            h=expit(gain*(np.asarray(h@w).ravel()/total-.5))
            if silenced:h=np.zeros_like(h)
            layers.append(h)
        action=h@self.decoder[phase]+self.bias[phase]
        return action,layers,x


def fit(source,output,seed=52):
    """Fit only a motor readout; strategy weights and scores remain bit-identical."""
    import shutil
    from scipy.linalg import solve
    from .policy import Policy,RESPONSE_GAINS
    source,output=Path(source),Path(output)
    if (output/'trained.npz').exists():raise FileExistsError('Yeni bir çıktı dizini seç; mevcut model korunuyor.')
    output.mkdir(parents=True,exist_ok=True)
    for name in ('circuit.json','body_ids.npz','layer0.npz','layer1.npz','layer2.npz','training.json','evaluation.json','untrained.npz'):
        if (source/name).exists():shutil.copy2(source/name,output/name)
    p=Policy(source/'trained.npz');rng=np.random.default_rng(seed)
    encoder=rng.normal(0,.022,(15,p.circuit.layers[0].shape[0]))
    xyz=rng.uniform([- .18,-.29]*3,[.18,-.075]*3,(5000,6));fit=xyz[:4000];test=xyz[4000:]
    decoders=[];biases=[];errors=[]
    for phase in range(9):
        inputs=np.c_[(xyz-MEAN)/SCALE,np.tile(np.eye(9)[phase],(len(xyz),1))]
        h=expit(inputs@encoder)
        for w,total,gain in zip(p.layers,p.sums,RESPONSE_GAINS):h=expit(gain*(np.asarray(h@w)/total-.5))
        # Training-only teacher for configured block geometry and table height.
        xy=xyz[:,:2] if phase<2 else xyz[:,4:6] if phase<4 else xyz[:,2:4]
        target=np.c_[xy,np.full(len(xyz),[.075,.020,.020,.065,.065,.030,.030,.065,.13][phase]),
                     np.full(len(xyz),.9 if phase in (0,1,6,7,8) else .08)]
        if phase==8:target[:,:3]=PARK
        a=np.c_[h[:4000],np.ones(4000)];mean=a.mean(0);mean[-1]=0
        a=a-mean;penalty=np.eye(a.shape[1])*1e-9;penalty[-1,-1]=0
        coef=solve(a.T@a+penalty,a.T@target[:4000],assume_a='pos')
        bias=coef[-1]-mean@coef;decoder=coef[:-1]
        predicted=h[4000:]@decoder+bias
        errors.append(float(np.max(np.abs(predicted-target[4000:]))));decoders.append(decoder);biases.append(bias)
    with np.load(source/'trained.npz',allow_pickle=False) as s:state={k:s[k].copy() for k in s.files}
    state.update(motor_encoder=encoder.astype(np.float32),motor_decoder=np.array(decoders,dtype=np.float32),motor_bias=np.array(biases,dtype=np.float32))
    np.savez_compressed(output/'trained.npz',**state)
    report=dict(method='synthetic target supervision / ridge readout',seed=seed,training_geometries=4000,validation_geometries=1000,
        maximum_action_errors_by_phase=errors,shared_anatomical_weights_frozen=True,random_input_encoder=True,
        phase_supervisor='engineered nine-phase feedback with bounded retries',token_geometry='30 mm training blocks with X/O marks',
        scope='Independent geometric validation only. Contact physics must pass separately; original 8 mm printed X/O tokens are not validated.')
    (output/'motor-training.json').write_text(json.dumps(report,indent=2));return report


class Controller:
    """Bounded contact/perception supervisor; never sets the controlled token pose."""
    def __init__(self,env,eyes,motor,cell,silenced=False):
        env.begin_placement(cell);self.env=env;self.eyes=eyes;self.motor=motor;self.silenced=silenced
        eyes.last_position=None;eyes.last_seen=None
        for tracker in eyes.trackers.values():tracker.reset()
        self.phase=0;self.anchor=env.ee[:2].copy();self.position=np.r_[env.supply[env.used['X']][:2],.015]
        self.held_offset=None;self.dwell=0.;self.elapsed=0.;self.phase_elapsed=0.;self.attempt=1;self.done=False;self.success=False
        self.error=None;self.outcome='running';self.last_action=None;self.layers=None;self.inputs=None;self.measurement=None;self.lifted=False
        self.verification=None;self.settled=0.;self.action_applied=False
    def retry(self,reason):
        if self.attempt>=3:
            self.done=True;self.error=reason;self.outcome='retry_exhausted';return
        self.attempt+=1;self.phase=0;self.phase_elapsed=0.;self.dwell=0.;self.held_offset=None;self.lifted=False;self.settled=0.
    def step(self):
        e=self.env;dt=.05
        self.action_applied=False
        if self.done:return
        self.elapsed+=dt;self.phase_elapsed+=dt
        if self.elapsed>60:
            self.done=True;self.error='60 saniye sınırı';self.outcome='timeout';return
        contacts=set(e.contacts());holding={'gripper','moving_jaw_so101_v1'}<=contacts
        if holding and self.held_offset is not None:prior=e.ee+self.held_offset
        else:prior=self.position
        self.eyes.capture()
        # Completion is a settled, camera-confirmed placement with the arm clear.
        # Reaching an arbitrary park coordinate is not part of the game task.
        # Physics state is used only by this independent outcome/safety check.
        if self.phase>=7:
            from .rules import play
            check=self.eyes.board();expected=play(e.board,e.target_cell,1)
            true_inside=np.linalg.norm(e.cube[:2]-CELLS[e.target_cell][:2])<.018 and e.cube[2]<.020
            joint=e.model.body_jntadr[e.cube_id];dof=e.model.jnt_dofadr[joint]
            still=np.linalg.norm(e.data.qvel[dof:dof+3])<.03
            clear=np.linalg.norm(e.ee-e.cube)>.060 and e.data.qpos[e.qadr[5]]>.78 and not holding
            confirmed=check['valid'] and tuple(check['board'])==expected and true_inside and still and clear and self.lifted
            self.settled=self.settled+dt if confirmed else 0.
            self.verification=dict(observed=check,expected=list(expected),true_inside=bool(true_inside),
                                   lifted=self.lifted,arm_clear=bool(clear),settled_s=self.settled)
            if self.settled>=.35:
                e.complete_placement(check['board']);self.done=self.success=True;self.outcome='success';return
        measurement=self.eyes.token(prior,holding)
        self.measurement=measurement
        if not measurement['valid']:
            age=measurement['age_s']
            if holding and self.held_offset is not None and age is not None and age<=5:
                measurement=dict(measurement,position=prior,valid=True,prediction='contact-conditioned joint encoders')
            elif self.phase>=6 and self.phase_elapsed<8 and age is not None and age<=8:
                measurement=dict(measurement,position=self.position,valid=True,prediction='last sighting while clearing camera view')
            else:
                self.done=True;self.error='Taş kamera izini kaybetti';self.outcome='sensor_stale';return
        self.measurement=measurement
        self.position=measurement['position']
        if holding:
            if self.held_offset is None:self.held_offset=self.position-e.ee
        else:self.held_offset=None
        phase=self.phase;goal=CELLS[e.target_cell][:2]
        # A cell has 35 mm free half-width and the block 15 mm half-width.
        # Allow bounded IK error here; final camera/physics checks require <18 mm.
        distance=np.linalg.norm(e.ee[:2]-self.position[:2]);at_goal=np.linalg.norm(e.ee[:2]-goal)<.008
        self.dwell=self.dwell+dt if holding else 0.
        opened=e.data.qpos[e.qadr[5]]>.78
        if phase==0 and distance<.012 and abs(e.ee[2]-.075)<.005 and opened:self.phase=1
        elif phase==1 and distance<.003 and e.ee[2]<.023:self.phase=2;self.anchor=e.ee[:2].copy()
        elif phase==2 and self.dwell>.35:self.phase=3
        elif phase==3 and holding and e.ee[2]>.060:self.phase=4;self.lifted=True
        elif phase==4 and at_goal and holding:self.phase=5
        elif phase==5 and at_goal and e.ee[2]<.033:self.phase=6
        elif phase==6 and opened and not holding:self.phase=7
        elif phase==7 and e.ee[2]>.060:self.phase=8
        elif phase==8 and np.linalg.norm(e.ee-PARK)<.01 and self.phase_elapsed>5:
            self.retry('Yerleştirme kamera ile doğrulanamadı')
        if self.phase!=phase:self.phase_elapsed=0.
        if self.phase in (3,4,5) and not holding and self.phase_elapsed>.25:self.retry('Taş düştü')
        if self.phase_elapsed>12:self.retry('Hareket ilerlemiyor')
        if self.done:return
        coordinates=np.r_[self.position[:2],goal,self.anchor]
        action,layers,inputs=self.motor.activity(coordinates,self.phase,self.silenced)
        self.last_action=action;self.layers=layers;self.inputs=inputs
        self.coordinates=coordinates.copy();self.applied_phase=self.phase
        self.action_frame_id=self.eyes.frame_id;self.action_sample_time=measurement['sample_time_s']
        self.action_images={k:self.eyes.images[k] for k in ('top','wrist')}
        if not np.isfinite(action).all() or np.any(action[:3]<[-.22,-.33,.015]) or np.any(action[:3]>[.23,.06,.16]) or not -.17<=action[3]<=1.1:
            self.done=True;self.error='Ağ komutu çalışma sınırında değil';self.outcome='unsafe';return
        desired=e.ee+np.clip((action[:3]-e.ee)*.3,-.003,.003)
        # With the token released, solve the network's observation target from
        # the calibrated elbow branch. The same servo/contact bounds still apply.
        q=e.ik(action[:3],q=e.observation_joints,iterations=60) if self.phase==8 else e.ik(desired,iterations=14)
        q[5]=float(action[3]);e.step_joints(q)
        self.action_applied=True
        unsafe=bool(e.data.warning.number.sum() or not np.isfinite(e.data.qpos).all() or e.cube[2]<-.005)
        for contact in e.data.contact:
            bodies={int(e.model.geom_bodyid[g]) for g in (contact.geom1,contact.geom2)}
            if (0 in bodies or e.model.body('game_board').id in bodies) and any(1<b<e.token_ids['X'][0] for b in bodies) and contact.dist<-.001:unsafe=True
        if unsafe:self.done=True;self.error='Fizik / çarpışma sınırı';self.outcome='unsafe'


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);p.add_argument('--seed',type=int,default=52)
    a=p.parse_args();print(json.dumps(fit(a.source,a.output,a.seed),indent=2))
