"""Run with the scientific environment; no downloaded anatomy is required."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy import sparse

from odor_policy import Circuit, Policy, GROUPS
from fly_sim import visual_signal
from lab_tasks import compatible


class PolicyContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.layers = [np.array([[1.,0.],[0.,1.]], dtype=np.float32) for _ in range(3)]
        files = []
        for i, layer in enumerate(self.layers):
            path = self.directory / f'layer{i}.npz'
            sparse.save_npz(path, sparse.csr_matrix(layer))
            files.append(dict(file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        ids = self.directory / 'body_ids.npz'
        np.savez_compressed(ids, **{g:np.array([i*2+1,i*2+2]) for i,g in enumerate(GROUPS)}, orn_side=np.array([0,1]))
        manifest = dict(groups={g:2 for g in GROUPS}, layers=files,
                        body_ids_sha256=hashlib.sha256(ids.read_bytes()).hexdigest())
        (self.directory / 'circuit.json').write_text(json.dumps(manifest))
        self.state = dict(weight=self.layers[2].copy(),decoder=np.array([[1.],[-1.]],dtype=np.float32),
                          bias=np.zeros(1,dtype=np.float32),task='odor',circuit_identity=Circuit(self.directory).identity)
        self.save()

    def save(self):
        np.savez_compressed(self.directory / 'trained.npz', **self.state)

    def test_live_activity_is_the_policy_decision(self):
        policy = Policy(self.directory / 'trained.npz')
        for inputs in [[0,0],[.1,.2],[1,.001]]:
            decision, activity = policy.activity(inputs)
            self.assertAlmostEqual(decision, policy(inputs), places=6)
            self.assertEqual(sum(map(len,activity)),8)
        self.assertLess(policy([.1,.2]),0)
        self.assertGreater(policy([.2,.1]),0)

    def test_input_shape_and_finiteness_are_enforced(self):
        policy = Policy(self.directory / 'trained.npz')
        for values in [[1], [[1,2],[3,4]], [np.nan,1], [np.inf,0],[-.1,.2]]:
            with self.assertRaises(ValueError):
                policy(values)

    def test_anatomical_mask_cannot_be_extended(self):
        self.state['weight'][0,1] = .1
        self.save()
        with self.assertRaisesRegex(ValueError,'outside the anatomical mask'):
            Policy(self.directory / 'trained.npz')

    def test_gain_sign_and_bounds_are_enforced(self):
        for value in [-.1, 5.]:
            self.state['weight'][0,0] = value
            self.save()
            with self.assertRaisesRegex(ValueError,'training bounds'):
                Policy(self.directory / 'trained.npz')

    def test_circuit_and_identity_corruption_are_rejected(self):
        self.state['circuit_identity'] = 'wrong'
        self.save()
        with self.assertRaisesRegex(ValueError,'different circuit'):
            Policy(self.directory / 'trained.npz')
        (self.directory / 'body_ids.npz').write_bytes(b'corrupted')
        with self.assertRaisesRegex(ValueError,'Neuron identity'):
            Circuit(self.directory)

    def test_task_mismatch_cannot_use_an_olfactory_network_for_vision(self):
        self.assertTrue(compatible('flight','odor'))
        self.assertFalse(compatible('vision','odor'))
        self.assertFalse(compatible('terrain','vision'))
        self.assertFalse(compatible('avoidance','odor'))
        self.state['task'] = 'vision'
        self.save()
        with self.assertRaisesRegex(ValueError, 'anatomical modality'):
            Policy(self.directory / 'trained.npz')

    def test_visual_signal_comes_from_rgb_pixels(self):
        pixels = np.zeros((2,20,20,3),dtype=np.uint8)
        np.testing.assert_array_equal(visual_signal(pixels),[0,0])
        pixels[0,5:15,5:15,0] = 255
        self.assertGreater(visual_signal(pixels)[0],.2)
        self.assertEqual(visual_signal(pixels)[1],0)
        np.testing.assert_allclose(visual_signal(pixels[::-1]),visual_signal(pixels)[::-1])
        pixels[:] = 255  # A white image is not the red target.
        np.testing.assert_array_equal(visual_signal(pixels),[0,0])


if __name__ == '__main__':
    unittest.main()
