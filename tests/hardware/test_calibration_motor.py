"""Full calibration against a virtual STS3215 bus through the installed SDK."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from so101.calibration_contract import atomic_bytes,atomic_json,calibration_packet,digest
from so101.calibration_motor import CalibrationBus,MotorCalibration
from so101.hardware_contract import JOINTS,signed_magnitude


class VirtualSerial:
    def __init__(self):
        self.registers={i:{3:777,9:700,11:3400,31:2048+188,33:0,40:1,55:1} for i in range(1,7)}
        self.actual={i:2200+i*10 for i in range(1,7)};self.buffer=bytearray();self.writes=[];self.fail_at=None
    @property
    def in_waiting(self):return len(self.buffer)
    def flush(self):pass
    def reset_input_buffer(self):self.buffer.clear()
    def close(self):pass
    def fileno(self):return 0
    def read(self,n):data=self.buffer[:n];del self.buffer[:n];return bytes(data)
    def write(self,packet):
        p=bytes(packet);motor=p[2];op=p[4];address=p[5];error=0;payload=[]
        if op==2:
            value=self.actual[motor]-signed_magnitude(self.registers[motor][31],11) if address==56 else self.registers[motor][address]
            payload=list(int(value).to_bytes(p[6],'little'))
        elif op==3:
            data=p[6:-1];calibration_packet(p,(motor,address,data));value=int.from_bytes(data,'little');self.writes.append((motor,address,value))
            if self.fail_at==(motor,address):error=32;self.fail_at=None
            else:self.registers[motor][address]=value
        else:raise AssertionError('Unexpected motor instruction')
        response=[motor,len(payload)+2,error,*payload];self.buffer.extend([255,255,*response,(~sum(response))&255]);return len(p)


class CalibrationMotorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.serial=VirtualSerial();self.serial_patch=patch('serial.Serial',return_value=self.serial);self.serial_patch.start();self.addCleanup(self.serial_patch.stop)
        self.ioctl_patch=patch('fcntl.ioctl');self.ioctl_patch.start();self.addCleanup(self.ioctl_patch.stop)
        self.target=self.root/'follower.json'
        self.original={n:dict(id=i,drive_mode=0,homing_offset=-188,range_min=700,range_max=3400) for i,n in enumerate(JOINTS,1)}
        self.target.write_text(json.dumps(self.original,indent=4));self.original_bytes=self.target.read_bytes()
        self.bus=CalibrationBus('OFFLINE_TEST');self.addCleanup(self.bus.close)
        self.session=MotorCalibration(self.bus,self.target,self.root/'session',dict(serial_number='VIRTUAL'))
        self.session.start();self.before=copy.deepcopy(self.serial.registers)

    def command(self,op,**kw):self.session.command(dict(op=op,revision=self.session.revision,**kw))
    def measure(self):
        self.command('release',supported=True);self.command('reference',supported=True)
        while self.session.stage=='ranges':
            name=self.session.current;i=JOINTS.index(name)+1;offset=signed_magnitude(self.serial.registers[i][31],11)
            for value in [1100,1400,1800,2100,2600,3000]*3:
                self.serial.actual[i]=value+offset;self.session.sample()
            self.command('next',range_confirmed=True)

    def assert_restored(self):
        for i in range(1,7):
            for address in (9,11,31,33):self.assertEqual(self.serial.registers[i][address],self.before[i][address])
            self.assertEqual(self.serial.registers[i][40],0)

    def test_backup_before_any_write_and_explicit_release(self):
        self.assertEqual(self.serial.writes,[]);self.assertTrue((self.root/'session/backup.json').is_file())
        with self.assertRaises(ValueError):self.command('release')
        self.assertEqual(self.serial.writes,[])
        self.command('release',supported=True);self.assertTrue(all(self.serial.registers[i][40]==0 for i in range(1,7)))
        self.assertFalse(any(address==40 and value!=0 for _,address,value in self.serial.writes))

    def test_full_measurement_save_readback_and_wrist_exception(self):
        self.measure();self.assertEqual(self.session.stage,'review')
        self.assertEqual(self.target.read_bytes(),self.original_bytes)
        self.command('save',confirmed=True);self.assertEqual(self.session.stage,'saved')
        result=json.loads(self.target.read_text());self.assertEqual(result['wrist_roll']['range_min'],0);self.assertEqual(result['wrist_roll']['range_max'],4095)
        for i,name in enumerate(JOINTS,1):
            self.assertEqual(self.serial.registers[i][9],result[name]['range_min'])
            self.assertEqual(self.serial.registers[i][40],0);self.assertEqual(self.serial.registers[i][55],1)
        self.session.cancel();self.assertEqual(self.session.stage,'saved')

    def test_incomplete_ranges_and_stale_commands_rejected(self):
        self.command('release',supported=True);self.command('reference',supported=True);self.session.sample()
        with self.assertRaisesRegex(ValueError,'yetersiz'):self.command('next',range_confirmed=True)
        with self.assertRaisesRegex(ValueError,'Adım değişti'):self.session.command(dict(op='save',revision=0,confirmed=True))
        self.session.cancel();self.assert_restored();self.assertEqual(self.target.read_bytes(),self.original_bytes)

    def test_partial_eeprom_failure_rolls_back_without_enabling_torque(self):
        self.measure();self.serial.fail_at=(3,9)
        with self.assertRaises(OSError):self.command('save',confirmed=True)
        self.session.cancel();self.assert_restored();self.assertEqual(self.target.read_bytes(),self.original_bytes)

    def test_external_file_edit_is_preserved(self):
        self.measure();external=b'{"external":"change"}';self.target.write_bytes(external)
        with self.assertRaisesRegex(OSError,'dışarıdan'):self.command('save',confirmed=True)
        self.session.cancel();self.assert_restored();self.assertEqual(self.target.read_bytes(),external)

    def test_rollback_failure_is_persisted_as_failure(self):
        self.command('release',supported=True);self.command('reference',supported=True);self.serial.fail_at=(1,31)
        self.session.cancel();self.assertEqual(self.session.stage,'failed');self.assertTrue(self.session.errors)
        self.assertEqual(json.loads((self.root/'session/status.json').read_text())['stage'],'failed')

    def test_restore_backup_preserves_original_file_bytes(self):
        backup=json.loads((self.root/'session/backup.json').read_text());self.measure();self.command('save',confirmed=True);self.bus.close()
        self.session=MotorCalibration(CalibrationBus('OFFLINE_TEST'),self.target,self.root/'restore',dict(serial_number='VIRTUAL'),backup)
        self.addCleanup(self.session.bus.close);self.session.start();self.command('release',supported=True);self.command('restore',confirmed=True)
        self.assertEqual(self.session.stage,'restored');self.assertEqual(self.target.read_bytes(),self.original_bytes);self.assert_restored()

    def test_bus_rejects_goal_torque_on_and_unpermitted_writes(self):
        for address,value,size in ((42,2048,2),(40,1,1),(5,1,1)):
            with self.assertRaises(PermissionError):self.bus.write(1,address,value,size)
        self.assertEqual(self.serial.writes,[])

    def test_profile_change_during_backup_never_releases_torque(self):
        other=MotorCalibration(self.bus,self.target,self.root/'race',dict(serial_number='VIRTUAL'))
        self.target.write_text('{"external":true}')
        with self.assertRaises(OSError):other.start()
        self.assertEqual(self.serial.writes,[]);self.assertFalse((self.root/'race/backup.json').exists())

    def test_corrupt_backup_and_wrong_motor_ids_rejected_before_writes(self):
        original=json.loads((self.root/'session/backup.json').read_text())
        for corrupt in ('sha','id'):
            backup=copy.deepcopy(original)
            if corrupt=='sha':backup['file_sha256']='0'*64
            else:backup['motors']['gripper']['id']=1
            other=MotorCalibration(self.bus,self.target,self.root/corrupt,dict(serial_number='VIRTUAL'),backup)
            with self.assertRaises(ValueError):other.start()
            self.assertEqual(self.serial.writes,[])

    def test_post_rename_failure_restores_file_and_motors(self):
        self.measure();failed=False
        def fail_after_replace(path,raw):
            nonlocal failed
            atomic_bytes(path,raw)
            if Path(path)==self.target and not failed:
                failed=True;raise OSError('Injected directory fsync failure')
        with patch('so101.calibration_motor.atomic_bytes',side_effect=fail_after_replace):
            with self.assertRaises(OSError):self.command('save',confirmed=True)
            self.session.cancel()
        self.assert_restored();self.assertEqual(self.target.read_bytes(),self.original_bytes)

    def test_status_failure_after_save_is_not_a_success(self):
        self.measure();failed=False
        def fail_terminal_status(path,record):
            nonlocal failed
            if record.get('stage')=='saved' and not failed:
                failed=True;raise OSError('Injected status write failure')
            atomic_json(path,record)
        with patch('so101.calibration_motor.atomic_json',side_effect=fail_terminal_status):
            with self.assertRaises(OSError):self.command('save',confirmed=True)
            self.assertEqual(self.session.stage,'review');self.session.cancel()
        self.assert_restored();self.assertEqual(self.target.read_bytes(),self.original_bytes)


if __name__=='__main__':unittest.main()
