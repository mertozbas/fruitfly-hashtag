"""Bounded continuous anatomical visual steering of the SO-101 base.

The camera is a left/right command input, not a calibrated visual servo.
Only motor 1 moves; the existing supported pose and gripper state are preserved.
"""
import time

import numpy as np

from .hardware_contract import JOINTS, signed_magnitude
from .neural_wrist import neural_readout, sensor_signal
from .range_probe import RangeBus


class NeuralPanBus(RangeBus):
    """Reuse the packet guard with a symmetric, calibrated base envelope."""
    def __init__(self, port, span=170):
        super().__init__(port, 1, span, tracking_limit=16)

    def envelope(self):
        return self.initial-self.span, self.initial+self.span


def visual_command(policy, rgb):
    import cv2
    signal = sensor_signal(rgb)
    colour = rgb.astype(np.int16)
    mask = ((colour[..., 0] > 100) & (colour[..., 0]-colour[..., 1] > 50)
            & (colour[..., 0]-colour[..., 2] > 50)).astype(np.uint8)
    _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    visible = any(s[4] >= 100 and s[2] >= 8 and s[3] >= 8 for s in stats[1:])
    if not visible:
        _, layers=policy.activity(signal)
        if any(not np.isfinite(a).all() for a in layers):raise ValueError('Geçersiz sinir ağı etkinliği')
        return dict(visible=False, drive=0., sensor_values=signal.tolist(),
                    layer_activity=[a.tolist() for a in layers],group_order=list(policy.circuit.groups))
    result = neural_readout(policy, signal)
    # A symmetric input gives a small learned bias. A colour-balance dead zone
    # suppresses it; outside it, direction and magnitude come from the network.
    balance = float((signal[0]-signal[1])/max(float(signal.sum()), 1e-6))
    result.update(visible=True, drive=result['bias_free_drive'] if abs(balance) > .15 else 0.,
                  colour_balance=balance, directional_mapping=False,
                  motor_adapter='Signed bias-free descending drive -> bounded base target; zero drive holds',
                  scope='Continuous visual command input on base only; no grasp or calibrated visual servo')
    return result


def read_telemetry(bus, saved):
    """Read feedback without treating observational data as an actuator command."""
    begin = time.monotonic()
    q = bus.positions()
    rows = []
    for i, name in enumerate(JOINTS, 1):
        c = saved[name]
        margin = 0 if i == 6 else 20
        row = dict(id=i, name=name, position=q[i-1], temperature_c=bus.read(i, 63, 1),
                   voltage_v=bus.read(i, 62, 1)/10, status=bus.read(i, 65, 1),
                   load=signed_magnitude(bus.read(i, 60), 10), torque=bool(bus.read(i, 40, 1)),
                   operating_mode=bus.read(i,33,1),
                   in_range=c['range_min']+margin <= q[i-1] <= c['range_max']-margin)
        rows.append(row)
    return q,rows,time.monotonic()-begin


def recording_telemetry(bus, saved):
    """A read-only recording requires all torque off and retains warning samples."""
    q,rows,elapsed=read_telemetry(bus,saved)
    if any(row['torque'] for row in rows):raise ValueError('Gösterim sırasında motor torku değişti')
    warnings=[]
    for row in rows:
        for code,condition,value in (
                ('temperature',row['temperature_c']>=50,row['temperature_c']),
                ('voltage',not 6<=row['voltage_v']<=13.2,row['voltage_v']),
                ('status',bool(row['status']),row['status']),
                ('load',abs(row['load'])>120,row['load']),
                ('mode',row['operating_mode']!=0,row['operating_mode']),
                ('range',not row['in_range'],row['position'])):
            if condition:warnings.append(dict(motor_id=row['id'],code=code,value=value))
    if elapsed>.15:warnings.append(dict(code='read_latency',value=elapsed))
    return q,rows,warnings


