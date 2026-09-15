"""Neural-to-servo causality and unchanged packet limits; virtual hardware only."""
import copy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from test_alignment_probe import Wire,Clock
from so101.alignment_probe import run_probe
from so101.hardware_contract import JOINTS
from so101.neural_wrist import sensor_signal,neural_readout
from so101.pose_hold import HeldWristProbeBus


class TinyVision:
    task='vision'
    circuit=SimpleNamespace(metadata={'task':'vision'},groups=('input','relay','projection','descending'))
    decoder=np.array([[4.],[-4.]])
    def activity(self,x):
        return .9,[np.asarray(x)]*4


class NeuralSignalTests(unittest.TestCase):
    def test_real_rgb_halves_and_zero_stimulus(self):
        frame=np.zeros((720,1280,3),np.uint8);frame[:,:640,0]=255
        left=sensor_signal(frame);np.testing.assert_allclose(left,[.9,0],atol=1e-5)
        right=sensor_signal(frame[:,::-1].copy());np.testing.assert_allclose(right,[0,.9],atol=1e-5)
        self.assertEqual(neural_readout(TinyVision(),left)['delta_counts'],8)
        negative=neural_readout(TinyVision(),right)
        self.assertEqual(negative['delta_counts'],8);self.assertFalse(negative['directional_mapping'])
        with self.assertRaisesRegex(ValueError,'No visible red'):neural_readout(TinyVision(),[0,0])

    def test_core_silence_has_no_command_even_with_nonzero_policy_bias(self):
        p=TinyVision()
        p.activity=lambda x:(.9,[np.zeros(2)]*4)
        result=neural_readout(p,[.9,0])
        self.assertEqual(result['original_steering'],.9)
        self.assertEqual(result['bias_free_drive'],0);self.assertEqual(result['delta_counts'],0)

    def test_invalid_input_task_and_activity_are_rejected(self):
        for x in ([float('nan'),0],[-1,1],[2,0],[1]):
            with self.assertRaises(ValueError):neural_readout(TinyVision(),x)
        with self.assertRaises(ValueError):sensor_signal(np.zeros((1080,1920,3),np.uint8))
        p=TinyVision();p.task='so101'
        with self.assertRaises(ValueError):neural_readout(p,[1,0])
        p=TinyVision();p.activity=lambda x:(1.,[np.array([np.nan,0])]*4)
        with self.assertRaises(ValueError):neural_readout(p,[1,0])

    def test_local_trained_vision_model_has_opposed_outputs_and_zero_silencing(self):
        path=Path('models/lab_runs/local-vision-seed42/trained.npz')
        if not path.exists():self.skipTest('Local model not distributed with tests')
        from odor_policy import Policy
        p=Policy(path);left=neural_readout(p,[.8,.2]);right=neural_readout(p,[.2,.8])
        self.assertGreater(left['bias_free_drive'],.8);self.assertLess(right['bias_free_drive'],-.8)
        self.assertEqual(left['delta_counts'],8);self.assertEqual(right['delta_counts'],8)
        self.assertEqual(left['silenced_delta_counts'],0)
        with patch.object(p,'activity',return_value=(.9,[np.zeros_like(np.asarray(a)) for a in left['layer_activity']])):
            self.assertEqual(neural_readout(p,[.8,.2])['delta_counts'],0)


class NeuralHardwareTests(unittest.TestCase):
    def setUp(self):
        self.wire=Wire();self.clock=Clock();self.records=[]
        self.saved={n:dict(id=i,drive_mode=0,range_min=700,range_max=3400,homing_offset=0) for i,n in enumerate(JOINTS,1)}
        for target in ('serial.Serial','fcntl.ioctl'):
            p=patch(target,return_value=self.wire if target=='serial.Serial' else None);p.start();self.addCleanup(p.stop)
        for i in range(1,6):self.wire.registers[i].update({40:1,42:2000,44:0,46:20,48:500})
        self.bus=HeldWristProbeBus('OFFLINE_TEST');self.addCleanup(self.bus.close)

    def run_it(self,decision,check=lambda:None,save=None):
        return run_probe(self.bus,self.saved,[2000]*6,check,
                         save or (lambda r:self.records.append(copy.deepcopy(r))),self.clock,self.clock.sleep,decision)

    def test_actual_neural_readout_drives_only_wrist_and_safety_return_is_separate(self):
        result=self.run_it(lambda:neural_readout(TinyVision(),[.9,0]))
        self.assertEqual(result['status'],'passed');self.assertTrue(result['brain_connected'])
        self.assertEqual(result['measured_peak_counts'],8);self.assertFalse(result['closed_loop'])
        self.assertEqual(result['return_source'],'deterministic_safety_return')
        self.assertTrue(all((i,a)==(5,42) and 2000<=v<=2008 for i,a,v in self.wire.writes))
        self.assertTrue(all(self.wire.registers[i][40] for i in range(1,6)))
        self.assertFalse(self.wire.registers[6][40])

    def test_zero_neural_output_holds_without_any_write(self):
        p=TinyVision();p.activity=lambda x:(.9,[np.zeros(2)]*4)
        result=self.run_it(lambda:neural_readout(p,[.9,0]))
        self.assertEqual(result['status'],'neural_hold');self.assertFalse(result['brain_connected'])
        self.assertEqual(self.wire.writes,[])

    def test_out_of_envelope_decision_never_enables_motion(self):
        for delta in (9,-1,True,8.):
            with self.subTest(delta=delta):
                result=self.run_it(lambda:dict(delta_counts=delta))
                self.assertEqual(result['status'],'failed');self.assertEqual(self.wire.writes,[])

    def test_stale_neural_input_or_bad_model_prevents_writes(self):
        def stale():raise ValueError('Live neural image is stale')
        result=self.run_it(stale)
        self.assertEqual(result['status'],'failed');self.assertEqual(self.wire.writes,[])

    def test_failed_durable_neural_audit_prevents_writes(self):
        def failed(r):
            if r['status']=='prepared':raise OSError('Disk full')
        result=self.run_it(lambda:neural_readout(TinyVision(),[.9,0]),save=failed)
        self.assertEqual(result['status'],'failed');self.assertEqual(self.wire.writes,[])

    def test_camera_loss_stops_at_current_pose_without_releasing_support(self):
        def lost():
            if self.bus.last_goal==2004:raise ValueError('Camera lost')
        result=self.run_it(lambda:neural_readout(TinyVision(),[.9,0]),check=lost)
        self.assertEqual(result['status'],'failed');self.assertEqual(self.wire.registers[5][42],2004)
        self.assertTrue(all(self.wire.registers[i][40] for i in range(1,6)))
        self.assertFalse(any(a!=42 or i!=5 for i,a,v in self.wire.writes))


if __name__=='__main__':unittest.main()
