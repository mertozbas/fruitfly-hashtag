"""Actual SDK packet boundaries and faults, with virtual serial hardware."""
import unittest
import queue
import threading
from unittest.mock import patch

import numpy as np

from test_alignment_probe import Wire, Clock
from test_neural_wrist import TinyVision
from so101.hardware_contract import JOINTS
from so101.neural_control import NeuralMotion, NeuralPanBus, visual_command


class ContinuousTests(unittest.TestCase):
    def setUp(self):
        self.wire=Wire();self.clock=Clock()
        self.saved={n:dict(id=i,drive_mode=0,range_min=700,range_max=3400,homing_offset=0) for i,n in enumerate(JOINTS,1)}
        for i in range(1,7):
            self.wire.registers[i].update({40:int(i<6),42:2000,44:0,46:20,48:500,60:0,65:0})
        for target in ('serial.Serial','fcntl.ioctl'):
            p=patch(target,return_value=self.wire if target=='serial.Serial' else None);p.start();self.addCleanup(p.stop)
        self.bus=NeuralPanBus('OFFLINE_TEST');self.addCleanup(self.bus.close)
        self.motion=NeuralMotion(self.bus,self.saved,[2000]*6,clock=self.clock)
        self.motion.start()

    def step(self,drive=1.,visible=True,heartbeat=0.,source=.1):
        self.clock.sleep(.1)
        return self.motion.step(drive,visible,heartbeat,source)

    def test_continuous_reversal_only_writes_bounded_base_goals(self):
        for _ in range(90):self.step(1.)
        self.assertEqual(self.wire.registers[1][56],1830)
        for _ in range(170):self.step(-1.)
        self.assertEqual(self.wire.registers[1][56],2170)
        self.motion.stop()
        self.assertTrue(all(i==1 and a==42 and 1830<=v<=2170 for i,a,v in self.wire.writes))
        goals=[2000]+[v for _,_,v in self.wire.writes]
        self.assertTrue(all(abs(a-b)<=2 for a,b in zip(goals,goals[1:])))
        self.assertTrue(all(self.wire.registers[i][40] for i in range(1,6)))
        self.assertEqual(self.wire.registers[6][40],0)

    def test_zero_neural_output_does_not_return_or_generate_motion(self):
        for _ in range(10):self.step(1.)
        before=list(self.wire.writes)
        self.step(0.)
        self.assertEqual(self.wire.writes,before)
        self.assertEqual(self.wire.registers[1][56],1980)

    def test_no_stimulus_latches_measured_position_without_new_neural_target(self):
        self.step();self.wire.registers[1][56]=1999
        r=self.step(1.,False)
        self.assertEqual(self.wire.registers[1][42],1999)
        self.assertFalse(r['neural_command'])

    def test_stale_camera_or_viewer_never_writes_another_target(self):
        for heartbeat,source in ((1.01,.1),(0.,.41),(0.,-.1)):
            with self.assertRaises(ValueError):self.step(heartbeat=heartbeat,source=source)
        self.assertEqual(self.wire.writes,[])

    def test_duration_and_slow_tick_stop_without_more_motion(self):
        self.clock.sleep(.3)
        with self.assertRaisesRegex(ValueError,'250 ms'):self.motion.step(1.,True,0.,.1)
        self.clock.sleep(30)
        with self.assertRaisesRegex(ValueError,'oturum'):self.motion.step(1.,True,0.,.1)
        self.assertEqual(self.wire.writes,[])

    def test_temperature_status_load_and_other_joint_drift_stop(self):
        for address,value in ((63,50),(65,1),(60,121),(56,2010)):
            previous=self.wire.registers[2][address];self.wire.registers[2][address]=value
            with self.assertRaises(ValueError):self.step()
            self.wire.registers[2][address]=previous
        self.assertEqual(self.wire.writes,[])

    def test_manual_outside_range_readout_requires_every_motor_torque_off(self):
        from so101.neural_control import telemetry
        self.wire.registers[2][56]=699
        with self.assertRaisesRegex(ValueError,'kalibrasyon sınırı'):
            telemetry(self.bus,self.saved,allow_manual=True)
        for i in range(1,7):self.wire.registers[i][40]=0
        q,rows=telemetry(self.bus,self.saved,allow_manual=True)
        self.assertEqual(q[1],699);self.assertFalse(rows[1]['in_range'])
        with self.assertRaisesRegex(ValueError,'kalibrasyon sınırı'):
            telemetry(self.bus,self.saved)
        self.assertEqual(self.wire.writes,[])

    def test_temperature_can_be_recorded_torque_off_but_still_blocks_motion(self):
        from so101.neural_control import recording_telemetry,telemetry
        self.wire.registers[6][63]=56
        with self.assertRaisesRegex(ValueError,'torku değişti'):
            recording_telemetry(self.bus,self.saved)
        for i in range(1,7):self.wire.registers[i][40]=0
        q,rows,warnings=recording_telemetry(self.bus,self.saved)
        self.assertEqual(rows[5]['temperature_c'],56)
        self.assertEqual(warnings,[dict(motor_id=6,code='temperature',value=56)])
        idle_q,idle_rows=telemetry(self.bus,self.saved,allow_manual=True)
        self.assertEqual(idle_rows[5]['temperature_c'],56)
        with self.assertRaisesRegex(ValueError,'sıcaklık/besleme'):
            telemetry(self.bus,self.saved)
        self.assertEqual(self.wire.writes,[])

    def test_stall_stops_without_expanding_lead(self):
        self.wire.stall=True
        with self.assertRaisesRegex(ValueError,'izleyemiyor'):
            for _ in range(30):self.step()
        self.assertLessEqual(max(abs(v-2000) for _,_,v in self.wire.writes),16)
        self.motion.stop();self.assertEqual(self.wire.registers[1][42],2000)

    def test_invalid_neural_output_never_writes(self):
        for drive in (True,float('nan'),float('inf'),1.1,None):
            with self.assertRaises(ValueError):self.step(drive)
        self.assertEqual(self.wire.writes,[])

    def test_guard_rejects_other_joint_eeprom_speed_and_oversized_step(self):
        for i,a,v in ((2,42,2001),(1,31,0),(1,46,60),(1,42,2003)):
            data=list(v.to_bytes(2,'little'));p=[i,5,3,a,*data]
            self.bus.permit=(a,bytes(data))
            with self.assertRaises(PermissionError):self.bus.port.writePort(bytes([255,255,*p,(~sum(p))&255]))
        self.assertEqual(self.wire.writes,[])


