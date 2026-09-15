"""Isolated, bounded USB diagnostics. This worker has no motion command mode."""
import argparse
import base64
from importlib import metadata
import json
import signal
import sys
import time
from .hardware_contract import JOINTS,assert_read_packet,calibration,compare_calibration,joint_value,signed_magnitude


def emit(**record):
    print(json.dumps(dict(wall_time=time.time(),**record),allow_nan=False),flush=True)


def inventory():
    from serial.tools.list_ports import comports
    versions={name:metadata.version(name) for name in ('pyserial','feetech-servo-sdk','numpy','opencv-python-headless')}
    ports=[dict(device=p.device,description=p.description,vid=p.vid,pid=p.pid,serial_number=p.serial_number) for p in comports()
           if p.device.startswith(('/dev/cu.usb','/dev/ttyUSB','/dev/ttyACM','COM'))]
    emit(kind='inventory',ports=ports,versions=versions,cameras_opened=False,motors_opened=False)


def read_only_port(name):
    from scservo_sdk import PortHandler
    class ReadOnlyPort(PortHandler):
        def writePort(self,packet):return super().writePort(assert_read_packet(packet))
        def getCurrentTime(self):return time.monotonic()*1000
    return ReadOnlyPort(name)


def inspect_arm(port_name,path,expected_sha,duration):
    from scservo_sdk import PacketHandler,COMM_SUCCESS
    saved=calibration(path)
    if not saved['valid'] or saved['sha256']!=expected_sha:raise ValueError('Kalibrasyon geçersiz veya seçildikten sonra değişti')
    port=read_only_port(port_name);packet=PacketHandler(0)
    def read(motor,address,size):
        result,comm,error=(packet.read1ByteTxRx if size==1 else packet.read2ByteTxRx)(port,motor,address)
        if comm!=COMM_SUCCESS or error:raise OSError(f'Motor {motor} okuma hatası (iletişim={comm}, durum={error})')
        return int(result)
    try:
        if not port.openPort():raise OSError('USB portu açılamadı')
        # Prevent a second POSIX tty opener while this diagnostic session owns it.
        if sys.platform!='win32':
            import fcntl,termios
            if hasattr(termios,'TIOCEXCL'):fcntl.ioctl(port.ser.fileno(),termios.TIOCEXCL)
        hardware={}
        for i,name in enumerate(JOINTS,1):
            model=read(i,3,2)
            if model!=777:raise ValueError(f'Motor {i}: STS3215 bekleniyordu; model kodu {model}')
            hardware[name]=dict(id=i,range_min=read(i,9,2),range_max=read(i,11,2),homing_offset=signed_magnitude(read(i,31,2),11))
        mismatches=compare_calibration(saved['motors'],hardware)
        deadline=time.monotonic()+duration;sequence=0
        while time.monotonic()<deadline:
            begin=time.monotonic();rows=[]
            for i,name in enumerate(JOINTS,1):
                position=signed_magnitude(read(i,56,2),15);cal=saved['motors'][name]
                value,unit=joint_value(name,position,cal)
                rows.append(dict(name=name,id=i,position_raw=position,value=value,unit=unit,
                    in_calibrated_range=cal['range_min']<=position<=cal['range_max'],
                    torque_enabled=bool(read(i,40,1)),operating_mode=read(i,33,1),
                    load_raw=signed_magnitude(read(i,60,2),10),voltage_v=read(i,62,1)/10,temperature_c=read(i,63,1)))
            sequence+=1
            emit(kind='arm',connected=True,sequence=sequence,motors=rows,calibration_sha256=saved['sha256'],
                 calibration_match=not mismatches,calibration_mismatches=mismatches,
                 sample_duration_ms=(time.monotonic()-begin)*1000,port=port_name,mode='read_only',
                 note='Servo yükü kavrama sensörü olarak henüz doğrulanmadı; eklemler MuJoCo koordinatı değildir.')
            time.sleep(max(0,.25-(time.monotonic()-begin)))
    finally:
        # Deliberately do not call a robot.disconnect() that may disable torque.
        if port.is_open:port.closePort()


