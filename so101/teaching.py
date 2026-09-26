"""Bounded, read-only capture of an operator's six-joint demonstration."""
import base64
import json
import time
from pathlib import Path

from .calibration_contract import atomic_json
from .physical_contract import MAX_RECORD_SECONDS, MAX_SAMPLES, MAX_RUN_SECONDS, RATE, check_pose


def latest_teaching(root,serial_number,calibration_sha256):
    """Restore display metadata only. A recording never grants motion permission."""
    paths=sorted(Path(root).glob('*/teaching-*/demonstration.json'),
                 key=lambda p:p.stat().st_mtime,reverse=True)
    for path in paths:
        try:
            if path.stat().st_size>16_000_000:continue
            data=json.loads(path.read_text());identity=data['identity'];points=data['points']
            if (data.get('schema')!=1 or data.get('controller')!='operator_demonstration_only'
                    or identity.get('serial_number')!=serial_number
                    or identity.get('calibration_sha256')!=calibration_sha256):continue
            if not isinstance(points,list) or len(points)>MAX_SAMPLES:continue
            return dict(active=False,valid=data.get('valid') is True,error=data.get('error'),
                        samples=len(points),seconds=float(points[-1]['t']) if points else 0,
                        joint_span_counts=data.get('joint_span_counts'),path=str(path),
                        bounded_playback_seconds=data.get('bounded_playback_seconds'),
                        execution_allowed=False,requires_review=data.get('requires_review',True),
                        warning_samples=data.get('warning_samples',0),restored=True)
        except (OSError,ValueError,KeyError,TypeError,IndexError):continue
    return None


class TeachingRecorder:
    def __init__(self, directory, bounds, identity, clock=time.monotonic):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=False)
        self.bounds=bounds;self.identity=identity;self.clock=clock;self.started=clock()
        self.points=[];self.closed=False
        self.last_image=-1.

    def append(self, q, cameras, decision, motors=None, warnings=None):
        if self.closed:raise ValueError('Gösterim kaydı kapandı')
        stamp=self.clock()-self.started
        if stamp>MAX_RECORD_SECONDS or len(self.points)>=MAX_SAMPLES:
            raise ValueError('Gösterim kayıt süresi doldu; kolu desteklemeye devam et')
        # A free arm may be hand-guided outside the later execution envelope.
        # Preserve that evidence; never widen the physical execution limits.
        check_pose(q,[(0,4095)]*6)
        if self.points:
            previous=self.points[-1];dt=stamp-previous['t']
            if not 0<dt<=.3:raise ValueError('Gösterim örnekleri arasında zaman boşluğu oluştu')
        point=dict(t=stamp,q=list(q),frames={name:{k:frame[k] for k in ('session','sequence','wall_time')}
                   for name,frame in cameras.items()},sensor_values=decision['sensor_values'],
                   wall_time=time.time(),motors=motors or [],warnings=warnings or [])
        self.points.append(point)
        with (self.directory/'samples.jsonl').open('a') as stream:
            stream.write(json.dumps(point,allow_nan=False)+'\n')
        if stamp-self.last_image>=1:
            for name,frame in cameras.items():
                if name not in ('top','wrist'):raise ValueError('Geçersiz öğretim kamerası')
                if frame.get('image'):
                    (self.directory/f'{len(self.points):04d}-{name}.jpg').write_bytes(
                        base64.b64decode(frame['image'].split(',')[-1],validate=True))
            self.last_image=stamp
        outside=[i+1 for i,(value,(lo,hi)) in enumerate(zip(q,self.bounds)) if not lo<=value<=hi]
        return dict(active=True,samples=len(self.points),seconds=stamp,seconds_left=max(0,MAX_RECORD_SECONDS-stamp),
                    outside_execution_limits=outside,warnings=warnings or [],
                    warning_samples=sum(bool(p['warnings']) for p in self.points))

    def finish(self, reason=None):
        self.closed=True;duration=None
        if reason is None:
            try:
                if len(self.points)<2:raise ValueError('Gösterimde en az iki örnek gerekli')
                duration=0.
                for i,point in enumerate(self.points):
                    check_pose(point['q'],self.bounds)
                    if i:
                        previous=self.points[i-1]
                        delta=max(abs(a-b) for a,b in zip(point['q'],previous['q']))
                        duration+=max(point['t']-previous['t'],delta/RATE)
                if duration>MAX_RUN_SECONDS:raise ValueError('Sınırlı yürütme 180 saniyeyi aşıyor; daha kısa gösterim gerekli')
            except ValueError as exc:reason=str(exc)
        span=[max(p['q'][i] for p in self.points)-min(p['q'][i] for p in self.points)
              for i in range(6)] if self.points else [0]*6
        warning_samples=sum(bool(p['warnings']) for p in self.points)
        result=dict(schema=1,controller='operator_demonstration_only',brain_connected=False,
                    identity=self.identity,points=self.points,valid=reason is None,error=reason,
                    bounded_playback_seconds=duration,joint_span_counts=span,
                    execution_allowed=False,requires_review=bool(warning_samples),warning_samples=warning_samples)
        path=self.directory/'demonstration.json';atomic_json(path,result)
        return dict(active=False,valid=reason is None,error=reason,samples=len(self.points),
                    seconds=self.points[-1]['t'] if self.points else 0,
                    joint_span_counts=span,path=str(path),bounded_playback_seconds=duration,
                    execution_allowed=False,requires_review=bool(warning_samples),warning_samples=warning_samples)
