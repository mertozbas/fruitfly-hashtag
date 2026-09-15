"""Explicit coarse range protocol through a virtual SDK bus; no real hardware."""
import copy
import unittest
from unittest.mock import patch

from test_alignment_probe import Wire,Clock
from so101.hardware_contract import JOINTS
from so101.range_probe import RangeBus,run_range


class RangeTests(unittest.TestCase):
    def setUp(self):
        self.wire=Wire();self.clock=Clock();self.records=[]
        self.saved={n:dict(id=i,drive_mode=0,range_min=700,range_max=3400,homing_offset=0) for i,n in enumerate(JOINTS,1)}
        for target in ('serial.Serial','fcntl.ioctl'):
            p=patch(target,return_value=self.wire if target=='serial.Serial' else None);p.start();self.addCleanup(p.stop)
        for i in range(1,6):self.wire.registers[i].update({40:1,42:2000,44:0,46:20,48:500})
        for i in range(1,7):self.wire.registers[i].update({60:0,65:0})
        self.bus=RangeBus('OFFLINE_TEST',5,170);self.addCleanup(self.bus.close)

    def run_it(self,drive=1.,check=lambda:None,save=None,thermal_pause=False):
        return run_range(self.bus,self.saved,[2000]*6,check,
                         save or (lambda r:self.records.append(copy.deepcopy(r))),
                         lambda:dict(bias_free_drive=drive,delta_counts=8),self.clock,self.clock.sleep,thermal_pause=thermal_pause)

    def test_170_count_roundtrip_only_writes_selected_goal_and_preserves_support(self):
        r=self.run_it();self.assertEqual(r['status'],'passed_coarse_range')
        self.assertEqual(r['measured_peak_counts'],170);self.assertEqual(r['return_error_counts'],0)
        self.assertTrue(r['brain_connected']);self.assertFalse(r['directional_mapping'])
        self.assertEqual(r['neural_readout_microprobe_delta_counts'],8)
        self.assertIn('170',r['motor_adapter'])
        self.assertTrue(all((i,a)==(5,42) and 2000<=v<=2170 for i,a,v in self.wire.writes))
        goals=[2000]+[v for _,_,v in self.wire.writes]
        self.assertTrue(all(abs(a-b)<=2 for a,b in zip(goals,goals[1:])))
        self.assertEqual(goals[-1],2000)
        self.assertTrue(all(self.wire.registers[i][40] for i in range(1,6)))
        self.assertFalse(self.wire.registers[6][40]);self.assertLess(r['duration_s'],45)

    def test_native_goal_not_measured_position_is_preserved_on_return(self):
        self.wire.registers[5][42]=1994
        r=self.run_it();self.assertEqual(r['status'],'passed_coarse_range')
        self.assertEqual(r['initial_native_goal'],1994);self.assertEqual(self.wire.registers[5][42],1994)
        self.assertEqual(r['return_error_counts'],-6)

    def test_half_drive_scales_range_and_silence_never_writes(self):
        r=self.run_it(.5);self.assertEqual(r['measured_peak_counts'],85)
        self.wire.writes.clear();self.bus=RangeBus('OFFLINE_TEST',5,170)
        r=self.run_it(0.);self.assertEqual(r['status'],'neural_hold');self.assertEqual(self.wire.writes,[])

    def test_invalid_drive_never_writes(self):
        for drive in (True,float('nan'),float('inf'),1.01,-1.01,None):
            with self.subTest(drive=drive):
                r=self.run_it(drive);self.assertEqual(r['status'],'failed');self.assertEqual(self.wire.writes,[])

    def test_stalled_motor_cannot_enlarge_8_count_tracking_lead(self):
        self.wire.stall=True;r=self.run_it()
        self.assertEqual(r['status'],'failed');self.assertIn('did not track',r['error'])
        self.assertLessEqual(max(v for _,_,v in self.wire.writes),2008)
        self.assertEqual(self.wire.registers[5][42],2000);self.assertEqual(r['measured_peak_counts'],0)

    def test_one_count_intermediate_handles_deadband_without_increasing_lead(self):
        original=self.wire.write;leads=[]
        def deadband(packet):
            p=bytes(packet);old=self.wire.registers[5][56]
            result=original(p)
            if p[4]==3 and p[2]==5 and p[5]==42:
                delta=int.from_bytes(p[6:-1],'little')-old;leads.append(abs(delta))
                self.wire.registers[5][56]=old+((3 if delta>0 else -3) if abs(delta)>=8 else 0)
            return result
        self.wire.write=deadband
        r=self.run_it();self.assertEqual(r['status'],'passed_coarse_range')
        self.assertLessEqual(max(leads),8);self.assertLessEqual(abs(r['return_error_counts']),8)
        self.assertTrue(any(abs(a[2]-b[2])==1 for a,b in zip(self.wire.writes,self.wire.writes[1:])))

    def test_recorded_return_is_one_way_and_never_a_neural_action(self):
        self.wire.registers[5].update({42:2150,56:2150})
        self.bus=RangeBus('OFFLINE_TEST',5,150,-1)
        def no_neural():raise AssertionError('Recovery must not call a policy')
        r=run_range(self.bus,self.saved,[2000]*4+[2150,2000],lambda:None,lambda r:None,
                    no_neural,self.clock,self.clock.sleep,recovery_target=2000)
        self.assertEqual(r['status'],'returned_recorded_range');self.assertFalse(r['brain_connected'])
        self.assertEqual(r['outbound_source'],'recorded_test_return');self.assertIsNone(r['neural_decision'])
        self.assertEqual(r['return_error_counts'],0);self.assertEqual(self.wire.registers[5][42],2000)
        goals=[2150]+[v for _,_,v in self.wire.writes]
        self.assertTrue(all(0<=a-b<=2 for a,b in zip(goals,goals[1:])))

    def test_camera_loss_holds_measured_pose_and_does_not_drop_body(self):
        def lost():
            if self.bus.last_goal==2010:raise ValueError('Camera lost')
        r=self.run_it(check=lost);self.assertEqual(r['status'],'failed')
        self.assertEqual(self.wire.registers[5][42],2010)
        self.assertTrue(all(self.wire.registers[i][40] for i in range(1,6)))
        self.assertTrue(all((i,a)==(5,42) for i,a,_ in self.wire.writes))

    def test_other_joint_motion_stops_test(self):
        def drift():
            if self.bus.last_goal==2010:self.wire.registers[1][56]=2009
        r=self.run_it(check=drift);self.assertEqual(r['status'],'failed');self.assertIn('Other joint',r['error'])
        self.assertLessEqual(max(v for _,_,v in self.wire.writes),2010)

    def test_audit_failure_prevents_all_writes(self):
        def failed(r):
            if r['status']=='prepared':raise OSError('Disk full')
        r=self.run_it(save=failed);self.assertEqual(r['status'],'failed');self.assertEqual(self.wire.writes,[])

    def test_calibrated_margin_and_native_holding_error_are_not_bypassed(self):
        for goal in (1980,3300):
            self.wire.registers[5][42]=goal
            r=self.run_it();self.assertEqual(r['status'],'failed');self.assertEqual(self.wire.writes,[])
        self.wire.registers[5].update({42:2000,11:2150});self.saved['wrist_roll']['range_max']=2150
        r=self.run_it();self.assertEqual(r['status'],'failed');self.assertIn('calibrated margin',r['error']);self.assertEqual(self.wire.writes,[])

    def test_read_deadline_failure_prevents_motion(self):
        r=self.run_it(check=lambda:self.clock.sleep(.16))
        self.assertEqual(r['status'],'failed');self.assertEqual(self.wire.writes,[])

    def test_single_bad_electrical_read_is_not_ignored_and_records_exact_motor(self):
        def sag():
            if self.bus.last_goal==2010:self.wire.registers[3][62]=0
        r=self.run_it(check=sag);self.assertEqual(r['status'],'failed')
        self.assertEqual(r['fault_observation']['motor'],dict(id=3,temperature_c=35,voltage_v=0.,status=0,native_load=0))
        self.assertEqual(self.wire.registers[5][42],2010)

    def test_explicit_16_count_lead_still_stops_stall_inside_original_stroke(self):
        self.bus=RangeBus('OFFLINE_TEST',5,170,tracking_limit=16);self.wire.stall=True
        r=self.run_it();self.assertEqual(r['status'],'failed')
        self.assertEqual(r['max_tracking_error_counts'],16);self.assertEqual(r['return_tolerance_counts'],8)
        self.assertLessEqual(max(v for _,_,v in self.wire.writes),2016)
        self.assertEqual(self.wire.registers[5][42],2000)

    def test_reviewed_lead_handles_larger_servo_deadband_without_config_writes(self):
        self.bus=RangeBus('OFFLINE_TEST',5,170,tracking_limit=16)
        original=self.wire.write
        def deadband(packet):
            p=bytes(packet);old=self.wire.registers[5][56];result=original(p)
            if p[4]==3 and p[2]==5 and p[5]==42:
                delta=int.from_bytes(p[6:-1],'little')-old
                self.assertLessEqual(abs(delta),16)
                self.wire.registers[5][56]=old+((6 if delta>0 else -6) if abs(delta)>=10 else 0)
            return result
        self.wire.write=deadband;r=self.run_it()
        self.assertEqual(r['status'],'passed_coarse_range');self.assertLessEqual(abs(r['return_error_counts']),8)
        self.assertTrue(all((i,a)==(5,42) for i,a,_ in self.wire.writes))

    def test_status_or_load_fault_interrupts_even_with_reviewed_16_count_lead(self):
        for address,value in ((65,4),(60,121),(60,1024+121)):
            self.bus=RangeBus('OFFLINE_TEST',5,170,tracking_limit=16)
            self.wire.registers[2][address]=value
            r=self.run_it();self.assertEqual(r['status'],'failed');self.assertIn('status/load',r['error'])
            self.assertEqual(self.wire.writes,[]);self.wire.registers[2][address]=0

    def test_transient_warning_holds_without_advancing_until_two_cool_seconds(self):
        triggered=False;warm_until=0.;hold_started=None;resume_at=None
        def readings():
            nonlocal triggered,warm_until,hold_started,resume_at
            if not triggered and self.bus.last_goal==2010:
                triggered=True;warm_until=self.clock()+.4
            self.wire.registers[6][63]=54 if triggered and self.clock()<warm_until else 35
            if self.bus.phase=='hold' and hold_started is None:hold_started=self.clock()
            if hold_started is not None and self.bus.phase=='move' and resume_at is None:resume_at=self.clock()
            if self.bus.phase=='hold':self.assertEqual(self.wire.registers[5][42],2010)
        r=self.run_it(check=readings,thermal_pause=True)
        self.assertEqual(r['status'],'passed_coarse_range');self.assertEqual(len(r['thermal_pauses']),1)
        self.assertGreaterEqual(resume_at-warm_until,2)
        self.assertEqual(self.wire.registers[5][42],2000)

    def test_persistent_warning_hard_temperature_voltage_or_camera_loss_never_resumes(self):
        for fault in ('persistent','hard','voltage','camera'):
            with self.subTest(fault=fault):
                self.bus=RangeBus('OFFLINE_TEST',5,170);self.clock=Clock();self.wire.writes=[]
                for i in range(1,7):self.wire.registers[i].update({63:35,62:124,56:2000})
                self.wire.registers[5][42]=2000
                def readings():
                    if self.bus.last_goal==2010:
                        self.wire.registers[6][63]=60 if fault=='hard' else 54
                        if self.bus.phase=='hold' and fault=='voltage':self.wire.registers[6][62]=0
                        if self.bus.phase=='hold' and fault=='camera':raise ValueError('Camera lost while paused')
                r=self.run_it(check=readings,thermal_pause=True)
                self.assertEqual(r['status'],'failed');self.assertEqual(self.wire.registers[5][42],2010)
                self.assertFalse(any(e.get('resume_t') for e in r.get('thermal_pauses',[])))
                self.assertLessEqual(max(v for _,_,v in self.wire.writes),2010)

    def test_third_warning_ends_test_and_never_adds_a_third_resume(self):
        triggers=set()
        def readings():
            goal=self.bus.last_goal
            if self.bus.phase=='move' and goal in (2010,2020,2030) and goal not in triggers:
                triggers.add(goal);self.wire.registers[6][63]=54
            else:self.wire.registers[6][63]=35
        r=self.run_it(check=readings,thermal_pause=True)
        self.assertEqual(r['status'],'failed');self.assertIn('more than twice',r['error'])
        self.assertEqual(len(r['thermal_pauses']),2);self.assertEqual(self.wire.registers[5][42],2030)

    def test_warm_preflight_still_forbids_start_even_with_pause_enabled(self):
        self.wire.registers[6][63]=54
        r=self.run_it(thermal_pause=True);self.assertEqual(r['status'],'failed');self.assertEqual(self.wire.writes,[])

    def test_gripper_and_larger_span_cannot_be_requested(self):
        for motor,span in ((6,170),(0,170),(True,170),(5,171),(5,0),(5,170.)):
            with self.assertRaises(ValueError):RangeBus('OFFLINE_TEST',motor,span)

    def test_packet_boundary_rejects_other_joint_torque_eeprom_and_large_steps(self):
        self.bus.open();self.bus.initial=self.bus.last_goal=2000;self.bus.phase='move'
        for i,a,v in ((1,42,2002),(5,40,0),(5,31,1),(5,46,50),(5,42,2003),(5,42,1999)):
            data=list(v.to_bytes(2,'little'));body=[i,5,3,a,*data]
            self.bus.permit=(a,bytes(data))
            with self.assertRaises(PermissionError):self.bus.guard(bytes([255,255,*body,(~sum(body))&255]))
        self.assertEqual(self.wire.writes,[])


if __name__=='__main__':unittest.main()
