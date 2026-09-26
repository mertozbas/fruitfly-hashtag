"""Isolated STS3215 transport. Construction/open/inspection never enables torque."""
import os
import time
from .hardware_contract import JOINTS,signed_magnitude,compare_calibration,joint_value
from .physical_contract import MAX_LEAD,MAX_STEP,motion_packet,check_pose


class PhysicalBus:
    def __init__(self,name):
        from scservo_sdk import PortHandler,PacketHandler
        class GuardedPort(PortHandler):
            permit=None
            def writePort(self,packet):
                allowed=motion_packet(packet,self.permit);self.permit=None
                return super().writePort(allowed)
            def getCurrentTime(self):return time.monotonic()*1000
        self.port=GuardedPort(name);self.packet=PacketHandler(0);self.enabled=False;self.targets=None;self.configured=False

    def open(self):
        if not self.port.openPort():raise OSError('USB motor portu açılamadı')
        if os.name=='posix':
            import fcntl,termios
            if hasattr(termios,'TIOCEXCL'):fcntl.ioctl(self.port.ser.fileno(),termios.TIOCEXCL)

    def close(self):
        # Stop leaves bounded position holding active; release is a separate supported-arm action.
        if self.port.is_open:self.port.closePort()

    def read(self,i,address,size=2):
        value,comm,error=(self.packet.read1ByteTxRx if size==1 else self.packet.read2ByteTxRx)(self.port,i,address)
        if comm or error:raise OSError(f'Motor {i}: okuma hatası {comm}/{error}')
        return int(value)

    def _write(self,i,address,value,size=2):
        self.port.permit=(i,address,int(value).to_bytes(size,'little'))
        try:
            comm,error=(self.packet.write1ByteTxRx if size==1 else self.packet.write2ByteTxRx)(self.port,i,address,value)
            if comm or error:raise OSError(f'Motor {i}: yazma hatası {comm}/{error}')
        finally:self.port.permit=None
        if self.read(i,address,size)!=value:raise OSError(f'Motor {i}: hareket ayarı geri okunamadı ({address})')

    def positions(self):return [signed_magnitude(self.read(i,56),15) for i in range(1,7)]

    def verify(self,saved):
        actual={}
        for i,name in enumerate(JOINTS,1):
            if self.read(i,3)!=777 or self.read(i,33,1)!=0:raise ValueError(f'Motor {i}: STS3215 / konum modu gerekli')
            actual[name]=dict(id=i,range_min=self.read(i,9),range_max=self.read(i,11),homing_offset=signed_magnitude(self.read(i,31),11))
        if compare_calibration(saved,actual):raise ValueError('Dosya ve motor kalibrasyonu eşleşmiyor')

    def telemetry(self,saved):
        q=self.positions();rows=[]
        for i,(name,p) in enumerate(zip(JOINTS,q),1):
            value,unit=joint_value(name,p,saved[name]);m=saved[name]
            rows.append(dict(name=name,id=i,position_raw=p,value=value,unit=unit,in_calibrated_range=m['range_min']<=p<=m['range_max'],
                torque_enabled=bool(self.read(i,40,1)),temperature_c=self.read(i,63,1),voltage_v=self.read(i,62,1)/10,
                load_raw=signed_magnitude(self.read(i,60),10),operating_mode=self.read(i,33,1)))
        return q,rows

    def enable_at_current(self,expected,bounds):
        q=self.positions();check_pose(q,bounds)
        if max(abs(a-b) for a,b in zip(q,expected))>3:raise ValueError('Kol onaydan sonra hareket etti; yeniden önizle')
        if any(self.read(i,40,1) for i in range(1,7)):raise ValueError('Başlatmadan önce motor torku kapalı olmalı')
        # Latch current position and low speed BEFORE torque-on. No EEPROM writes.
        for i,p in enumerate(q,1):
            existing=self.read(i,48);ceiling=self.read(i,16)
            cap=min(existing,ceiling,250 if i==6 else 500)
            if cap<=0:raise ValueError(f'Motor {i}: geçerli tork sınırı okunamadı')
            self._write(i,46,50);self._write(i,44,0);self._write(i,48,cap);self._write(i,42,p)
        self.configured=True;self.targets=q.copy()
        if max(abs(a-b) for a,b in zip(self.positions(),q))>3:raise ValueError('Tork açılmadan kol hareket etti; yeniden önizle')
        # Mark ownership before first enable, including partial bus failures.
        self.enabled=True
        for i in range(1,7):self._write(i,40,1,1)
        return q

    def goal(self,target,bounds):
        if not self.enabled or not self.configured:raise PermissionError('Onaylanmış tork oturumu gerekli')
        check_pose(target,bounds);q=self.positions()
        if max(abs(a-b) for a,b in zip(target,self.targets))>MAX_STEP:raise ValueError('Tek komut adımı aşıldı')
        if max(abs(a-b) for a,b in zip(target,q))>MAX_LEAD:raise ValueError('Motor hedefi izleyemiyor; hareket durdu')
        for i,p in enumerate(target,1):
            if self.read(i,40,1)!=1:raise OSError(f'Motor {i}: tork kaybı')
            self._write(i,42,p)
        self.targets=target.copy()

    def hold(self):
        # No distant target on stop. If bus fails, the last target was <=8 counts ahead.
        if not self.enabled:return
        q=self.positions()
        if max(abs(a-b) for a,b in zip(q,self.targets))>16:raise OSError('Motor tutma konumundan uzaklaştı; gücü güvenle kes')
        for i,p in enumerate(q,1):self._write(i,42,p)
        self.targets=q

    def release(self):
        for i in range(1,7):self._write(i,40,0,1)
        self.enabled=False;self.configured=False;self.targets=None
