"""Bounded live check of single-task stop, automatic repetition and pause."""
import argparse
import json
from pathlib import Path
import time
import urllib.request


def check(base,output):
    def request(path,body=None):
        data=None if body is None else json.dumps(body).encode()
        req=urllib.request.Request(base+path,data=data,headers={'Content-Type':'application/json','Origin':base})
        with urllib.request.urlopen(req,timeout=15) as response:return json.load(response)
    def state():return request('/api/state')['simulation']
    def control(**body):return request('/api/control',body)
    def wait(predicate,seconds=100):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            s=state()
            if predicate(s):return s
            if s.get('error'):raise AssertionError(s['error'])
            time.sleep(.15)
        raise AssertionError('SO-101 episode loop timed out')
    assert state().get('behavior')=='so101'
    completed=[]
    try:
        control(op='loop',enabled=False);control(op='next')
        single=wait(lambda s:s.get('paused') and s.get('outcome')!='running')
        assert single['outcome']=='success',single['outcome']
        time.sleep(.5);still=state()
        assert still['episode']==single['episode'] and still['time_s']==single['time_s']
        completed.append(dict(episode=single['episode'],seed=single['seed'],outcome=single['outcome'],mode='single'))
        control(op='loop',enabled=True)
        previous=single['episode']
        for _ in range(2):
            started=wait(lambda s:s['episode']>previous and s['time_s']>0)
            assert started['robot']['loop_enabled'] and not started['paused']
            assert started['robot']['perception']['camera_name']=='wrist'
            ended=wait(lambda s:s['episode']==started['episode'] and s['robot']['awaiting_next'])
            assert ended['outcome']=='success',ended['outcome']
            completed.append(dict(episode=ended['episode'],seed=ended['seed'],outcome=ended['outcome'],mode='loop'))
            previous=ended['episode']
            print(json.dumps(completed[-1]),flush=True)
        wait(lambda s:s['episode']>previous and s['time_s']>0)
        control(op='pause',paused=True)
        paused=wait(lambda s:s['paused']);time.sleep(.5);still=state()
        assert still['episode']==paused['episode'] and still['time_s']==paused['time_s']
        report=dict(single_task_stops=True,two_automatic_successes=True,loop_pause_stops_physics=True,
            wrist_camera=True,completed=completed)
        Path(output).write_text(json.dumps(report,indent=2));return report
    finally:control(op='pause',paused=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:8772')
    p.add_argument('--output',default='artifacts/so101/wrist-camera/loop-check.json')
    a=p.parse_args();print(json.dumps(check(a.base,a.output),indent=2))
