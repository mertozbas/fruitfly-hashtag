"""Portable connectome policy: every internal edge has a MaleCNS body-ID pair.

Robot observations are an artificial input adapter, not biological touch signals.
Independent sigmoid neuron responses and the motor decoder are engineered. There
is no global activity normalization or connection bypass around the sparse core.
"""
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np
from scipy.special import expit
from scipy import sparse
from odor_policy import Circuit

OBS_SIZE=30
PHASES=('approach','lower','close','lift','transport','place','release','retreat')
MEMORY_SIZE=len(PHASES)
RESPONSE_GAINS=(12.,16.,16.)
TARGET_CENTER=np.array([.075,-.1825,.08],dtype=np.float32)
TARGET_SCALE=np.array([.125,.0875,.08],dtype=np.float32)

def task_feature_mask(size):
    """Explicit artificial sensor adapter: geometry, gripper and tactile state.

    Arm angles/velocities and previous commands are still recorded but excluded
    here to discourage trajectory shortcuts. This does not prescribe actions.
    """
    mask=np.ones(size,dtype=np.float32)
    mask[:5]=0;mask[6:12]=0;mask[26:30]=0
    return mask


def prepare(directory):
    from task_circuit import circuit_directory,build
    source=build("terrain")
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    for name in ("body_ids.npz","layer0.npz","layer1.npz","layer2.npz"):
        shutil.copy2(source/name,directory/name)
    metadata=json.loads((source/"circuit.json").read_text())
    metadata.update(task="so101",input_encoding="robot_observation_v1",
        sensor_adapter="30 normalized robot/task features -> learned sigmoid encoder; artificial remapping to Touch neuron IDs",
        motor_adapter="four learned continuous outputs -> bounded TCP delta XYZ and gripper -> five-axis IK and position servos",
        response_gains=list(RESPONSE_GAINS),
        scope="MaleCNS Touch/VNC/Motor anatomical subgraph repurposed for SO-101. Engineered sigmoid responses, encoder and motor decoder; not a biological arm-control circuit or whole-brain emulation.")
    (directory/"circuit.json").write_text(json.dumps(metadata,indent=2)+"\n")
    return Circuit(directory)