def telemetry(bus, saved, reference=None, allow_manual=False, *, permit_warm=False):
    q,rows,elapsed=read_telemetry(bus,saved)
    # Only the idle readout may display unfiltered feedback with all torque off.
    # Hold/run always use the strict default, including before torque-on.
    if allow_manual and reference is None and not any(row['torque'] for row in rows):
        return q,rows
    for row in rows:
        i=row['id']
        if row['operating_mode'] != 0 or row['status'] or abs(row['load']) > 120:
            raise ValueError(f'Motor {i}: mod/durum/yük sınırı ({row})')
        # Only a reviewed controller that holds at 50 C may inspect 50..59 C.
        # Preflight, pose hold and ordinary movement keep the strict default.
        if row['temperature_c'] >= (60 if permit_warm else 50) or not 6 <= row['voltage_v'] <= 13.2:
            raise ValueError(f'Motor {i}: sıcaklık/besleme sınırı ({row})')
        if reference is not None and row['torque'] != (i < 6):
            raise ValueError(f'Motor {i}: tork durumu değişti')
    for row in rows:
        if not row['in_range']:raise ValueError(f"{row['name']}: kalibrasyon sınırı")
    if reference is not None:
        if any(abs(a-b) > 8 for a, b in zip(q[1:], reference[1:])):
            raise ValueError('Tutulan eklem kaydı; hareket durdu')
        low, high = bus.envelope()
        if not low-8 <= q[0] <= high+8:
            raise ValueError('Taban ölçümü çalışma aralığını aştı')
    if elapsed > .15:
        raise ValueError('Motor telemetrisi 150 ms sınırını aştı')
    return q, rows


class NeuralMotion:
    """One finite session. A stop never resumes or releases supporting torque."""
    def __init__(self, bus, saved, expected, duration=30, clock=time.monotonic):
        if not 1 <= duration <= 30:
            raise ValueError('Oturum en fazla 30 saniye')
        self.bus, self.saved, self.expected = bus, saved, expected
        self.duration, self.clock = duration, clock
        self.started = self.last_tick = None
        self.stall_since = None
        self.commands = 0
        self.reference = None

    def start(self):
        self.bus.open()
        self.bus.verify(self.saved)
        q, rows = telemetry(self.bus, self.saved)
        if any(abs(a-b) > 3 for a, b in zip(q, self.expected)):
            raise ValueError('Kol önizlemeden sonra hareket etti')
        self.bus.prepare(q, self.saved)
        self.reference = q
        self.started = self.last_tick = self.clock()
        self.bus.begin_motion()
        return q, rows

    def step(self, drive, visible, heartbeat_age, source_age):
        now = self.clock()
        if self.started is None or now-self.started >= self.duration:
            raise ValueError('30 saniyelik oturum tamamlandı')
        if heartbeat_age > 1. or source_age > .4 or source_age < 0:
            raise ValueError('Panel veya kamera güncelliğini kaybetti')
        dt = now-self.last_tick
        if dt > .25:
            raise ValueError('Kontrol döngüsü 250 ms sınırını aştı')
        self.last_tick = now
        if type(drive) not in (int, float) or not np.isfinite(drive) or not -1 <= drive <= 1:
            raise ValueError('Geçersiz sinir ağı çıkışı')
        q, rows = telemetry(self.bus, self.saved, self.reference)
        if source_age+self.clock()-now > .4:
            raise ValueError('Kamera motor okuması sırasında eskidi')
        if not visible or drive == 0:
            # Loss of stimulus cancels the in-flight lead once, then waits.
            if self.bus.last_goal != q[0]:
                self.bus.stop_position=q[0];self.bus.phase='hold'
                self.bus.write(42, q[0]);self.bus.last_goal=q[0];self.bus.phase='move'
            self.stall_since=None
            return dict(q=q, motors=rows, goal=self.bus.last_goal, desired=None, neural_command=False)
        desired = self.bus.initial-int(round(self.bus.span*drive))
        delta = max(-2, min(2, desired-self.bus.last_goal))
        # At most 20 counts/s, matching the existing native velocity limit.
        if dt < .08 or delta == 0:
            return dict(q=q, motors=rows, goal=self.bus.last_goal, desired=desired, neural_command=False)
        target = self.bus.last_goal+delta
        if abs(target-q[0]) > self.bus.tracking_limit:
            if self.stall_since is None:self.stall_since=now
            if now-self.stall_since > 1.:raise ValueError('Motor hedefi izleyemiyor')
            return dict(q=q, motors=rows, goal=self.bus.last_goal, desired=desired, neural_command=False)
        self.stall_since=None
        self.bus.goal(target)
        self.commands += 1
        return dict(q=q, motors=rows, goal=target, desired=desired, neural_command=True)

    def stop(self):
        errors=self.bus.finish()
        self.bus.close()
        if errors:raise OSError('; '.join(errors))
