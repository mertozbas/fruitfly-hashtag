"""Exercise coordinated movement against the real SDK with virtual serial I/O."""
import unittest
from unittest.mock import patch

from test_alignment_probe import Wire,Clock
from so101.body_control import BodyBus,BodyMotion
from so101.hardware_contract import JOINTS


class BodyControlTests(unittest.TestCase):
    def setUp(self):
        self.wire=Wire();self.clock=Clock()
        self.saved={name:dict(id=i,range_min=700,range_max=3400,homing_offset=0,drive_mode=0)
                    for i,name in enumerate(JOINTS,1)}
        for i in range(1,7):self.wire.registers[i].update({40:int(i<6),42:2000,44:0,46:20,48:500,60:0,65:0})
        for name in ('serial.Serial','fcntl.ioctl'):
            p=patch(name,return_value=self.wire if name=='serial.Serial' else None);p.start();self.addCleanup(p.stop)
        self.bus=BodyBus('OFFLINE_TEST');self.addCleanup(self.bus.close)
        self.target=[2000,1960,1960,1980,2000,2000]
        self.motion=BodyMotion(self.bus,self.saved,[2000]*6,self.target,clock=self.clock)

    def step(self,heartbeat=0.,source=.1):
        self.clock.sleep(.1);return self.motion.step(1.,True,heartbeat,source)

    def test_three_joints_reach_target_without_any_torque_or_gripper_write(self):
        self.motion.start()
        for _ in range(40):
            step=self.step()
            if step['complete']:break
        self.assertTrue(step['complete']);self.motion.stop()
        self.assertEqual([self.wire.registers[i][56] for i in range(1,7)],self.target)
        previous={i:2000 for i in range(1,7)}
        for i,address,value in self.wire.writes:
            self.assertIn(i,(2,3,4));self.assertEqual(address,42)
            self.assertLessEqual(abs(value-previous[i]),2);previous[i]=value
        self.assertTrue(all(self.wire.registers[i][40] for i in range(1,6)))
        self.assertFalse(self.wire.registers[6][40]);self.assertFalse(self.motion.brain_driven)

    def test_invalid_target_gripper_and_span_are_rejected_before_any_write(self):
        for target in (None,[2000]*5,[2000.]*6,[2000]*5+[2001],[2171]+[2000]*5):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    BodyMotion(self.bus,self.saved,[2000]*6,target).start()
        self.assertEqual(self.wire.writes,[])

    def test_unrequested_loaded_joints_keep_their_native_holding_goals(self):
        for i in (2,3,4):self.wire.registers[i][56]=2004
        q=[2000,2004,2004,2004,2000,2000]
        self.motion=BodyMotion(self.bus,self.saved,q,[2020,*q[1:]],clock=self.clock)
        self.motion.start()
        for _ in range(30):
            step=self.step()
            if step['complete']:break
        self.assertTrue(step['complete']);self.motion.stop()
        self.assertEqual({i for i,_,_ in self.wire.writes},{1})
        for i in (2,3,4):
            self.assertEqual(self.wire.registers[i][42],2000)
            self.assertEqual(self.wire.registers[i][56],2004)

    def test_stale_camera_viewer_and_loop_delay_never_advance(self):
        self.motion.start()
        for heartbeat,source in ((1.1,.1),(0.,.5),(0.,-.1)):
            with self.assertRaises(ValueError):self.step(heartbeat,source)
        self.clock.sleep(.3)
        with self.assertRaisesRegex(ValueError,'250 ms'):self.step()
        self.assertEqual(self.wire.writes,[])

    def test_thermal_fault_and_torque_loss_do_not_advance(self):
        self.motion.start()
        for motor,address,value in ((6,63,50),(2,40,0),(3,65,1)):
            old=self.wire.registers[motor][address];self.wire.registers[motor][address]=value
            with self.assertRaises(ValueError):self.step()
            self.wire.registers[motor][address]=old
        self.assertEqual(self.wire.writes,[])

    def test_stall_stops_at_existing_tracking_lead_and_latches_once(self):
        self.motion.start();self.wire.stall=True
        with self.assertRaisesRegex(ValueError,'izleyemedi') as failure:
            for _ in range(40):self.step()
        self.assertIn('shoulder_lift (motor 2): ölçüm=2000',str(failure.exception))
        self.assertIn('gönderilmeyen hedef=',str(failure.exception))
        self.assertIn('takip sınırı=16',str(failure.exception))
        self.assertTrue(all(abs(value-2000)<=16 for _,_,value in self.wire.writes))
        self.motion.stop();before=list(self.wire.writes);self.motion.stop()
        self.assertEqual(before,self.wire.writes)
        self.assertEqual([self.wire.registers[i][42] for i in range(1,6)],[2000]*5)

    def test_tracking_lag_waits_without_more_goals_then_resumes_after_feedback(self):
        self.motion.start();self.wire.stall=True
        for _ in range(10):self.step()
        before=list(self.wire.writes)
        for _ in range(4):self.step()
        self.assertEqual(before,self.wire.writes)
        for i in range(1,6):self.wire.registers[i][56]=self.wire.registers[i][42]
        self.wire.stall=False;self.step()
        self.assertGreater(len(self.wire.writes),len(before))

    def test_final_goal_requires_measured_arrival_and_has_settling_deadline(self):
        self.motion.target=[2000,1984,1984,1984,2000,2000]
        self.motion.start();self.wire.stall=True
        with self.assertRaisesRegex(ValueError,'yerleşemedi') as failure:
            for _ in range(40):
                self.assertFalse(self.step()['complete'])
        self.assertIn('wrist_flex (motor 4): ölçüm=2000, hedef=1984, fark=16, tolerans=8',str(failure.exception))
        self.assertEqual(self.bus.goals,self.motion.target[:5])
        self.motion.stop()

    def test_packet_guard_rejects_configuration_gripper_and_large_steps(self):
        self.motion.start()
        for i,address,value in ((2,40,0),(2,31,0),(6,42,2000),(2,42,1997),(2,42,2002)):
            data=value.to_bytes(2,'little');p=[i,5,3,address,*data]
            self.bus.permit=(i,address,data)
            with self.assertRaises(PermissionError):self.bus.port.writePort(bytes([255,255,*p,(~sum(p))&255]))
        self.assertEqual(self.wire.writes,[])

    def camera_motion(self):
        self.motion=BodyMotion(self.bus,self.saved,[2000]*6,[2040,2000,2000,2000,2000,2000],
            clock=self.clock,thermal_pause_review='Reviewed free-space pan measurement; gripper remains off')
        self.motion.start();self.step()

    def test_reviewed_warning_holds_until_all_motors_stay_cool_for_two_seconds(self):
        self.camera_motion();self.wire.registers[6][63]=55
        state=self.step();self.assertTrue(state['thermal_paused']);writes=list(self.wire.writes)
        self.wire.registers[6][63]=39
        for _ in range(15):self.assertTrue(self.step()['thermal_paused'])
        self.wire.registers[2][63]=45;self.step()  # resets the consecutive-cool interval
        self.wire.registers[2][63]=35
        for _ in range(20):self.assertTrue(self.step()['thermal_paused'])
        self.assertEqual(self.wire.writes,writes)
        for _ in range(3):
            state=self.step()
            if not state['thermal_paused']:break
        self.assertFalse(state['thermal_paused']);self.assertEqual(self.wire.writes,writes)
        self.step();self.assertGreater(len(self.wire.writes),len(writes))
        self.assertEqual(len(state['thermal_pauses']),1)
        self.assertIn('resume_t',state['thermal_pauses'][0])

    def test_paused_motion_keeps_all_nonthermal_guards_and_hard_temperature_stop(self):
        self.camera_motion();self.wire.registers[6][63]=55;self.step();writes=list(self.wire.writes)
        for motor,address,value in ((6,63,60),(2,60,121),(3,62,133),(4,65,1),(1,40,0)):
            old=self.wire.registers[motor][address];self.wire.registers[motor][address]=value
            with self.subTest(address=address):
                with self.assertRaises(ValueError):self.step()
            self.wire.registers[motor][address]=old
        with self.assertRaises(ValueError):self.step(source=.5)
        with self.assertRaises(ValueError):self.step(heartbeat=1.1)
        self.assertEqual(self.wire.writes,writes)
        self.motion.stop();self.assertEqual(self.wire.writes,writes)
        self.assertTrue(all(self.wire.registers[i][40] for i in range(1,6)))

    def test_persistent_warm_reading_times_out_without_advancing(self):
        self.camera_motion();self.wire.registers[6][63]=55;self.step();writes=list(self.wire.writes)
        with self.assertRaisesRegex(ValueError,'sekiz saniyede'):
            for _ in range(85):self.step()
        self.assertEqual(self.wire.writes,writes)

    def test_third_warning_ends_reviewed_measurement(self):
        self.camera_motion()
        for _ in range(2):
            self.wire.registers[6][63]=55;self.assertTrue(self.step()['thermal_paused'])
            self.wire.registers[6][63]=39
            for _ in range(24):
                if not self.step()['thermal_paused']:break
        self.wire.registers[6][63]=50
        with self.assertRaisesRegex(ValueError,'Üçüncü'):self.step()
        self.assertEqual(len(self.motion.thermal_events),2)

    def test_pause_requires_a_single_reviewed_pan_or_roll_and_cool_preflight(self):
        for target,review in ((self.target,'review'),([2040,2000,2000,2000,2040,2000],'review'),
                              ([2040,2000,2000,2000,2000,2000],'')):
            with self.assertRaises(ValueError):
                BodyMotion(self.bus,self.saved,[2000]*6,target,thermal_pause_review=review)
        self.wire.registers[6][63]=50
        with self.assertRaises(ValueError):self.camera_motion()
        self.assertEqual(self.wire.writes,[])


if __name__=='__main__':unittest.main()