class VisionTests(unittest.TestCase):
    def test_red_direction_reverses_and_absence_holds(self):
        rgb=np.zeros((720,1280,3),np.uint8);rgb[100:200,100:200,0]=255
        self.assertGreater(visual_command(TinyVision(),rgb)['drive'],0)
        self.assertLess(visual_command(TinyVision(),rgb[:,::-1].copy())['drive'],0)
        self.assertFalse(visual_command(TinyVision(),np.zeros_like(rgb))['visible'])

    def test_silenced_core_and_balanced_stimulus_hold(self):
        rgb=np.zeros((720,1280,3),np.uint8);rgb[100:200,100:200,0]=255
        p=TinyVision();p.activity=lambda x:(.9,[np.zeros(2)]*4)
        self.assertEqual(visual_command(p,rgb)['drive'],0)
        rgb[:,:,0]=255
        self.assertEqual(visual_command(TinyVision(),rgb)['drive'],0)


class SessionRecoveryTests(unittest.TestCase):
    def test_idle_feedback_survives_failed_camera_and_preserves_high_reading(self):
        from unittest.mock import Mock
        from pathlib import Path
        from tempfile import TemporaryDirectory
        lab=self.camera_lab();lab.recorder=None;lab.saved={'motors':{}}
        lab.bus=Mock();lab.identity=Mock();lab.reopen=Mock();lab.recover_cameras=Mock()
        lab.commands=queue.Queue();lab.stop_requested=threading.Event();lab.shutdown=threading.Event()
        def camera_failure():lab.shutdown.set();raise ValueError('camera offline')
        lab.frames=Mock(side_effect=camera_failure)
        rows=[{'id':6,'temperature_c':57,'torque':False}]
        with TemporaryDirectory() as directory,patch('so101.neural_live.read_telemetry',return_value=([2000]*6,rows,.01)):
            lab.directory=Path(directory);lab.loop()
        self.assertEqual(lab.state['motors'],rows)
        self.assertEqual(lab.state['last_motor_warning']['motors'][0]['temperature_c'],57)
        self.assertGreater(lab.state['motor_wall_time'],0)
        self.assertEqual(lab.state['error'],'camera offline')
        self.assertNotIn('camera_wall_time',lab.state)
        lab.bus.write.assert_not_called()

    def test_idle_observer_never_competes_with_motion_or_recorder(self):
        lab=self.camera_lab();lab.recorder=None;lab.motion=object()
        with patch('so101.neural_live.read_telemetry') as read:
            lab.observe_motors();read.assert_not_called()
            lab.motion=None;lab.recorder=object()
            lab.observe_motors();read.assert_not_called()

    def camera_lab(self):
        from so101.neural_live import NeuralLab
        from unittest.mock import Mock
        lab=NeuralLab.__new__(NeuralLab)
        lab.motion=None;lab.last_view=100.;lab.camera_retries=0
        lab.next_camera_retry=0.;lab.camera_healthy_since=None
        lab.lock=threading.Lock();lab.state={};lab.start_cameras=Mock()
        return lab

    def test_camera_reconnect_requires_viewer_and_no_motion(self):
        lab=self.camera_lab();lab.motion=object()
        self.assertFalse(lab.recover_cameras(100.))
        lab.motion=None
        self.assertFalse(lab.recover_cameras(102.))
        lab.start_cameras.assert_not_called()
        lab.last_view=102.
        self.assertTrue(lab.recover_cameras(102.))
        lab.start_cameras.assert_called_once()
        self.assertIsNone(lab.motion)

    def test_camera_retries_have_backoff_and_three_attempt_ceiling(self):
        lab=self.camera_lab()
        self.assertTrue(lab.recover_cameras(100.))
        self.assertFalse(lab.recover_cameras(100.5))
        for now in (103.,109.):
            lab.last_view=now
            self.assertTrue(lab.recover_cameras(now))
        lab.last_view=130.
        self.assertFalse(lab.recover_cameras(130.))
        self.assertEqual(lab.start_cameras.call_count,3)
        self.assertEqual(lab.camera_retries,3)

    def test_stop_discards_pending_start_requests(self):
        from so101.neural_live import NeuralLab
        lab=NeuralLab.__new__(NeuralLab)
        lab.stop_requested=threading.Event();lab.commands=queue.Queue(4)
        lab.commands.put({'op':'run'});lab.commands.put({'op':'hold'})
        lab.submit({'op':'stop'})
        self.assertTrue(lab.stop_requested.is_set());self.assertTrue(lab.commands.empty())

    def test_failed_start_rotates_preview_instead_of_trapping_operator(self):
        from so101.neural_live import NeuralLab
        import time
        lab=NeuralLab.__new__(NeuralLab)
        lab.motion=None;lab.used=set();lab.lock=threading.Lock();lab.stop_requested=threading.Event()
        lab.state={'preview':'old'}
        def changed():raise ValueError('USB changed')
        lab.identity=changed
        with self.assertRaisesRegex(ValueError,'USB changed'):
            lab.action({'op':'run','preview':'old','created':time.monotonic()})
        self.assertIn('old',lab.used);self.assertNotEqual(lab.state['preview'],'old')


if __name__=='__main__':unittest.main()
