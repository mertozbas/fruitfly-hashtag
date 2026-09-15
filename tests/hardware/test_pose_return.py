"""Recorded-pose restoration against a virtual SDK wire; no hardware I/O."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_alignment_probe import Wire,Clock
from so101.hardware_contract import JOINTS
from so101.pose_hold import RecordedReturnBus,return_recorded_pose,recorded_return_target


class ReturnTests(unittest.TestCase):
    def setUp(self):
        self.wire=Wire();self.clock=Clock()
        self.saved={n:dict(id=i,drive_mode=0,range_min=700,range_max=3400,homing_offset=0) for i,n in enumerate(JOINTS,1)}
        for i in range(1,6):self.wire.registers[i].update({40:1,42:2000,44:0,46:20,48:500})
        for target in ('serial.Serial','fcntl.ioctl'):
            p=patch(target,return_value=self.wire if target=='serial.Serial' else None);p.start();self.addCleanup(p.stop)
        self.bus=RecordedReturnBus('OFFLINE_TEST',4,1995)
    def run_it(self,check=lambda:None,save=lambda r:None):
        return return_recorded_pose(self.bus,self.saved,[2000]*6,check,save,self.clock,self.clock.sleep)

    def test_returns_inside_old_interval_and_waits_without_other_writes(self):
        before=copy.deepcopy(self.wire.registers);r=self.run_it()
        self.assertEqual(r['status'],'returned_to_reference');self.assertEqual(r['return_error_counts'],0)
        self.assertGreaterEqual(self.clock(),2.6);self.assertFalse(r['brain_connected']);self.assertFalse(r['joint_mapping_verified'])
        self.assertTrue(all((i,a)==(4,42) and 1995<=v<=2000 for i,a,v in self.wire.writes))
        for i in (1,2,3,5,6):self.assertEqual(self.wire.registers[i],before[i])
        self.assertTrue(self.wire.registers[4][40]);self.assertTrue(r['calibration_preserved'])

    def test_stalled_joint_not_retried_beyond_recorded_target(self):
        self.wire.stall=True;r=self.run_it()
        self.assertEqual(r['status'],'return_outside_tolerance');self.assertEqual(r['return_error_counts'],5)
        self.assertFalse(r['motion_observed']);self.assertEqual(self.wire.registers[4][42],2000)
        self.assertEqual([v for _,_,v in self.wire.writes],[2000,1998,1996,1995,2000])

    def test_camera_loss_holds_measured_position_without_releasing_torque(self):
        def lost():
            if self.bus.last_goal==1998:raise ValueError('Camera lost')
        r=self.run_it(lost);self.assertEqual(r['status'],'failed')
        self.assertEqual(self.wire.registers[4][42],1998)
        self.assertTrue(all((i,a)==(4,42) for i,a,_ in self.wire.writes))

    def test_reference_too_far_and_missing_audit_cannot_move(self):
        self.bus.target=1991;r=self.run_it();self.assertEqual(r['status'],'failed');self.assertEqual(self.wire.writes,[])
        self.bus=RecordedReturnBus('OFFLINE_TEST',4,1995)
        def bad_save(r):
            if r['status']=='prepared':raise OSError('Disk full')
        r=self.run_it(save=bad_save);self.assertEqual(r['status'],'failed');self.assertEqual(self.wire.writes,[])

    def test_packet_boundary_rejects_expansion_other_motor_and_eeprom(self):
        self.bus.open();self.addCleanup(self.bus.close);self.bus.phase='move';self.bus.initial=self.bus.last_goal=2000
        for i,a,v in ((4,42,1994),(4,42,2001),(5,42,1998),(6,42,1998),(4,31,1998),(4,46,1998),(4,42,1997)):
            data=v.to_bytes(2,'little');b=[i,5,3,a,*data];self.bus.permit=(a,data)
            with self.assertRaises(PermissionError):self.bus.guard(bytes([255,255,*b,(~sum(b))&255]))
        self.assertEqual(self.wire.writes,[])

    def test_reference_is_pinned_to_prior_robot_joint_and_measured_pose(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous=Path.cwd();os.chdir(tmp)
            try:
                ref=Path('.runtime/hardware/probes/test');ref.mkdir(parents=True)
                prior=dict(kind='held_joint_probe_v1',motor_id=4,port='OFFLINE_TEST',serial_number='TEST',calibration_sha256='cal')
                result=dict(status='return_outside_tolerance',motor_id=4,initial=[2000,2000,2000,1995,2000,2000],calibration_preserved=True)
                a=json.dumps(prior).encode();b=json.dumps(result).encode();(ref/'plan.json').write_bytes(a);(ref/'result.json').write_bytes(b)
                plan=dict(prior,reference_plan=str(ref/'plan.json'),reference_sha256=hashlib.sha256(a+b).hexdigest(),q=[2000]*6)
                self.assertEqual(recorded_return_target(plan),1995)
                with self.assertRaises(ValueError):recorded_return_target(dict(plan,motor_id=3))
                with self.assertRaises(ValueError):recorded_return_target(dict(plan,serial_number='OTHER'))
                with self.assertRaises(ValueError):recorded_return_target(dict(plan,q=[2000,2008,2000,2000,2000,2000]))
                (ref/'result.json').write_text('{}')
                with self.assertRaises(ValueError):recorded_return_target(plan)
            finally:os.chdir(previous)


if __name__=='__main__':unittest.main()
