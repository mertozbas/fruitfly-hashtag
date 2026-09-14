"""Deterministic motor calibration limits and durable local records."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from .hardware_contract import JOINTS,assert_read_packet

RANGED_JOINTS=tuple(n for n in JOINTS if n!='wrist_roll')
TERMINAL={'saved','restored','cancelled','failed'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).exists() else None


def atomic_json(path,record):
    atomic_bytes(path,json.dumps(record,indent=2,allow_nan=False).encode())


def atomic_bytes(path,raw):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
        if os.name=='posix':
            parent=os.open(path.parent,os.O_RDONLY)
            try:os.fsync(parent)
            finally:os.close(parent)
    finally:
        if os.path.exists(name):os.unlink(name)


def signed_word(value):
    if type(value) is not int or not -2047<=value<=2047:raise ValueError('Offset -2047…2047 aralığında olmalı')
    return abs(value)|(2048 if value<0 else 0)


def validate_backup(record):
    import base64
    motors=record.get('motors',{})
    if not isinstance(motors,dict) or set(motors)!=set(JOINTS):raise ValueError('Yedekte altı eklem tam olmalı')
    for i,name in enumerate(JOINTS,1):
        m=motors[name]
        if not isinstance(m,dict) or any(type(m.get(k)) is not int for k in ('id','range_min','range_max','homing_offset','operating_mode','torque','lock')):raise ValueError('Yedekte geçersiz motor alanı')
        if m['id']!=i or not 0<=m['range_min']<=m['range_max']<=4095 or m['operating_mode'] not in (0,1,2,3) or m['torque'] not in (0,1) or m['lock'] not in (0,1):raise ValueError('Yedekte motor sınırı / kimliği geçersiz')
        signed_word(m['homing_offset'])
    raw=record.get('file_base64')
    actual=hashlib.sha256(base64.b64decode(raw,validate=True)).hexdigest() if raw is not None else None
    if actual!=record.get('file_sha256'):raise ValueError('Yedek dosyası SHA-256 doğrulamasını geçmedi')


def calibration_packet(packet,permit=None):
    """No goal-position, torque-on, broadcast or arbitrary register writes.

    A write must exactly match the single use permit issued by the controller.
    Torque can only become OFF. Other writes require an EEPROM preparation gate.
    """
    p=bytes(packet)
    if len(p)>4 and p[4] in (1,2):return assert_read_packet(p)
    if len(p)<8 or p[:2]!=b'\xff\xff' or p[2] not in range(1,7) or p[3]+4!=len(p) or sum(p[2:])&255!=255 or p[4]!=3:
        raise PermissionError('Geçersiz kalibrasyon yazma paketi')
    address=p[5];data=p[6:-1];value=int.from_bytes(data,'little')
    if permit!=(p[2],address,bytes(data)):raise PermissionError('Bu yazma için tek kullanımlık izin yok')
    allowed=(len(data)==1 and ((address==40 and value==0) or (address==55 and value in (0,1)) or (address==33 and value in (0,1,2,3)))) or (len(data)==2 and address in (9,11,31) and value<=4095)
    if not allowed:raise PermissionError('Hareket / tork açma / ID / hız komutu engellendi')
    return p


def range_errors(ranges,samples,reference):
    errors=[]
    for name in RANGED_JOINTS:
        lo,hi=ranges[name]
        if not 0<=lo<hi<=4095:errors.append(f'{name}: enkoder taşması / geçersiz sınır')
        if hi-lo<300:errors.append(f'{name}: hareket aralığı yetersiz (en az 300 sayım)')
        if samples.get(name,0)<12:errors.append(f'{name}: en az 12 örnek gerekli')
        if not lo+50<=reference[name]<=hi-50:errors.append(f'{name}: referansın iki yönü de ölçülmeli')
    return errors
