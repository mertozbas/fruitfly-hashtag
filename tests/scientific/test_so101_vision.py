"""Camera provenance and bounded recovery tests, with optional asset checks."""
import base64
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import numpy as np

from so101.recovery import RetrySupervisor


class RecoveryTests(unittest.TestCase):
    def test_dropped_cube_restarts_memory_without_world_access(self):
        r=RetrySupervisor(3);policy=SimpleNamespace(reset=Mock())
        obs=np.zeros(30,np.float32);obs[21]=.5;obs[22]=1;obs[23]=1
        r.observe(obs,1.,policy)
        obs[21]=.1;obs[22]=0
        r.observe(obs,2.,policy)
        self.assertTrue(r.observe(obs,2.7,policy))
        policy.reset.assert_called_once();self.assertEqual(obs[23],0)
        self.assertEqual(r.status()['events'][0]['reason'],'grasp_lost')

    def test_three_attempts_are_a_hard_bound(self):
        r=RetrySupervisor(3);policy=SimpleNamespace(reset=Mock());obs=np.zeros(30)
        for t in (12.,24.,36.):r.observe(obs,t,policy)
        self.assertTrue(r.exhausted);self.assertEqual(policy.reset.call_count,2)
        self.assertEqual(r.attempt,3)

    def test_normal_release_in_bin_is_not_a_failed_grasp(self):
        r=RetrySupervisor();p=SimpleNamespace(reset=Mock());obs=np.zeros(30)
        obs[22]=1;r.observe(obs,1.,p)
        obs[22]=0;obs[24]=1
        for t in (2.,3.,13.,25.):r.observe(obs,t,p)
        p.reset.assert_not_called()

    def test_drop_after_twelve_seconds_waits_for_landing(self):
        r=RetrySupervisor();p=SimpleNamespace(reset=Mock());obs=np.zeros(30)
        obs[22]=1;obs[21]=.6;r.observe(obs,11.9,p)
        obs[22]=0;r.observe(obs,12.1,p)
        p.reset.assert_not_called()
        obs[21]=.1;r.observe(obs,12.8,p)
        p.reset.assert_called_once()
        self.assertEqual(r.events[0]['reason'],'grasp_lost')


class VisualSelectionTests(unittest.TestCase):
    def test_recovery_gain_cannot_hide_normal_regression_or_relabel_old_training(self):
        from so101 import vision_job
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);initial=root/'trained.npz';initial.write_bytes(b'original')
            (root/'training.json').write_text(json.dumps(dict(after_mse=.02,steps=16000)))
            directory=root/'candidate';directory.mkdir()
            def train(*args,**kwargs):
                (directory/'trained.npz').write_bytes(b'bc')
                (directory/'training.json').write_text(json.dumps(dict(after_mse=.001,steps=100,checkpoint_sha256='candidate')))
            def fit(*args,**kwargs):(directory/'readout-0.0001.npz').write_bytes(b'ridge')
            calls=[]
            def evaluate(path,episodes,start_seed,**kwargs):
                calls.append((episodes,start_seed,kwargs.get('variant')))
                if episodes==8 and kwargs.get('variant')!='silenced':
                    normal,recovery={'untrained.npz':(6,1),'bc-candidate.npz':(5,8),'readout-0.0001.npz':(6,0)}[path.name]
                    successes=recovery if kwargs.get('disturbance') else normal
                else:successes=0 if kwargs.get('variant')=='silenced' else 37 if episodes==40 else 12
                import hashlib
                return dict(episodes=episodes,success_count=successes,unsafe_count=0,checkpoint_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            with patch.object(vision_job,'train',train),patch.object(vision_job,'fit',fit),patch.object(vision_job,'evaluate',evaluate):
                result=vision_job.refine(directory,root/'data.npz',100,44,initial)
            self.assertEqual((directory/'trained.npz').read_bytes(),b'original')
            self.assertFalse(result['selected_model_changed']);self.assertFalse(result['acceptance_passed'])
            report=json.loads((directory/'training.json').read_text())
            self.assertEqual(report['after_mse'],.02);self.assertEqual(report['steps'],16000)
            self.assertEqual(json.loads((directory/'candidate-training.json').read_text())['steps'],100)
            self.assertEqual(calls[-3:],[(40,24400,None),(24,24440,None),(8,24400,'silenced')])


@unittest.skipUnless(os.environ.get('SO101_TEST_ASSETS')=='1','requires local MuJoCo assets')
class CameraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from so101.task import PickPlaceEnv
        from so101.perception import CameraObservation
        cls.env=PickPlaceEnv();cls.camera=CameraObservation(cls.env)

    @classmethod
    def tearDownClass(cls):cls.camera.close();cls.env.close()

    def setUp(self):self.env.reset(7010);self.camera.reset()

    def test_rgb_depth_preview_is_the_consumed_frame(self):
        from PIL import Image
        c=self.camera;e=self.env;obs=c.observation()
        truth=e.cube.copy();estimate=np.asarray(c.last['estimated_cube'])
        self.assertLess(np.linalg.norm(estimate-truth),.008)
        self.assertEqual(c.last['sample_time_s'],e.data.time)
        sample=c.tracker.rgb.copy();before=e.data.qpos.copy();frame=c.last['frame_id']
        previews=c.tracker.previews()
        self.assertEqual(set(previews),{'rgb','detection','depth'})
        decoded=np.asarray(Image.open(io.BytesIO(base64.b64decode(previews['rgb']))))
        self.assertEqual(decoded.shape,(480,640,3))
        self.assertLess(np.abs(decoded.astype(float)-sample).mean(),4.)
        np.testing.assert_array_equal(e.data.qpos,before)
        self.assertEqual(c.tracker.frame_id,frame)
        np.testing.assert_allclose(obs[15:18]*.15+e.ee,estimate,atol=1e-7)

    def test_invisible_cube_stops_without_truth_fallback(self):
        c=self.camera;e=self.env
        ids=[g for g in range(e.model.ngeom) if e.model.geom_bodyid[g]==e.cube_id and e.model.geom_group[g]==2]
        old=e.model.geom_rgba[ids].copy()
        try:
            e.model.geom_rgba[ids,:3]=.1
            with self.assertRaises(RuntimeError):c.observation()
            self.assertFalse(c.last['valid']);self.assertIsNone(c.last['estimated_cube'])
            self.assertIsNone(c.last['age_s'])
        finally:e.model.geom_rgba[ids]=old

    def test_camera_observation_cannot_read_object_pose(self):
        from so101.perception import CameraObservation
        env=self.env
        class SensorOnly:
            def __getattr__(self,name):
                if name in {'cube','observation','sensors'}:raise AssertionError('Hidden object-state read: '+name)
                return getattr(env,name)
        camera=CameraObservation(SensorOnly())
        try:
            obs=camera.observation()
            self.assertEqual(obs.shape,(30,));self.assertTrue(np.isfinite(obs).all())
        finally:camera.close()

    def test_short_occlusion_expires_after_half_a_second(self):
        c=self.camera;e=self.env;c.observation()
        ids=[g for g in range(e.model.ngeom) if e.model.geom_bodyid[g]==e.cube_id and e.model.geom_group[g]==2]
        old=e.model.geom_rgba[ids].copy()
        try:
            e.model.geom_rgba[ids,:3]=.1
            e.data.time=.2;c.observation()
            self.assertFalse(c.last['visible']);self.assertTrue(c.last['valid'])
            e.data.time=.501
            with self.assertRaises(RuntimeError):c.observation()
            self.assertFalse(c.last['valid'])
        finally:e.model.geom_rgba[ids]=old


if __name__=='__main__':unittest.main()
