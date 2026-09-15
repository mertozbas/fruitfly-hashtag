"""Single real-camera/vision-core decision inside the existing +8-count wrist limit.

This is an engineered commissioning adapter, not pick/place, a robot-frame
calibration, biological whole-brain emulation, or closed-loop visual servoing.
The outbound amplitude comes from a trained anatomical readout. The return is
deterministic safety motion. Magnitude is mapped to the tested one-sided range;
this deliberately makes no claim about matching visual and wrist directions.
"""
import base64
import hashlib
import json
from pathlib import Path
import time
import urllib.request

import numpy as np


def sensor_signal(rgb):
    """Use the existing fly red-salience equation on two halves of one RGB image."""
    rgb=np.asarray(rgb)
    if rgb.shape!=(720,1280,3) or rgb.dtype!=np.uint8:
        raise ValueError('Expected a native 1280x720 RGB frame')
    eyes=np.stack((rgb[:,:640],rgb[:,640:])).astype(np.float32)/255
    salience=np.maximum(0,eyes[...,0]-np.maximum(eyes[...,1],eyes[...,2])-.1)
    return salience.mean(axis=(1,2)).astype(np.float32)


def neural_readout(policy,signal):
    if policy.task!='vision' or policy.circuit.metadata.get('task')!='vision':
        raise ValueError('A trained anatomical vision policy is required')
    signal=np.asarray(signal,dtype=np.float32)
    if signal.shape!=(2,) or not np.isfinite(signal).all() or np.any(signal<0) or np.any(signal>1):
        raise ValueError('Expected two finite nonnegative visual intensities')
    if float(signal.sum())<1e-5:raise ValueError('No visible red stimulus; no motor command')
    with np.errstate(over='raise',invalid='raise',divide='raise'):
        steering,layers=policy.activity(signal)
    if not np.isfinite(steering) or any(not np.isfinite(x).all() for x in layers):
        raise ValueError('Non-finite neural activity')
    # Remove the decoder bias so silence cannot generate a physical command.
    with np.errstate(over='raise',invalid='raise',divide='raise'):
        drive=float(np.tanh(layers[-1]@policy.decoder).item())
        silenced=float(np.tanh(np.zeros_like(layers[-1])@policy.decoder).item())
    if not np.isfinite(drive) or not -1<=drive<=1 or silenced!=0:
        raise ValueError('Invalid neural motor readout')
    delta=int(np.rint(8*abs(drive)))
    return dict(sensor_values=signal.tolist(),original_steering=float(steering),
                bias_free_drive=drive,delta_counts=delta,silenced_delta_counts=0,
                directional_mapping=False,layer_activity=[a.tolist() for a in layers],
                group_order=list(policy.circuit.groups),
                input_adapter='physical top RGB left/right halves -> red salience -> trained vision circuit',
                motor_adapter='magnitude of bias-free descending readout -> round(8*abs(drive)) positive wrist encoder counts',
                scope='One forward pass and bounded wrist pulse; no physical pick/place or coordinate alignment')


def live_decision(plan):
    import cv2
    from odor_policy import Policy
    model=Path(plan['neural_model_path'])
    checkpoint_sha=hashlib.sha256(model.read_bytes()).hexdigest()
    if checkpoint_sha!=plan['neural_model_sha256']:raise ValueError('Neural checkpoint changed')
    policy=Policy(model)
    if policy.circuit.identity!=plan['neural_circuit_sha256']:raise ValueError('Neural circuit changed')
    if hashlib.sha256(model.read_bytes()).hexdigest()!=checkpoint_sha:raise ValueError('Checkpoint changed while loading')
    with urllib.request.urlopen('http://127.0.0.1:8766/api/hardware/state',timeout=.25) as response:state=json.load(response)
    camera=state['cameras']['top']
    if (not camera.get('fresh') or camera.get('age_ms',10000)>400
            or camera.get('session')!=plan['cameras']['top']
            or not 0<=time.time()-camera['wall_time']<=.4):
        raise ValueError('Live neural image is stale or its camera session changed')
    raw=base64.b64decode(camera['image'].split(',')[-1],validate=True)
    frame=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
    if frame is None:raise ValueError('Invalid neural camera image')
    # The API draws green marker annotations. Exclude their small non-red effect
    # from the scope claim: this is the displayed RGB frame, not sensor RAW.
    rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
    # This visual-navigation circuit consumes colour, not marker identities or
    # metric object poses. Require a visible compact red region in the input.
    colour=rgb.astype(np.int16)
    red=((colour[...,0]>100)&(colour[...,0]-colour[...,1]>50)&(colour[...,0]-colour[...,2]>50)).astype(np.uint8)
    _,_,stats,_=cv2.connectedComponentsWithStats(red)
    regions=[s.tolist() for s in stats[1:] if s[4]>=100 and s[2]>=8 and s[3]>=8]
    if not regions:raise ValueError('No visible red stimulus region; no motor command')
    result=neural_readout(policy,sensor_signal(rgb));result['red_regions_xywha']=regions
    if time.time()-camera['wall_time']>.4:raise ValueError('Neural decision missed camera freshness deadline')
    result.update(model_path=str(model),model_sha256=checkpoint_sha,circuit_sha256=policy.circuit.identity,
                  input_image_sha256=hashlib.sha256(raw).hexdigest(),
                  source_frame={k:camera[k] for k in ('session','sequence','wall_time','width','height')},
                  decision_wall_time=time.time())
    return result