class Policy:
    def __init__(self,path):
        path=Path(path)
        self.circuit=Circuit(path.parent)
        if self.circuit.metadata.get("task")!="so101":
            raise ValueError("Expected a SO-101 circuit manifest")
        self.task="so101"
        with np.load(path,allow_pickle=False) as s:
            if str(s["circuit_identity"])!=self.circuit.identity or str(s["task"])!="so101":
                raise ValueError("SO-101 checkpoint/circuit mismatch")
            for k in ("encoder","encoder_bias","input_mean","input_scale","weight","decoder","bias"):
                setattr(self,k,s[k].copy())
            self.all_core='weight0' in s
            self.action_mode=str(s['action_mode']) if 'action_mode' in s else 'delta'
            if self.action_mode not in {'delta','target'}:raise ValueError('Invalid robot action mode')
            self.input_mask=s['input_mask'].copy() if 'input_mask' in s else np.ones(len(self.input_mean),np.float32)
            self.early_weights=[s[f'weight{i}'].copy() for i in range(2)] if self.all_core else []
            self.has_memory='memory_weight' in s
            self.motor_heads=int(s['motor_heads']) if 'motor_heads' in s else 1
            self.progress_supervision=bool(s['progress_supervision']) if 'progress_supervision' in s else False
            self.motor_phase_feedback=bool(s['motor_phase_feedback']) if 'motor_phase_feedback' in s else False
            if self.motor_heads not in (1,MEMORY_SIZE) or (self.motor_heads>1 and not self.has_memory):
                raise ValueError('Invalid learned motor-head schema')
            if (self.progress_supervision or self.motor_phase_feedback) and (self.motor_heads!=MEMORY_SIZE or self.action_mode!='target'):
                raise ValueError('Task supervision requires eight learned target heads')
            if self.has_memory:
                self.memory_weight=s['memory_weight'].copy();self.memory_bias=s['memory_bias'].copy()
                self.transition_counts=s['transition_counts'].copy() if 'transition_counts' in s else np.zeros((MEMORY_SIZE,MEMORY_SIZE))
                self.start_counts=s['start_counts'].copy() if 'start_counts' in s else np.zeros(MEMORY_SIZE)
        self.input_size=OBS_SIZE+(MEMORY_SIZE if self.has_memory else 0)
        n0=self.circuit.layers[0].shape[0]
        base=self.circuit.layers[2].toarray()
        shapes={"encoder":(self.input_size,n0),"encoder_bias":(n0,),"input_mean":(self.input_size,),
                "input_mask":(self.input_size,),
                "input_scale":(self.input_size,),"weight":base.shape,"decoder":(base.shape[1],4*self.motor_heads),"bias":(4*self.motor_heads,)}
        if self.has_memory:shapes.update(memory_weight=(base.shape[1],MEMORY_SIZE),memory_bias=(MEMORY_SIZE,),transition_counts=(MEMORY_SIZE,MEMORY_SIZE),start_counts=(MEMORY_SIZE,))
        for key,shape in shapes.items():
            v=getattr(self,key)
            if v.shape!=shape or not np.isfinite(v).all():
                raise ValueError("Invalid SO-101 parameter: "+key)
        if np.any(self.input_scale<=0) or np.any(self.weight[base==0]!=0):
            raise ValueError("Invalid scaling or connection outside anatomical mask")
        if not np.isin(self.input_mask,[0,1]).all():raise ValueError('Invalid input feature mask')
        if self.has_memory and (np.any(self.transition_counts<0) or np.any(self.start_counts<0)):
            raise ValueError('Invalid learned transition counts')
        self.has_transition_graph=self.has_memory and bool(np.any(self.transition_counts))
        ratios=self.weight[base!=0]/base[base!=0]
        if (ratios<np.exp(-1.5)-1e-5).any() or (ratios>np.exp(1.5)+1e-5).any():
            raise ValueError("Anatomical gain bounds exceeded")
        for i,weight in enumerate(self.early_weights):
            original=self.circuit.layers[i].toarray();mask=original!=0
            if weight.shape!=original.shape or not np.isfinite(weight).all() or np.any(weight[~mask]!=0):
                raise ValueError('Invalid early anatomical weight')
            ratios=weight[mask]/original[mask]
            if (ratios<np.exp(-1.5)-1e-5).any() or (ratios>np.exp(1.5)+1e-5).any():
                raise ValueError('Early anatomical gain bounds exceeded')
        self.last=sparse.csr_matrix(self.weight)
        self.layers=[*[sparse.csr_matrix(w) for w in self.early_weights],self.last] if self.all_core else [*self.circuit.layers[:2],self.last]
        self.input_sums=[np.asarray(w.sum(axis=0)).ravel() for w in self.layers]
        self.reset()

    def reset(self):
        initial=int(np.argmax(self.start_counts)) if self.has_memory else 0
        self.memory=np.eye(MEMORY_SIZE,dtype=np.float32)[initial]
        self.last_memory=self.memory.copy()

    def augmented(self,observation):
        x=np.asarray(observation,dtype=np.float32)
        if self.has_memory and x.shape==(OBS_SIZE,):x=np.r_[x,self.memory]
        if x.shape!=(self.input_size,) or not np.isfinite(x).all():
            raise ValueError(f'Expected {OBS_SIZE} finite external robot observations')
        return x

    def core_activity(self,x,silenced=False):
        x=np.clip((x-self.input_mean)/self.input_scale,-6,6)*self.input_mask
        h=expit(x@self.encoder+self.encoder_bias)
        if silenced:h=np.zeros_like(h)
        layers=[h]
        for w,gain,total in zip(self.layers,RESPONSE_GAINS,self.input_sums):
            # Weight-sum normalization is constant per target neuron, so it
            # neither adds activity-dependent cross-neuron links nor a bypass.
            h=expit(gain*((w.T@h)/np.maximum(total,1e-8)-.5))
            if silenced:h=np.zeros_like(h)
            layers.append(h)
        return layers

    def activity(self,observation,advance=False,silenced=False):
        x=self.augmented(observation)
        if self.has_memory:self.last_memory=x[OBS_SIZE:].copy()
        layers=self.core_activity(x,silenced)
        logits=self.phase_logits(layers[-1],self.last_memory) if self.has_memory else np.zeros(MEMORY_SIZE)
        if self.progress_supervision:
            from .phase_supervision import feasible_phases
            logits=np.where(feasible_phases(x),logits,-1e9)
        phase=int(np.argmax(logits))
        if self.motor_phase_feedback:
            # The selected skill is fed through the SAME anatomical circuit.
            # Display/replay the motor pass, whose activity actually yields the
            # applied action. No geometry bypass around the circuit is added.
            motor_x=np.r_[x[:OBS_SIZE],np.eye(MEMORY_SIZE,dtype=np.float32)[phase]]
            layers=self.core_activity(motor_x,silenced)
        h=layers[-1]
        action=np.tanh(self.motor_logits(h,phase))
        if self.has_memory and advance:
            self.memory=np.eye(MEMORY_SIZE,dtype=np.float32)[phase]
        return action.astype(np.float32),layers

    def motor_logits(self,h,phase=0):
        logits=(h@self.decoder+self.bias).reshape(self.motor_heads,4)
        return logits[phase if self.motor_heads>1 else 0]

    def phase_logits(self,h,memory):
        logits=h@self.memory_weight+self.memory_bias
        allowed=self.transition_counts[int(np.argmax(memory))]>0
        return np.where(allowed,logits,-1e9) if allowed.any() else logits

    def __call__(self,observation):
        return self.activity(observation,advance=True)[0]


