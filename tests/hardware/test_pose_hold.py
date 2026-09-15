"""Static pose holding tests on a virtual SDK wire, never physical hardware."""
import copy
import unittest
from unittest.mock import patch
from test_alignment_probe import Wire,Clock
from so101.pose_hold import HoldBus,HeldWristProbeBus,HeldJointProbeBus,hold_current
from so101.alignment_probe import run_probe
from so101.hardware_contract import JOINTS


class HoldTests(unittest.TestCase):
    def setUp(self):
        self.wire=Wire();self.clock=Clock();self.records=[]
        self.saved={n:dict(id=i,drive_mode=0,range_min=700,range_max=3400,homing_offset=0) for i,n in enumerate(JOINTS,1)}
        for target in ('serial.Serial','fcntl.ioctl'):
            p=patch(target,return_value=self.wire if target=='serial.Serial' else None);p.start();self.addCleanup(p.stop)
        self.bus=HoldBus('OFFLINE_TEST');self.addCleanup(self.bus.close)
    def run_it(self,check=lambda:None,save=None):
        return hold_current(self.bus,self.saved,[2000]*6,check,save or (lambda r:self.records.append(copy.deepcopy(r))),self.clock,self.clock.sleep)

    def test_latch_all_current_targets_before_any_enable_gripper_never_written(self):
        result=self.run_it();self.assertEqual(result['status'],'holding_at_measured_pose')
        self.assertEqual(result['torque_after'],[True]*5+[False]);self.assertFalse(result['brain_connected'])
        first=next(i for i,(_,a,_) in enumerate(self.wire.writes) if a==40)
        self.assertEqual({i for i,a,v in self.wire.writes[:first] if a==42 and v==2000},set(range(1,6)))
        self.assertTrue(all(i!=6 for i,_,_ in self.wire.writes))
        self.assertTrue(all(v==2000 for _,a,v in self.wire.writes if a==42))
        self.assertTrue(all(a in (40,42,44,46,48) for _,a,_ in self.wire.writes))

    def test_failed_audit_prevents_all_writes(self):
        def save(r):
            if r['status']=='prepared':raise OSError('Disk full')
        self.assertEqual(self.run_it(save=save)['status'],'failed');self.assertEqual(self.wire.writes,[])

    def test_failed_configuration_never_enables(self):
        self.wire.fail=(3,42);result=self.run_it();self.assertEqual(result['status'],'failed')
        self.assertEqual(result['torque_after'],[False]*6);self.assertFalse(any(a==40 for _,a,_ in self.wire.writes))

    def test_camera_loss_after_enable_never_drops_supporting_arm(self):
        def lost():
            if self.bus.phase=='holding':raise ValueError('Lost camera')
        result=self.run_it(check=lost);self.assertEqual(result['status'],'failed')
        self.assertEqual(result['torque_after'],[True]*5+[False])
        self.assertNotIn(0,[v for _,a,v in self.wire.writes if a==40])

    def test_partial_enable_failure_is_reported_with_actual_torque_states(self):
        self.wire.fail=(3,40);result=self.run_it();self.assertEqual(result['status'],'failed')
        self.assertEqual(result['torque_after'],[True,True,False,False,False,False])

    def test_initial_torque_on_rejected(self):
        self.wire.registers[1][40]=1;result=self.run_it();self.assertEqual(result['status'],'failed');self.assertEqual(self.wire.writes,[])

    def test_gripper_and_nonmeasured_targets_blocked_at_packet_boundary(self):
        self.bus.open();self.bus.phase='setup';self.bus.q0=[2000]*6;self.bus.caps={i:500 for i in range(1,6)}
        for i,a,v in ((6,42,2000),(1,42,2001),(1,31,2000),(1,46,0)):
            data=v.to_bytes(2,'little');b=[i,5,3,a,*data];self.bus.permit=(i,a,data)
            with self.assertRaises(PermissionError):self.bus.guard(bytes([255,255,*b,(~sum(b))&255]))
        self.assertEqual(self.wire.writes,[])

    def test_held_probe_returns_without_releasing_support_or_writing_other_motors(self):
        for i in range(1,6):self.wire.registers[i].update({40:1,42:2000,44:0,46:20,48:500})
        before=copy.deepcopy(self.wire.registers);bus=HeldWristProbeBus('OFFLINE_TEST')
        result=run_probe(bus,self.saved,[2000]*6,lambda:None,lambda r:None,self.clock,self.clock.sleep)
        self.assertEqual(result['status'],'passed');self.assertEqual(self.wire.registers,before)
        self.assertTrue(all((i,a)==(5,42) for i,a,_ in self.wire.writes))

    def test_held_probe_camera_loss_keeps_support_and_stops_at_current_wrist(self):
        for i in range(1,6):self.wire.registers[i].update({40:1,42:2000,44:0,46:20,48:500})
        bus=HeldWristProbeBus('OFFLINE_TEST')
        def lost():
            if bus.last_goal==2004:raise ValueError('Lost camera')
        result=run_probe(bus,self.saved,[2000]*6,lost,lambda r:None,self.clock,self.clock.sleep)
        self.assertEqual(result['status'],'failed');self.assertEqual(self.wire.registers[5][42],2004)
        self.assertTrue(all(self.wire.registers[i][40] for i in range(1,6)));self.assertEqual(self.wire.registers[6][40],0)

    def test_held_probe_requires_existing_limited_hold(self):
        bus=HeldWristProbeBus('OFFLINE_TEST')
        result=run_probe(bus,self.saved,[2000]*6,lambda:None,lambda r:None,self.clock,self.clock.sleep)
        self.assertEqual(result['status'],'failed');self.assertEqual(self.wire.writes,[])

    def test_each_body_joint_isolated_and_returns_without_other_writes(self):
        for motor_id in range(1,5):
            with self.subTest(motor_id=motor_id):
                self.wire.writes.clear()
                for i in range(1,6):self.wire.registers[i].update({40:1,42:2000,56:2000,44:0,46:20,48:500})
                before=copy.deepcopy(self.wire.registers)
                bus=HeldJointProbeBus('OFFLINE_TEST',motor_id)
                result=run_probe(bus,self.saved,[2000]*6,lambda:None,lambda r:None,self.clock,self.clock.sleep)
                self.assertEqual(result['status'],'passed');self.assertEqual(result['commanded_joint'],JOINTS[motor_id-1])
                self.assertEqual(result['measured_peak_counts'],8);self.assertEqual(self.wire.registers,before)
                self.assertFalse(result['joint_mapping_verified']);self.assertFalse(result['brain_connected'])
                self.assertTrue(all((i,a)==(motor_id,42) for i,a,_ in self.wire.writes))
                self.assertTrue(all(2000<=v<=2008 for _,_,v in self.wire.writes))

    def test_held_joint_packet_rejects_other_motor_gripper_torque_and_eeprom(self):
        bus=HeldJointProbeBus('OFFLINE_TEST',4);bus.open();self.addCleanup(bus.close)
        bus.phase='move';bus.initial=bus.last_goal=2000
        for i,a,v in ((5,42,2002),(6,42,2002),(4,40,0),(4,31,0),(4,42,2010),(4,42,1999),(4,42,2004)):
            data=v.to_bytes(2,'little');b=[i,5,3,a,*data];bus.permit=(a,data)
            with self.assertRaises(PermissionError):bus.guard(bytes([255,255,*b,(~sum(b))&255]))
        self.assertEqual(self.wire.writes,[])

    def test_held_joint_camera_loss_holds_current_and_never_releases_body(self):
        for i in range(1,6):self.wire.registers[i].update({40:1,42:2000,44:0,46:20,48:500})
        bus=HeldJointProbeBus('OFFLINE_TEST',4)
        def lost():
            if bus.last_goal==2004:raise ValueError('Lost camera')
        result=run_probe(bus,self.saved,[2000]*6,lost,lambda r:None,self.clock,self.clock.sleep)
        self.assertEqual(result['status'],'failed');self.assertEqual(self.wire.registers[4][42],2004)
        self.assertTrue(all((i,a)==(4,42) for i,a,_ in self.wire.writes))
        self.assertTrue(all(self.wire.registers[i][40] for i in range(1,6)));self.assertFalse(self.wire.registers[6][40])

    def test_unsettled_target_and_stall_are_not_retried_or_enlarged(self):
        for i in range(1,6):self.wire.registers[i].update({40:1,42:2000,44:0,46:20,48:500})
        self.wire.registers[4][42]=1995
        bus=HeldJointProbeBus('OFFLINE_TEST',4)
        result=run_probe(bus,self.saved,[2000]*6,lambda:None,lambda r:None,self.clock,self.clock.sleep)
        self.assertEqual(result['status'],'failed');self.assertEqual(self.wire.writes,[])
        self.wire.registers[4][42]=2000;self.wire.stall=True
        bus=HeldJointProbeBus('OFFLINE_TEST',4)
        result=run_probe(bus,self.saved,[2000]*6,lambda:None,lambda r:None,self.clock,self.clock.sleep)
        self.assertEqual(result['status'],'no_confirmed_motion');self.assertEqual(result['measured_peak_counts'],0)
        self.assertLessEqual(max(v for _,_,v in self.wire.writes),2008)

    def test_motion_with_return_error_is_reported_separately_from_no_motion(self):
        for i in range(1,6):self.wire.registers[i].update({40:1,42:2000,44:0,46:20,48:500})
        bus=HeldJointProbeBus('OFFLINE_TEST',4)
        def stick_on_return():
            if self.wire.registers[4][56]>=2008:self.wire.stall=True
        result=run_probe(bus,self.saved,[2000]*6,stick_on_return,lambda r:None,self.clock,self.clock.sleep)
        self.assertEqual(result['status'],'return_outside_tolerance')
        self.assertTrue(result['motion_observed']);self.assertEqual(result['return_error_counts'],8)
        self.assertEqual(self.wire.registers[4][42],2008)
        self.assertTrue(all((i,a)==(4,42) for i,a,_ in self.wire.writes))

    def test_joint_selection_excludes_gripper_and_invalid_ids(self):
        for i in (0,6,True,4.0,'4'):
            with self.assertRaises(ValueError):HeldJointProbeBus('OFFLINE_TEST',i)


if __name__=='__main__':unittest.main()
