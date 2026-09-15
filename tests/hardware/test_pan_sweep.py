"""Pan-only larger/faster envelope and restoration against a virtual bus."""
import unittest
from unittest.mock import patch
from test_alignment_probe import Wire,Clock
from so101.hardware_contract import JOINTS
from so101.pan_sweep import PanSweepBus
from so101.range_probe import run_range


class PanSweepTests(unittest.TestCase):
    def setUp(self):
        self.wire=Wire();self.clock=Clock()
        self.saved={n:dict(id=i,drive_mode=0,range_min=700,range_max=3400,homing_offset=0) for i,n in enumerate(JOINTS,1)}
        for target in ('serial.Serial','fcntl.ioctl'):
            p=patch(target,return_value=self.wire if target=='serial.Serial' else None);p.start();self.addCleanup(p.stop)
        for i in range(1,6):self.wire.registers[i].update({40:1,42:2000,44:0,46:20,48:500})
        for i in range(1,7):self.wire.registers[i].update({60:0,65:0})
        self.bus=PanSweepBus('OFFLINE_TEST',340);self.addCleanup(self.bus.close)

    def run_it(self,check=lambda:None,save=lambda r:None,drive=1.):
        return run_range(self.bus,self.saved,[2000]*6,check,save,lambda:dict(bias_free_drive=drive),self.clock,self.clock.sleep,thermal_pause=True)

    def test_30_degree_roundtrip_writes_only_pan_goal_and_bounded_velocity(self):
        r=self.run_it();self.assertEqual(r['status'],'passed_coarse_range');self.assertEqual(r['measured_peak_counts'],340)
        self.assertTrue(all(i==1 and (a==42 and 2000<=v<=2340 or a==46 and v in (20,60)) for i,a,v in self.wire.writes))
        self.assertEqual(self.wire.writes[0],(1,46,60));self.assertEqual(self.wire.writes[-1],(1,46,20))
        goals=[2000]+[v for _,a,v in self.wire.writes if a==42]
        self.assertTrue(all(abs(a-b)<=5 for a,b in zip(goals,goals[1:])))
        self.assertEqual(self.wire.registers[1][46],20);self.assertEqual(goals[-1],2000)
        self.assertTrue(all(self.wire.registers[i][40] for i in range(1,6)));self.assertFalse(self.wire.registers[6][40])

    def test_stall_stops_within_16_count_lead_and_restores_velocity(self):
        self.wire.stall=True;r=self.run_it();self.assertEqual(r['status'],'failed')
        self.assertLessEqual(max(v for _,a,v in self.wire.writes if a==42),2016)
        self.assertEqual(self.wire.registers[1][42],2000);self.assertEqual(self.wire.registers[1][46],20)

    def test_warning_holds_then_resumes_with_five_count_steps_and_restores_speed(self):
        triggered=False;hold_started=None
        def readings():
            nonlocal triggered,hold_started
            if not triggered and self.bus.last_goal==2010:
                triggered=True;self.wire.registers[6][63]=54
                # Feedback trails the target when the warning arrives.
                self.wire.registers[1][56]=2006
            else:self.wire.registers[6][63]=35
            if self.bus.phase=='hold':
                if hold_started is None:hold_started=self.clock()
                self.assertEqual(self.wire.registers[1][42],2006)
        r=self.run_it(check=readings)
        self.assertEqual(r['status'],'passed_coarse_range')
        event=r['thermal_pauses'][0]
        self.assertEqual(event['hold_position'],2006)
        self.assertGreaterEqual(round(event['resume_t']-hold_started,4),2)
        goals=[2000]+[v for _,a,v in self.wire.writes if a==42]
        self.assertTrue(all(abs(a-b)<=5 for a,b in zip(goals,goals[1:])))
        self.assertEqual(goals[-1],2000);self.assertEqual(self.wire.registers[1][46],20)

    def test_camera_loss_holds_pan_and_restores_velocity_without_dropping_arm(self):
        def lost():
            if self.bus.last_goal==2010:raise ValueError('Camera lost')
        r=self.run_it(check=lost);self.assertEqual(r['status'],'failed')
        self.assertEqual(self.wire.registers[1][42],2010);self.assertEqual(self.wire.registers[1][46],20)
        self.assertTrue(all(self.wire.registers[i][40] for i in range(1,6)))

    def test_failed_speed_setup_restores_without_any_position_command(self):
        self.wire.fail=(1,46);r=self.run_it();self.assertEqual(r['status'],'failed')
        self.assertFalse(any(a==42 for _,a,_ in self.wire.writes));self.assertEqual(self.wire.registers[1][46],20)

    def test_audit_failure_or_silence_does_not_change_speed(self):
        def failed(r):
            if r['status']=='prepared':raise OSError('Disk full')
        r=self.run_it(save=failed);self.assertEqual(r['status'],'failed');self.assertEqual(self.wire.writes,[])
        self.bus=PanSweepBus('OFFLINE_TEST',340);r=self.run_it(drive=0.)
        self.assertEqual(r['status'],'neural_hold');self.assertEqual(self.wire.writes,[])

    def test_other_motor_torque_eeprom_speed_and_larger_range_blocked(self):
        for span in (341,0,340.,True):
            with self.assertRaises(ValueError):PanSweepBus('OFFLINE_TEST',span)
        self.bus.phase='speed_setup'
        for i,a,v in ((2,46,60),(1,46,61),(1,40,1),(1,21,32)):
            data=list(v.to_bytes(2,'little'));body=[i,5,3,a,*data];self.bus.permit=(a,bytes(data))
            with self.assertRaises(PermissionError):self.bus.guard(bytes([255,255,*body,(~sum(body))&255]))
        self.assertEqual(self.wire.writes,[])