def torch_model(circuit,mean,scale,seed=42,frozen_core=False,motor_heads=1,all_core=False,task_features=False,action_mode='delta'):
    import torch
    from torch import nn
    torch.manual_seed(seed)

    class Actor(nn.Module):
        def __init__(self):
            super().__init__()
            self.register_buffer("input_mean",torch.as_tensor(mean,dtype=torch.float32))
            self.register_buffer("input_scale",torch.as_tensor(scale,dtype=torch.float32))
            self.register_buffer('input_mask',torch.from_numpy(task_feature_mask(len(mean)) if task_features else np.ones(len(mean),np.float32)))
            for i,w in enumerate(circuit.layers):
                self.register_buffer("base"+str(i),torch.from_numpy(w.toarray().astype(np.float32)))
            row,col=circuit.layers[2].nonzero()
            self.register_buffer("edge_row",torch.from_numpy(row.astype(np.int64)))
            self.register_buffer("edge_col",torch.from_numpy(col.astype(np.int64)))
            self.has_memory=len(mean)>OBS_SIZE
            self.motor_heads=motor_heads
            self.all_core=all_core
            self.action_mode=action_mode
            self.progress_supervision=False;self.motor_phase_feedback=False
            if all_core:
                for i in range(2):
                    row_i,col_i=circuit.layers[i].nonzero()
                    self.register_buffer(f'edge_row{i}',torch.from_numpy(row_i.astype(np.int64)))
                    self.register_buffer(f'edge_col{i}',torch.from_numpy(col_i.astype(np.int64)))
                    self.register_parameter(f'raw_gain{i}',nn.Parameter(torch.zeros(len(row_i)),requires_grad=not frozen_core))
            self.encoder=nn.Linear(len(mean),circuit.layers[0].shape[0])
            nn.init.normal_(self.encoder.weight,std=.25)
            nn.init.zeros_(self.encoder.bias)
            self.raw_gain=nn.Parameter(torch.zeros(len(row)),requires_grad=not frozen_core)
            self.decoder=nn.Linear(circuit.layers[2].shape[1],4*motor_heads)
            nn.init.normal_(self.decoder.weight,std=.01)
            nn.init.zeros_(self.decoder.bias)
            if self.has_memory:self.memory_decoder=nn.Linear(circuit.layers[2].shape[1],MEMORY_SIZE)
            self.register_buffer('transition_counts',torch.zeros(MEMORY_SIZE,MEMORY_SIZE))
            self.register_buffer('start_counts',torch.zeros(MEMORY_SIZE))
            self.critic=nn.Linear(circuit.layers[2].shape[1],1)
            self.log_std=nn.Parameter(torch.full((4,),-2.3))

        def effective_weight(self,level=2):
            if level<2 and not self.all_core:return getattr(self,f'base{level}')
            suffix='' if level==2 else str(level)
            weight=getattr(self,f'base{level}').clone()
            rows,cols=getattr(self,'edge_row'+suffix),getattr(self,'edge_col'+suffix)
            weight[rows,cols]=weight[rows,cols]*torch.exp(1.5*torch.tanh(getattr(self,'raw_gain'+suffix)))
            return weight

        def core_activity(self,x):
            x=((x-self.input_mean)/self.input_scale).clamp(-6,6)*self.input_mask
            h=torch.sigmoid(self.encoder(x))
            layers=[h]
            for weight,gain in zip((self.effective_weight(i) for i in range(3)),RESPONSE_GAINS):
                h=torch.sigmoid(gain*(h@weight/weight.sum(0).clamp_min(1e-8)-.5))
                layers.append(h)
            return layers

        def forward(self,x,details=False,phase=None):
            memory=x[:,OBS_SIZE:]
            layers=self.core_activity(x);h=layers[-1]
            self.last_phase_features=h
            if self.motor_heads>1:
                if phase is None:
                    scores=self.phase_logits(h,memory)
                    if self.progress_supervision:
                        from .phase_supervision import feasible_phases
                        allowed=torch.as_tensor(feasible_phases(x.detach().cpu().numpy()),device=x.device)
                        scores=scores.masked_fill(~allowed,-1e9)
                    phase=scores.argmax(-1)
                if self.motor_phase_feedback:
                    motor_x=torch.cat([x[:,:OBS_SIZE],torch.nn.functional.one_hot(phase,MEMORY_SIZE).to(x.dtype)],dim=1)
                    layers=self.core_activity(motor_x);h=layers[-1]
            logits=self.decoder(h)
            if self.motor_heads>1:
                logits=logits.reshape(-1,self.motor_heads,4)[torch.arange(len(h),device=h.device),phase]
            return (logits,layers,self.critic(h).squeeze(-1)) if details else torch.tanh(logits)

        def phase_logits(self,h,memory):
            logits=self.memory_decoder(h)
            allowed=self.transition_counts[memory.argmax(-1)]>0
            allowed=allowed|(~allowed.any(-1,keepdim=True))
            return logits.masked_fill(~allowed,-1e9)

        def save(self,path):
            def array(t):return t.detach().cpu().numpy()
            extra=dict(memory_weight=array(self.memory_decoder.weight.T),memory_bias=array(self.memory_decoder.bias),
                transition_counts=array(self.transition_counts),start_counts=array(self.start_counts)) if self.has_memory else {}
            if self.all_core:
                for i in range(2):extra.update({f'weight{i}':array(self.effective_weight(i)),f'raw_gain{i}':array(getattr(self,f'raw_gain{i}'))})
            np.savez_compressed(path,task="so101",circuit_identity=circuit.identity,motor_heads=self.motor_heads,action_mode=self.action_mode,
                progress_supervision=self.progress_supervision,motor_phase_feedback=self.motor_phase_feedback,
                encoder=array(self.encoder.weight.T),encoder_bias=array(self.encoder.bias),
                input_mean=array(self.input_mean),input_scale=array(self.input_scale),input_mask=array(self.input_mask),
                weight=array(self.effective_weight()),decoder=array(self.decoder.weight.T),bias=array(self.decoder.bias),
                raw_gain=array(self.raw_gain),critic_weight=array(self.critic.weight),critic_bias=array(self.critic.bias),log_std=array(self.log_std),**extra)

        def restore(self,path):
            s=np.load(path,allow_pickle=False)
            self.action_mode=str(s['action_mode']) if 'action_mode' in s else 'delta'
            self.progress_supervision=bool(s['progress_supervision']) if 'progress_supervision' in s else False
            self.motor_phase_feedback=bool(s['motor_phase_feedback']) if 'motor_phase_feedback' in s else False
            if str(s["circuit_identity"])!=circuit.identity:
                raise ValueError("Resume circuit identity mismatch")
            with torch.no_grad():
                for param,key,transpose in [(self.encoder.weight,"encoder",True),(self.encoder.bias,"encoder_bias",False),
                    (self.decoder.weight,"decoder",True),(self.decoder.bias,"bias",False),(self.raw_gain,"raw_gain",False),
                    (self.critic.weight,"critic_weight",False),(self.critic.bias,"critic_bias",False),(self.log_std,"log_std",False)]:
                    param.copy_(torch.as_tensor(s[key].T if transpose else s[key],device=param.device))
                self.input_mean.copy_(torch.as_tensor(s["input_mean"],device=self.input_mean.device))
                self.input_scale.copy_(torch.as_tensor(s["input_scale"],device=self.input_scale.device))
                if 'input_mask' in s:self.input_mask.copy_(torch.as_tensor(s['input_mask'],device=self.input_mask.device))
                if self.has_memory:
                    self.memory_decoder.weight.copy_(torch.as_tensor(s['memory_weight'].T,device=self.memory_decoder.weight.device))
                    self.memory_decoder.bias.copy_(torch.as_tensor(s['memory_bias'],device=self.memory_decoder.bias.device))
                    for key in ('transition_counts','start_counts'):
                        if key in s:getattr(self,key).copy_(torch.as_tensor(s[key],device=getattr(self,key).device))
                if self.all_core:
                    for i in range(2):
                        key=f'raw_gain{i}'
                        if key in s:getattr(self,key).copy_(torch.as_tensor(s[key],device=getattr(self,key).device))
            s.close()
    return Actor()
