"""Exercise the live flight API and mode isolation without browser automation."""
import json
import time
from pathlib import Path
import urllib.request
import urllib.error

BASE = 'http://127.0.0.1:8766/api/'
def api(path, body=None):
    request = urllib.request.Request(BASE+path, data=None if body is None else json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(request, timeout=10))

def until(predicate, timeout=35):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        s = api('state')['simulation']
        assert not s.get('error'), s
        if predicate(s):
            return s
        time.sleep(.12)
    raise AssertionError('Timed out waiting for simulation condition')

initial = until(lambda s: s.get('seq'))
assert initial.get('behavior') == 'odor', 'Start in odor mode to verify preservation'
assert api('state')['job']['status'] not in ['training', 'evaluating', 'cancelling']
checks = []
try:
    api('control', {'op': 'pause', 'paused': True})
    before = until(lambda s: s.get('paused'))
    api('control', {'op': 'behavior', 'behavior': 'flight'})
    s = until(lambda s: s.get('behavior') == 'flight' and s.get('seq'))
    assert s['render']['width'] == 1920 and s['render']['height'] == 1080 and s['render']['msaa'] == 4
    assert s['model'] == before['model'] and len(s['activity']) == 7075 and s['circuit_identity']==before['circuit_identity'] and s['neural']['brain_connected']
    checks += ['Full HD flight frame', 'Selected MaleCNS brain inherited by flight worker']
    start = s['time_s']
    s = until(lambda s: s.get('time_s', 0) > start+.002)
    assert s['altitude_mm'] > 2 and 200 < s['wing_hz'] < 240
    checks.append('Live aerodynamic state advances with plausible wing frequency')
    api('control', {'op': 'pause', 'paused': True})
    s = until(lambda s: s.get('paused'))
    paused_time, seq = s['time_s'], s['seq']
    s = until(lambda s: s.get('seq', 0) >= seq+3)
    assert s['time_s'] == paused_time
    checks.append('Pause freezes simulation time')
    for gesture, dx, dy in [('rotate', .08, .03), ('pan', .02, .02), ('zoom', 0, .08)]:
        pose = s['camera_pose']; seq = s['seq']
        api('control', {'op': 'camera', 'camera': 'body', 'gesture': gesture, 'dx': dx, 'dy': dy})
        s = until(lambda s: s.get('seq', 0) >= seq+2)
        assert s['camera_pose'] != pose
        assert s['time_s'] == paused_time
        checks.append('Mouse '+gesture+' while paused')
    api('control', {'op': 'camera', 'camera': 'body', 'reset_view': True})
    api('control', {'op': 'reset', 'goal': [25,-8]})
    s = until(lambda s: s.get('goal_mm') == [25,-8])
    assert s['paused'] and s['time_s'] == 0
    checks.append('User odor target changes while paused')
    model = api('model/'+s['model'])
    assert s['model_sha256'] == model['sha256'] and len(model['gains'])==82747
    graph = api('graph'); e = graph['edges'][0]
    edge = api(f"connection/{graph['nodes'][e['a']]['id']}/{graph['nodes'][e['b']]['id']}?model={s['model']}")
    assert edge['model'] is not None and edge['anatomical_contacts'] > 0
    checks.append('Flight brain checkpoint and actual synaptic gain inspection')
    api('control', {'op':'model','model':'untrained'})
    s=until(lambda s:s.get('model')=='untrained')
    assert s['paused'] and len(s['activity'])==7075
    api('control', {'op':'model','model':before['model']})
    s=until(lambda s:s.get('model')==before['model'])
    checks.append('Flight brain model changes and restores while paused')
    api('control', {'op': 'behavior', 'behavior': 'odor'})
    after = until(lambda s: s.get('behavior') == 'odor' and s.get('seq'))
    for k in ['model', 'model_sha256', 'goal_mm', 'time_s', 'position_mm', 'camera_pose', 'activity']:
        assert before[k] == after[k], k
    checks.append('Odor model, weights, target, physics pose, camera and activity preserved exactly')
finally:
    api('control', {'op': 'behavior', 'behavior': 'odor'})
    api('control', {'op': 'pause', 'paused': initial['paused']})

path = Path('artifacts/lab/flight/ui-validation.json')
path.write_text(json.dumps(dict(passed=len(checks), checks=checks, validation='HTTP API and physics; no browser UI test'), indent=2))
print(json.dumps(dict(passed=len(checks), checks=checks), indent=2))
