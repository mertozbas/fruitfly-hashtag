"""Empty-gripper opening through the real SDK and virtual serial packets."""
import unittest
from unittest.mock import patch

from test_alignment_probe import Wire,Clock
from so101.gripper_control import GripperBus,GripperOpening
from so101.hardware_contract import JOINTS


class GripperTests(unittest.TestCase):
    def setUp(self):
        self.wire=Wire();self.clock=Clock()
        self.saved={n:dict(id=i,drive_mode=0,range_min=700,range_max=3400,homing_offset=0)
                    for i,n in enumerate(JOINTS,1)}
        for i in range(1,7):self.wire.registers[i].update({40:int(i<6),42:2000,44:0,46:20,48:500,60:0,65:0})
        for name in ('serial.Serial','fcntl.ioctl'):
            p=patch(name,return_value=self.wire if name=='serial.Serial' else None);p.start();self.addCleanup(p.stop)
        self.bus=GripperBus('OFFLINE_TEST');self.addCleanup(self.bus.close)
        self.target=[2000]*5+[2064]
        self.motion=GripperOpening(self.bus,self.saved,[2000]*6,self.target,empty_gripper=True,clock=self.clock)

    def step(self,source=.1,heartbeat=0):
        self.clock.sleep(.1);return self.motion.step(0,True,heartbeat,source)

    def test_opens_only_gripper_latches_before_enable_and_restores_off(self):
        self.motion.start()
        for _ in range(60):
            result=self.step()
            if result['complete']:break
        self.assertTrue(result['complete']);self.motion.stop()
        self.assertEqual(self.wire.registers[6][56],2064)
        self.assertEqual({i for i,_,_ in self.wire.writes},{6})
        self.assertTrue(all(self.wire.registers[i][40] for i in range(1,6)))
        self.assertEqual(self.wire.registers[6][40],0)
        for a,v in ((44,0),(46,20),(48,500)):self.assertEqual(self.wire.registers[6][a],v)
        self.assertLess(self.wire.writes.index((6,42,2000)),self.wire.writes.index((6,40,1)))
        self.assertIn((6,48,100),self.wire.writes)
        goals=[v for _,a,v in self.wire.writes if a==42]
        self.assertTrue(all(0<=b-a<=2 for a,b in zip(goals,goals[1:])))
        self.assertFalse(self.motion.brain_driven)

    def test_empty_confirmation_and_target_scope_are_required_before_writes(self):
        with self.assertRaises(ValueError):GripperOpening(self.bus,self.saved,[2000]*6,self.target)
        for target in (None,[2000]*5,[2000.]*6,[2000]*5+[1990],[2001]+[2000]*4+[2064],[2000]*5+[2129]):
            with self.assertRaises(ValueError):
                GripperOpening(self.bus,self.saved,[2000]*6,target,empty_gripper=True).start()
        self.assertEqual(self.wire.writes,[])

    def test_warm_preflight_never_enables_or_writes(self):
        self.wire.registers[6][63]=50
        with self.assertRaises(ValueError):self.motion.start()
        self.motion.stop();self.assertEqual(self.wire.writes,[])

    def test_runtime_heat_load_camera_and_body_drift_stop_progress(self):
        self.motion.start();self.step();writes=list(self.wire.writes)
        for i,a,v in ((6,63,50),(6,60,81),(1,56,2009),(2,40,0),(3,65,1)):
            old=self.wire.registers[i][a];self.wire.registers[i][a]=v
            with self.assertRaises(ValueError):self.step()
            self.wire.registers[i][a]=old
        with self.assertRaises(ValueError):self.step(source=.5)
        with self.assertRaises(ValueError):self.step(heartbeat=1.1)
        self.assertEqual(self.wire.writes,writes);self.motion.stop()
        self.assertEqual(self.wire.registers[6][40],0)
        self.assertTrue(all(self.wire.registers[i][40] for i in range(1,6)))

    def test_stall_keeps_eight_count_lead_then_turns_only_gripper_off(self):
        self.motion.start();self.wire.stall=True
        with self.assertRaisesRegex(ValueError,'izlemiyor'):
            for _ in range(25):self.step()
        self.assertLessEqual(self.bus.last_goal-2000,8);self.motion.stop()
        self.assertEqual(self.wire.registers[6][40],0)

    def test_enable_failure_still_disables_and_off_failure_does_not_restore(self):
        self.wire.fail=(6,40)
        with self.assertRaises(OSError):self.motion.start()
        self.motion.stop();self.assertEqual(self.wire.registers[6][40],0)

    def test_failed_off_keeps_low_cap_and_reports_failure(self):
        self.motion.start();self.wire.fail=(6,40)
        with self.assertRaises(OSError):self.motion.stop()
        self.assertEqual(self.wire.registers[6][48],100)
        self.assertTrue(self.bus.may_be_on)

    def test_packet_boundary_rejects_body_writes_closing_large_steps_and_eeprom(self):
        self.motion.start()
        for i,a,v in ((1,42,2000),(6,42,1999),(6,42,2003),(6,31,0),(6,48,500),(6,46,200)):
            data=v.to_bytes(2,'little');p=[i,5,3,a,*data];self.bus.permit=(a,data)
            with self.assertRaises(PermissionError):self.bus.port.writePort(bytes([255,255,*p,(~sum(p))&255]))
        self.motion.stop()


if __name__=='__main__':unittest.main()
