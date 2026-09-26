"""Operator recording must never generate a movement or torque-on command."""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from test_alignment_probe import Wire, Clock
from so101.physical_driver import PhysicalBus
from so101.teaching import TeachingRecorder,latest_teaching


class TeachingTests(unittest.TestCase):
    def test_restart_restores_matching_capture_without_motion_permission(self):
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root)/'session'/'teaching-one'
            recorder=TeachingRecorder(directory,[(700,3400)]*6,
                {'serial_number':'robot','calibration_sha256':'cal'},Clock())
            recorder.append([2000]*6,{},dict(sensor_values=[0,0]))
            recorder.clock.sleep(.1)
            recorder.append([2001]*6,{},dict(sensor_values=[0,0]))
            recorder.finish()
            restored=latest_teaching(root,'robot','cal')
            self.assertTrue(restored['valid']);self.assertTrue(restored['restored'])
            self.assertEqual(restored['samples'],2)
            self.assertFalse(restored['active']);self.assertFalse(restored['execution_allowed'])
            self.assertIsNone(latest_teaching(root,'other','cal'))
            self.assertIsNone(latest_teaching(root,'robot','changed-cal'))
            (directory/'demonstration.json').write_text('broken json')
            self.assertIsNone(latest_teaching(root,'robot','cal'))

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.clock=Clock()
        self.recorder=TeachingRecorder(Path(self.tmp.name)/'demo',[(700,3400)]*6,
                                       {'calibration_sha256':'fixture'},self.clock)
        self.cameras={n:dict(session=n,sequence=1,wall_time=100.) for n in ('top','wrist')}

    def sample(self,q=None):
        return self.recorder.append(q or [2000]*6,self.cameras,dict(sensor_values=[.1,.2]))

    def test_six_joints_and_identity_persist_without_claiming_neural_execution(self):
        self.sample();self.clock.sleep(.1);self.sample([2001,2002,2003,2004,2005,2006])
        result=self.recorder.finish()
        saved=json.loads(Path(result['path']).read_text())
        self.assertTrue(result['valid']);self.assertFalse(saved['brain_connected'])
        self.assertEqual(saved['joint_span_counts'],[1,2,3,4,5,6])
        self.assertEqual(saved['points'][1]['q'],[2001,2002,2003,2004,2005,2006])
        self.assertEqual(saved['identity']['calibration_sha256'],'fixture')
        self.assertEqual(len((self.recorder.directory/'samples.jsonl').read_text().splitlines()),2)

    def test_gap_and_invalid_encoder_values_are_rejected(self):
        self.sample();self.clock.sleep(.1)
        for q in ([4096]*6,[-1]*6,[2000.]*6,[2000]*5):
            with self.assertRaises(ValueError):self.sample(q)
        self.clock.sleep(.3)
        with self.assertRaisesRegex(ValueError,'zaman boşluğu'):self.sample()
        result=self.recorder.finish('interrupted')
        self.assertFalse(result['valid']);self.assertEqual(result['samples'],1)

    def test_fast_manual_demonstration_is_captured_for_slower_execution(self):
        self.sample();self.clock.sleep(.1);self.sample([2200]*6)
        result=self.recorder.finish()
        self.assertTrue(result['valid']);self.assertEqual(result['bounded_playback_seconds'],5.)

    def test_outside_execution_envelope_is_preserved_but_never_approved(self):
        self.sample();self.clock.sleep(.1);state=self.sample([699]*6)
        self.assertEqual(state['outside_execution_limits'],list(range(1,7)))
        result=self.recorder.finish()
        self.assertFalse(result['valid']);self.assertEqual(result['samples'],2)

    def test_deadline_and_abort_preserve_capture_but_do_not_validate_it(self):
        self.sample();self.clock.sleep(91)
        with self.assertRaisesRegex(ValueError,'süresi'):self.sample()
        result=self.recorder.finish('viewer lost')
        self.assertFalse(result['valid']);self.assertTrue(Path(result['path']).exists())
        with self.assertRaisesRegex(ValueError,'kapandı'):self.sample()

    def test_empty_demo_is_not_valid(self):
        self.assertFalse(self.recorder.finish()['valid'])

    def test_release_only_writes_six_torque_off_packets(self):
        wire=Wire()
        for i in range(1,7):wire.registers[i][40]=int(i<6)
        with patch('serial.Serial',return_value=wire),patch('fcntl.ioctl'):
            bus=PhysicalBus('OFFLINE_TEST')
            try:
                bus.open();bus.release()
            finally:bus.close()
        self.assertEqual(wire.writes,[(i,40,0) for i in range(1,7)])

    def test_encoder_capture_continues_while_camera_caller_is_blocked(self):
        from so101.neural_live import NeuralLab
        lab=NeuralLab.__new__(NeuralLab)
        lab.lock=threading.Lock();lab.state={};lab.shutdown=threading.Event()
        lab.teach_done=threading.Event();lab.teach_fault=None
        lab.bus=object();lab.saved={'motors':{}};lab.cameras=self.cameras
        lab.recorder=TeachingRecorder(Path(self.tmp.name)/'thread-demo',[(700,3400)]*6,{})
        with patch('so101.neural_live.recording_telemetry',return_value=([2000]*6,[{'torque':False}]*6,[])):
            lab.teach_thread=threading.Thread(target=lab.record_joints)
            lab.teach_thread.start()
            try:
                # Reproduce a camera HTTP stall longer than the old 300 ms gap.
                time.sleep(.45)
            finally:lab.end_teaching()
        result=lab.state['teaching']
        self.assertTrue(result['valid']);self.assertGreaterEqual(result['samples'],6)
        self.assertFalse(lab.teach_thread.is_alive());self.assertIsNone(lab.recorder)

    def test_temperature_warning_is_saved_without_granting_execution(self):
        self.sample();self.clock.sleep(.1)
        warnings=[dict(motor_id=6,code='temperature',value=56)]
        self.recorder.append([2001]*6,self.cameras,dict(sensor_values=[.1,.2]),
                             [dict(id=6,temperature_c=56,torque=False)],warnings)
        result=self.recorder.finish()
        saved=json.loads(Path(result['path']).read_text())
        self.assertTrue(result['valid']);self.assertTrue(result['requires_review'])
        self.assertFalse(result['execution_allowed']);self.assertEqual(result['warning_samples'],1)
        self.assertEqual(saved['points'][1]['motors'][0]['temperature_c'],56)
        self.assertEqual(saved['points'][1]['warnings'],warnings)


if __name__=='__main__':unittest.main()
