"""Read-only SO-101 commissioning contracts; no actuator execution API."""
import hashlib
import json
import math
from pathlib import Path

JOINTS=('shoulder_pan','shoulder_lift','elbow_flex','wrist_flex','wrist_roll','gripper')
FIELDS=('id','drive_mode','homing_offset','range_min','range_max')


def calibration(path):
    raw=Path(path).read_bytes();motors=json.loads(raw)
    errors=[]
    if not isinstance(motors,dict) or set(motors)!=set(JOINTS):
        raise ValueError('Kalibrasyonda altı SO-101 eklemi tam ve doğru adlarla bulunmalı.')
    for i,name in enumerate(JOINTS,1):
        m=motors[name]
        if not isinstance(m,dict) or any(type(m.get(k)) is not int for k in FIELDS):
            errors.append(f'{name}: eksik / geçersiz motor alanları');continue
        if m['id']!=i:errors.append(f'{name}: beklenen motor ID {i}')
        if m['drive_mode'] not in (0,1):errors.append(f'{name}: yön bilgisi geçersiz')
        if not -2047<=m['homing_offset']<=2047:errors.append(f'{name}: homing offset sınır dışında')
        if not 0<=m['range_min']<m['range_max']<=4095:errors.append(f'{name}: enkoder aralığı geçersiz')
        elif m['range_max']-m['range_min']<200:errors.append(f'{name}: kaydedilen hareket aralığı çok dar')
    return dict(motors=motors,sha256=hashlib.sha256(raw).hexdigest(),valid=not errors,errors=errors)


def signed_magnitude(value,bit):
    return -(value & ((1<<bit)-1)) if value & (1<<bit) else value


def joint_value(name,position,cal):
    """LeRobot 0.6 DEGREES for arm, RANGE_0_100 for gripper; not MuJoCo radians.

    Homing offset is already applied by the motor. Do not subtract it again.
    Values outside the calibrated range stay visible rather than being clipped.
    """
    if not math.isfinite(position):raise ValueError('Sonlu enkoder konumu gerekli')
    if name=='gripper':
        value=100*(position-cal['range_min'])/(cal['range_max']-cal['range_min'])
        return (100-value if cal['drive_mode'] else value),'%'
    return (position-(cal['range_min']+cal['range_max'])/2)*360/4095,'°'


def assert_read_packet(packet):
    """Serial boundary: only unicast PING / READ for IDs 1..6 may leave the app.

    Includes checksum and length checks. Goal, torque, calibration, reset, sync
    write, broadcast and action instructions are all rejected before transport.
    """
    p=bytes(packet)
    if len(p)<6 or p[:2]!=b'\xff\xff' or p[2] not in range(1,7) or p[3]+4!=len(p):
        raise PermissionError('Geçersiz donanım tanılama paketi')
    if (sum(p[2:])&255)!=255:raise PermissionError('Geçersiz paket sağlama toplamı')
    if not ((p[4]==1 and len(p)==6) or (p[4]==2 and len(p)==8 and 1<=p[6]<=16 and p[5]+p[6]<=72)):
        raise PermissionError('Salt okuma: motor / tork / kalibrasyon yazma komutu engellendi')
    return p


def compare_calibration(saved,hardware):
    return [f'{name}.{field}' for name in JOINTS for field in ('id','range_min','range_max','homing_offset')
            if saved[name][field]!=hardware.get(name,{}).get(field)]


def readiness(saved,arm,cameras):
    """Observed preparation checks only; autonomous motion is not commissioned."""
    motors=arm.get('motors',[]) if arm.get('connected') else []
    outside=[m.get('name','?') for m in motors if m.get('in_calibrated_range') is False]
    def sees(role,key):
        camera=cameras.get(role,{})
        p=camera.get('perception',{})
        return bool(camera.get('fresh') and p.get('frame_sequence')==camera.get('sequence')
                    and camera.get('sequence') is not None and p.get(key))
    return [
        dict(id='calibration_file',label='Yerel kalibrasyon dosyası',passed=bool(saved and saved['valid'])),
        dict(id='motor_bus',label='Altı STS3215 motorun okunması',passed=bool(arm and arm.get('connected') and len(arm.get('motors',[]))==6)),
        dict(id='live_calibration',label='Dosya ve motor kalibrasyonunun eşleşmesi',passed=bool(arm and arm.get('connected') and arm.get('calibration_match'))),
        dict(id='joint_ranges',label='Canlı eklemlerin kayıtlı aralıkta olması'+(' · '+', '.join(outside) if outside else ''),
             passed=bool(len(motors)==6 and all(m.get('in_calibrated_range') is True for m in motors))),
        *[dict(id=f'{role}_camera',label=label,passed=bool(cameras.get(role,{}).get('fresh'))) for role,label in [('wrist','Bilek kamera görüntüsü'),('top','Üst / karşı kamera görüntüsü')]],
        dict(id='cube_marker',label='Küp işaretinin canlı görüntüde okunması · 200',passed=any(sees(r,'cube_visible') for r in ('wrist','top'))),
        dict(id='bin_marker',label='Kutu işaretinin üst kamerada okunması · 211',passed=sees('top','bin_visible')),
        dict(id='joint_alignment',label='Gerçek eklem yönleri ve simülasyon sıfırlarının ölçülmesi',passed=False),
        dict(id='vision_geometry',label='Kamera / masa / robot koordinat kalibrasyonu',passed=False),
        dict(id='grasp_feedback',label='Gerçek kavrama ve düşme algısının doğrulanması',passed=False),
        dict(id='physical_trial',label='Sınırlı gerçek kol deneyi',passed=False),
    ]