def read_camera_frame(camera,deadline,size=(1280,720)):
    """Bound transient read failures; never reuse or resize an old frame.

    The process owner still enforces the worker lifetime if a backend blocks.
    Missing frames emit no heartbeat, so the existing freshness gates expire.
    """
    end=min(deadline,time.monotonic()+3)
    failures=mismatches=0
    observed_size=None
    for _ in range(30):
        if time.monotonic()>=end:break
        ok,frame=camera.read()
        if time.monotonic()>=end:break
        if ok and frame is not None and frame.size:
            observed_size=(frame.shape[1],frame.shape[0])
            if observed_size==size:
                return frame,dict(read_failures=failures,resolution_mismatches=mismatches)
            mismatches+=1
        else:failures+=1
        time.sleep(.02)
    if mismatches:
        raise OSError(f'Kamera çözünürlüğü beklenen {size} ile uyuşmuyor: {observed_size}')
    raise OSError('Kameradan süre sınırı içinde güncel kare alınamadı')


def preview(index,role,duration,session=None,profile=None):
    import cv2
    import json,queue,threading,uuid
    from pathlib import Path
    from .calibration_camera import CameraCalibration
    from .hardware_vision import AccessoryVision
    vision=AccessoryVision()
    session=session or uuid.uuid4().hex
    lens=CameraCalibration(Path(__file__).resolve().parents[1]/'.runtime/hardware/cameras'/role/session,role,index,profile)
    commands=queue.Queue(16)
    def receive():
        try:
            for line in sys.stdin:
                if len(line)>4096:break
                commands.put_nowait(json.loads(line))
        except (ValueError,queue.Full):pass
    threading.Thread(target=receive,daemon=True).start()
    backend=cv2.CAP_AVFOUNDATION if sys.platform=='darwin' else cv2.CAP_ANY
    camera=cv2.VideoCapture(index,backend)
    try:
        if not camera.isOpened():raise OSError('Kamera açılamadı; USB bağlantısı, kamera indeksi ve işletim sistemi iznini kontrol et')
        camera.set(cv2.CAP_PROP_FRAME_WIDTH,1280);camera.set(cv2.CAP_PROP_FRAME_HEIGHT,720)
        camera.set(cv2.CAP_PROP_FPS,15)
        deadline=time.monotonic()+duration;sequence=0
        while time.monotonic()<deadline:
            start=time.monotonic();frame,capture=read_camera_frame(camera,deadline)
            sequence+=1
            # Detect on the unannotated frame, never on calibration overlays.
            observation=vision.observe(frame,sequence)
            frame=lens.observe(frame,sequence)
            while not commands.empty():
                try:lens.command(commands.get_nowait())
                except (ValueError,cv2.error) as exc:lens.warning=str(exc)
            frame=vision.annotate(frame,observation)
            ok,encoded=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,85])
            if not ok:raise OSError('Kamera karesi kodlanamadı')
            emit(kind='camera',role=role,index=index,sequence=sequence,width=frame.shape[1],height=frame.shape[0],
                 image=base64.b64encode(encoded).decode(),source='physical_usb_rgb',depth_available=False,
                 session=session,calibration=lens.state(),perception=observation,capture=capture,
                 note='Kamera adayı; rol ve lens/robot kalibrasyonu henüz doğrulanmadı.')
            time.sleep(max(0,.125-(time.monotonic()-start)))
    finally:camera.release()


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['inventory','arm','camera'])
    p.add_argument('--port');p.add_argument('--calibration');p.add_argument('--sha')
    p.add_argument('--camera-index',type=int);p.add_argument('--role',choices=['wrist','top'])
    p.add_argument('--session');p.add_argument('--camera-profile')
    p.add_argument('--duration',type=int,default=600);a=p.parse_args()
    if not 1<=a.duration<=600:p.error('Tanılama oturumu 1–600 saniye olmalı')
    signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
    try:
        if a.mode=='inventory':inventory()
        elif a.mode=='arm':
            if not all((a.port,a.calibration,a.sha)):p.error('Port, kalibrasyon ve SHA gerekli')
            inspect_arm(a.port,a.calibration,a.sha,a.duration)
        else:
            if a.camera_index is None or not 0<=a.camera_index<=15 or not a.role:p.error('Kamera indeksi 0–15 ve rol gerekli')
            preview(a.camera_index,a.role,a.duration,a.session,a.camera_profile)
    except Exception as exc:
        emit(kind='error',error=f'{type(exc).__name__}: {exc}');raise SystemExit(1)


if __name__=='__main__':main()
