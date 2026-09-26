"""Limits for operator-supervised, joint-space teaching. No camera-to-XYZ policy."""
import hashlib
import json
import math
from .hardware_contract import JOINTS,assert_read_packet

TICKS_PER_DEGREE=4095/360
RATE=40.0  # commanded encoder counts / second (3.52 deg/s)
MAX_STEP=2
MAX_LEAD=8
MARGIN=20
MAX_SAMPLES=1800
MAX_RECORD_SECONDS=90
MAX_RUN_SECONDS=180
HOLD_TIMEOUT=.5
HEARTBEAT_TIMEOUT=1.0


def signature(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def limits(motors):
    return [(motors[n]['range_min']+(0 if n=='gripper' else MARGIN),motors[n]['range_max']-(0 if n=='gripper' else MARGIN)) for n in JOINTS]


def check_pose(q,bounds):
    if not isinstance(q,(list,tuple)) or len(q)!=6 or any(type(v) is not int for v in q):raise ValueError('Altı tam sayı enkoder konumu gerekli')
    for name,value,(lo,hi) in zip(JOINTS,q,bounds):
        if not lo<=value<=hi:raise ValueError(f'{name}: {value}, güvenli {lo}–{hi} aralığının dışında; elle sınırdan uzaklaştır')


def validate_trajectory(points,bounds):
    if not 2<=len(points)<=MAX_SAMPLES:raise ValueError('Kayıtta 2–1800 örnek gerekli')
    previous=None;duration=0.
    for point in points:
        check_pose(point['q'],bounds)
        stamp=point['t']
        if type(stamp) not in (float,int) or not math.isfinite(stamp) or stamp<0 or stamp>MAX_RECORD_SECONDS:raise ValueError('Kayıt zamanı geçersiz')
        if previous:
            dt=stamp-previous['t']
            if not 0<dt<=.3:raise ValueError('Kayıtta zaman boşluğu var; yeniden kaydet')
            delta=max(abs(a-b) for a,b in zip(point['q'],previous['q']))
            if delta>35:raise ValueError('Öğretim fazla hızlı; iki örnek arasında 35 sayım aşıldı')
            duration+=max(dt,delta/RATE)
        previous=point
    if duration>MAX_RUN_SECONDS:raise ValueError('Yavaş oynatım 180 saniyeyi aşıyor; daha kısa kayıt gerekli')
    return duration


def interpolate(a,b,fraction):return [round(x+(y-x)*fraction) for x,y in zip(a,b)]


def motion_packet(packet,permit=None):
    p=bytes(packet)
    if len(p)>4 and p[4] in (1,2):return assert_read_packet(p)
    if len(p)<8 or p[:2]!=b'\xff\xff' or p[2] not in range(1,7) or p[3]+4!=len(p) or sum(p[2:])&255!=255 or p[4]!=3:raise PermissionError('Geçersiz fiziksel komut paketi')
    address=p[5];data=p[6:-1];value=int.from_bytes(data,'little')
    if permit!=(p[2],address,data):raise PermissionError('Tek kullanımlık hareket izni yok')
    allowed=(len(data)==1 and address==40 and value in (0,1)) or (len(data)==2 and (
        (address==42 and 0<=value<=4095) or (address==44 and value==0) or (address==46 and 1<=value<=50)
        or (address==48 and 1<=value<=(250 if p[2]==6 else 500))))
    if not allowed:raise PermissionError('EEPROM / kalibrasyon / ID / sınırsız hız yazımı engellendi')
    return p
