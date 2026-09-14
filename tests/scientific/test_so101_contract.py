"""Robot neural contracts, independent of downloaded robot/anatomy assets."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from scipy import sparse
from odor_policy import Circuit
from so101.policy import Policy,OBS_SIZE,MEMORY_SIZE,torch_model


class RobotPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        groups=['Touch','VNC_relay','VNC_premotor','Motor']
        layers=[]
        for i in range(3):
            p=self.root/f'layer{i}.npz';sparse.save_npz(p,sparse.eye(3,dtype=np.float32,format='csr'))
            layers.append(dict(file=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
        ids=self.root/'body_ids.npz'
        np.savez_compressed(ids,**{g:np.arange(i*3,i*3+3) for i,g in enumerate(groups)},orn_side=[0,1,0])
        meta=dict(task='so101',group_order=groups,groups={g:3 for g in groups},layers=layers,body_ids_sha256=hashlib.sha256(ids.read_bytes()).hexdigest())
        (self.root/'circuit.json').write_text(json.dumps(meta))
        self.circuit=Circuit(self.root)
        self.actor=torch_model(self.circuit,np.zeros(OBS_SIZE),np.ones(OBS_SIZE))
        self.path=self.root/'trained.npz';self.actor.save(self.path)

    def test_numpy_torch_and_live_activity_agree(self):
        import torch
        policy=Policy(self.path)
        x=np.random.default_rng(4).normal(size=(6,OBS_SIZE)).astype(np.float32)
        with torch.no_grad():expected=self.actor(torch.from_numpy(x)).numpy()
        for row,wanted in zip(x,expected):
            action,layers=policy.activity(row)
            np.testing.assert_allclose(action,wanted,atol=1e-5)
            np.testing.assert_array_equal(policy(row),action)
            self.assertEqual([len(a) for a in layers],[3]*4)
            self.assertTrue(all(((a>=0)&(a<=1)).all() for a in layers))

    def mutate(self,key,value):
        with np.load(self.path) as s:state={k:s[k].copy() for k in s.files}
        state[key]=value;np.savez_compressed(self.path,**state)

    def test_nonanatomical_edges_rejected(self):
        w=np.eye(3,dtype=np.float32);w[0,1]=.1;self.mutate('weight',w)
        with self.assertRaisesRegex(ValueError,'anatomical mask'):Policy(self.path)

    def test_shape_nonfinite_and_negative_scaling_rejected(self):
        policy=Policy(self.path)
        for x in [np.zeros(2),np.full(OBS_SIZE,np.nan),np.zeros((1,OBS_SIZE))]:
            with self.assertRaises(ValueError):policy(x)
        self.mutate('input_scale',-np.ones(OBS_SIZE))
        with self.assertRaises(ValueError):Policy(self.path)

    def test_checkpoint_identity_and_gain_bounds(self):
        self.mutate('circuit_identity','foreign')
        with self.assertRaisesRegex(ValueError,'mismatch'):Policy(self.path)
        self.actor.save(self.path);self.mutate('weight',np.eye(3)*5)
        with self.assertRaisesRegex(ValueError,'bounds'):Policy(self.path)

    def test_silencing_internal_signal_changes_motor_output(self):
        policy=Policy(self.path);x=np.zeros(OBS_SIZE)
        a,layers=policy.activity(x)
        disconnected=np.tanh(np.zeros(3)@policy.decoder+policy.bias)
        self.assertFalse(np.allclose(a,disconnected))

    def test_memory_is_learned_reproducible_feedback(self):
        import torch
        actor=torch_model(self.circuit,np.zeros(OBS_SIZE+MEMORY_SIZE),np.ones(OBS_SIZE+MEMORY_SIZE))
        actor.save(self.path);p=Policy(self.path);x=np.zeros(OBS_SIZE,dtype=np.float32)
        before=p.memory.copy();features=p.augmented(x)
        with torch.no_grad():logits,layers,_=actor(torch.from_numpy(features)[None,:],details=True)
        action,actual=p.activity(x)
        np.testing.assert_array_equal(p.memory,before) # inspection must not advance memory
        np.testing.assert_allclose(action,torch.tanh(logits)[0].numpy(),atol=1e-5)
        expected=int(actor.memory_decoder(layers[-1]).argmax(-1)[0])
        p(x);self.assertEqual(int(p.memory.argmax()),expected)
        p.reset();np.testing.assert_array_equal(p.memory,before)
        # Full input including previous memory replays the exact same forward pass.
        np.testing.assert_array_equal(p.activity(features)[0],action)

    def test_memory_cannot_bypass_the_anatomical_core(self):
        actor=torch_model(self.circuit,np.zeros(OBS_SIZE+MEMORY_SIZE),np.ones(OBS_SIZE+MEMORY_SIZE))
        actor.save(self.path);p=Policy(self.path)
        action,layers=p.activity(np.zeros(OBS_SIZE))
        np.testing.assert_allclose(action,np.tanh(layers[-1]@p.decoder+p.bias),atol=1e-6)
        p.memory_weight=np.zeros_like(p.memory_weight);p.memory_bias=np.arange(MEMORY_SIZE,dtype=np.float32)
        p(np.zeros(OBS_SIZE));self.assertEqual(int(p.memory.argmax()),MEMORY_SIZE-1)

    def test_learned_motor_heads_match_torch_and_selected_neural_readout(self):
        import torch
        actor=torch_model(self.circuit,np.zeros(OBS_SIZE+MEMORY_SIZE),np.ones(OBS_SIZE+MEMORY_SIZE),motor_heads=MEMORY_SIZE)
        actor.save(self.path);p=Policy(self.path);x=np.zeros(OBS_SIZE,dtype=np.float32)
        with torch.no_grad():expected=actor(torch.from_numpy(p.augmented(x))[None,:])[0].numpy()
        action,layers=p.activity(x)
        np.testing.assert_allclose(action,expected,atol=1e-5)
        phase=int(np.argmax(layers[-1]@p.memory_weight+p.memory_bias))
        np.testing.assert_allclose(action,np.tanh(p.motor_logits(layers[-1],phase)),atol=1e-6)
        p(x);self.assertEqual(int(p.memory.argmax()),phase)

    def test_all_anatomical_layers_learn_with_portable_parity(self):
        import torch
        actor=torch_model(self.circuit,np.zeros(OBS_SIZE),np.ones(OBS_SIZE),all_core=True)
        with torch.no_grad():
            actor.raw_gain0.fill_(.3);actor.raw_gain1.fill_(-.2);actor.raw_gain.fill_(.1)
        actor.save(self.path);p=Policy(self.path)
        x=np.random.default_rng(9).normal(size=(4,OBS_SIZE)).astype(np.float32)
        with torch.no_grad():expected=actor(torch.from_numpy(x)).numpy()
        np.testing.assert_allclose(np.stack([p(row) for row in x]),expected,atol=1e-5)
        self.assertTrue(p.all_core)
        self.assertTrue((p.early_weights[0].diagonal()>1).all())
        bad=p.early_weights[0].copy();bad[0,1]=.2;self.mutate('weight0',bad)
        with self.assertRaisesRegex(ValueError,'early anatomical'):Policy(self.path)

    def test_empirical_transition_support_has_no_builtin_phase_order(self):
        import torch
        actor=torch_model(self.circuit,np.zeros(OBS_SIZE+MEMORY_SIZE),np.ones(OBS_SIZE+MEMORY_SIZE),motor_heads=MEMORY_SIZE)
        with torch.no_grad():
            actor.start_counts[5]=3
            actor.transition_counts[5,2]=7 # arbitrary learned edge, not next phase
        actor.save(self.path);p=Policy(self.path)
        self.assertEqual(p.memory.argmax(),5)
        x=np.zeros(OBS_SIZE,dtype=np.float32)
        with torch.no_grad():expected=actor(torch.from_numpy(p.augmented(x))[None,:])[0].numpy()
        actual=p(x);self.assertEqual(p.memory.argmax(),2)
        np.testing.assert_allclose(actual,expected,atol=1e-5)
        p.reset();self.assertEqual(p.memory.argmax(),5)

    def test_task_feature_mask_and_actual_neural_ablation(self):
        actor=torch_model(self.circuit,np.zeros(OBS_SIZE),np.ones(OBS_SIZE),task_features=True,action_mode='target')
        actor.save(self.path);p=Policy(self.path)
        a=np.zeros(OBS_SIZE,dtype=np.float32);b=a.copy();b[p.input_mask==0]=4
        np.testing.assert_array_equal(p(a),p(b))
        self.assertEqual(p.action_mode,'target')
        action,layers=p.activity(a,silenced=True)
        self.assertTrue(all(np.count_nonzero(h)==0 for h in layers))
        np.testing.assert_allclose(action,np.tanh(p.bias),atol=1e-6)


if __name__=='__main__':unittest.main()
