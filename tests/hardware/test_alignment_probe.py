"""Fixed wrist probe through the installed SDK, against a virtual serial bus."""
import copy
import tempfile
import unittest
from unittest.mock import patch
from so101.alignment_probe import ProbeBus,run_probe
from so101.hardware_contract import JOINTS


class Wire:
    def __init__(self):
        self.registers={i:{3:777,9:700,11:3400,31:0,33:0,40:0,44:0,46:0,48:1000,16:1000,56:2000,62:124,63:35,42:3000} for i in range(1,7)}
        self.buffer=bytearray();self.writes=[];self.fail=None;self.stall=False
    @property
    def in_waiting(self):return len(self.buffer)
    def read(self,n):v=self.buffer[:n];del self.buffer[:n];return bytes(v)
    def reset_input_buffer(self):self.buffer.clear()
    def flush(self):pass
    def close(self):pass
    def fileno(self):return 0
    def write(self,p):
        p=bytes(p);i=p[2];op=p[4];a=p[5];error=0;data=[]
        if op==2:data=list(self.registers[i][a].to_bytes(p[6],'little'))
        elif op==3:
            v=int.from_bytes(p[6:-1],'little');self.writes.append((i,a,v))
            if self.fail==(i,a):error=32;self.fail=None
            else:
                self.registers[i][a]=v
                if a==42 and self.registers[i][40] and not self.stall:self.registers[i][56]=v
                if a==40 and v==1:self.registers[i][56]=self.registers[i][42]
        else:raise AssertionError('Unexpected instruction')
        r=[i,len(data)+2,error,*data];self.buffer.extend([255,255,*r,(~sum(r))&255]);return len(p)


class Clock:
    def __init__(self):self.now=0.
    def __call__(self):return self.now
    def sleep(self,t):self.now+=t


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.wire=Wire();self.saved={n:dict(id=i,drive_mode=0,range_min=700,range_max=3400,homing_offset=0) for i,n in enumerate(JOINTS,1)}
        self.before=copy.deepcopy(self.wire.registers);self.clock=Clock();self.records=[]
        p=patch('serial.Serial',return_value=self.wire);p.start();self.addCleanup(p.stop)
        p=patch('fcntl.ioctl');p.start();self.addCleanup(p.stop)
        self.bus=ProbeBus('OFFLINE_TEST');self.addCleanup(self.bus.close)
    def run_it(self,check=lambda:None,save=None,expected=None):
        def audit(record):self.records.append(copy.deepcopy(record))
        return run_probe(self.bus,self.saved,expected or [2000]*6,check,save or audit,self.clock,self.clock.sleep)

    def test_roundtrip_latches_before_enable_and_restores_torque_off(self):
        result=self.run_it();self.assertEqual(result['status'],'passed');self.assertEqual(result['measured_peak_counts'],8)
        self.assertFalse(result['brain_connected']);self.assertFalse(result['joint_mapping_verified'])
        self.assertEqual(self.wire.registers,self.before|{5:{**self.before[5],42:2000}})
        self.assertTrue(all(i==5 for i,_,_ in self.wire.writes))
        goals=[v for _,a,v in self.wire.writes if a==42]
        self.assertTrue(all(2000<=v<=2008 for v in goals));self.assertTrue(all(abs(a-b)<=2 for a,b in zip(goals,goals[1:])))
        self.assertLess(self.wire.writes.index((5,42,2000)),self.wire.writes.index((5,40,1)))

    def test_audit_failure_before_writes_never_enables(self):
        def save(record):
            if record['status']=='prepared':raise OSError('Disk full')
        self.assertEqual(self.run_it(save=save)['status'],'failed');self.assertEqual(self.wire.writes,[])

    def test_wrong_identity_range_voltage_or_initial_pose_never_writes(self):
        for a,value in [(3,999),(9,900),(56,3500),(62,150),(40,1),(33,1),(63,55)]:
            with self.subTest(register=a):
                self.wire.registers=copy.deepcopy(self.before);self.wire.registers[1][a]=value
                self.bus=ProbeBus('OFFLINE_TEST');self.assertEqual(self.run_it()['status'],'failed');self.assertEqual(self.wire.writes,[])

    def test_camera_loss_stops_and_disables_only_wrist(self):
        def lost():
            if self.bus.may_be_on:raise ValueError('Camera lost')
        result=self.run_it(check=lost);self.assertEqual(result['status'],'failed')
        self.assertFalse(result['torque_may_be_on']);self.assertEqual(self.wire.registers[5][40],0)
        self.assertTrue(all(i==5 for i,_,_ in self.wire.writes))

    def test_stall_never_reports_motion_and_does_not_expand_range(self):
        self.wire.stall=True;result=self.run_it();self.assertEqual(result['status'],'no_confirmed_motion')
        self.assertEqual(result['measured_peak_counts'],0);self.assertEqual(self.wire.registers[5][40],0)
        self.assertTrue(all(v<=2008 for _,a,v in self.wire.writes if a==42))

    def test_write_failure_never_proceeds_to_enable(self):
        self.wire.fail=(5,42);result=self.run_it();self.assertEqual(result['status'],'failed')
        self.assertNotIn((5,40,1),self.wire.writes);self.assertEqual(self.wire.registers[5][40],0)

    def test_enable_failure_still_requests_off(self):
        self.wire.fail=(5,40);result=self.run_it();self.assertEqual(result['status'],'failed')
        self.assertEqual(self.wire.registers[5][40],0);self.assertFalse(result['torque_may_be_on'])

    def test_changed_other_joint_interrupts_probe(self):
        def moved():
            if self.bus.may_be_on:self.wire.registers[2][56]=2010
        result=self.run_it(check=moved);self.assertEqual(result['status'],'failed');self.assertEqual(self.wire.registers[5][40],0)
        self.assertTrue(all(i==5 for i,_,_ in self.wire.writes))

    def test_off_failure_reported_without_restoring_limits(self):
        def lost():
            if self.bus.may_be_on:
                self.wire.fail=(5,40);raise ValueError('Camera lost')
        result=self.run_it(check=lost)
        self.assertEqual(result['status'],'failed');self.assertTrue(result['torque_may_be_on'])
        self.assertTrue(result['cleanup_errors']);self.assertEqual(self.wire.registers[5][48],100)

    def test_slow_preflight_never_writes(self):
        result=self.run_it(check=lambda:self.clock.sleep(.2))
        self.assertEqual(result['status'],'failed');self.assertEqual(self.wire.writes,[])

    def test_durable_record_precedes_first_write(self):
        def save(record):
            if record['status']=='prepared':self.assertEqual(self.wire.writes,[])
        self.assertEqual(self.run_it(save=save)['status'],'passed')

    def test_packet_gate_blocks_other_ids_eeprom_unlimited_speed_and_large_goal(self):
        self.bus.open()
        def packet(i,a,v,size=2):
            data=list(v.to_bytes(size,'little'));b=[i,len(data)+3,3,a,*data];return bytes([255,255,*b,(~sum(b))&255])
        for phase,i,a,v,size in [('setup',1,42,2000,2),('setup',5,31,10,2),('setup',5,46,0,2),('read',5,40,1,1),('move',5,42,2010,2),('move',5,42,1999,2)]:
            self.bus.phase=phase;self.bus.initial=self.bus.last_goal=2000;self.bus.permit=(a,v.to_bytes(size,'little'))
            with self.assertRaises(PermissionError):self.bus.port.writePort(packet(i,a,v,size))
        self.assertEqual(self.wire.writes,[])


if __name__=='__main__':unittest.main()
