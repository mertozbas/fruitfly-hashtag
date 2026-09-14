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
    def test_progress_checks_forbid_transport_without_grasp(self):
        from so101.phase_supervision import feasible_phases
        obs=np.zeros(30,np.float32);obs[5]=.9
        obs[12:15]=([.03,-.21,.08]-np.array([.06,-.18,.06]))/.15
        obs[15:18]=[0,0,-.065/.15]
        obs[18:21]=[.8,.3,0]
        obs[21]=.1
        allowed=feasible_phases(obs)
        self.assertFalse(allowed[0]) # aligned approach has completed
        self.assertTrue(allowed[1]);self.assertFalse(allowed[4])
        before=obs.copy();feasible_phases(obs);np.testing.assert_array_equal(obs,before)

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
            from so101.camera_mount import PROFILE
            np.savez(root/'data.npz',camera_name='wrist',camera_profile=PROFILE)
            (root/'training.json').write_text(json.dumps(dict(after_mse=.02,steps=16000)))
            directory=root/'candidate';directory.mkdir()
            def train(*args,**kwargs):
                (directory/'trained.npz').write_bytes(b'bc')
                (directory/'training.json').write_text(json.dumps(dict(after_mse=.001,steps=100,checkpoint_sha256='candidate')))
            def fit(*args,**kwargs):(directory/'phase-readout-0.0001.npz').write_bytes(b'ridge')
            calls=[]
            def evaluate(path,episodes,start_seed,**kwargs):
                calls.append((episodes,start_seed,kwargs.get('variant')))
                if episodes==8 and kwargs.get('variant')!='silenced':
                    normal,recovery={'untrained.npz':(6,1),'bc-candidate.npz':(5,8),'phase-readout-0.0001.npz':(6,0)}[path.name]
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

    def test_front_camera_data_cannot_silently_train_wrist_policy(self):
        from so101.vision_job import refine
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);np.savez(root/'front.npz',camera_name='front')
            with self.assertRaisesRegex(ValueError,'camera differs'):
                refine(root/'candidate',root/'front.npz',200,44,root/'unused.npz')

    def test_old_wrist_mount_data_is_rejected_before_training(self):
        from so101.vision_job import refine
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);np.savez(root/'old.npz',camera_name='wrist')
            with self.assertRaisesRegex(ValueError,'calibration profile differs'):
                refine(root/'candidate',root/'old.npz',200,44,root/'unused.npz')


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

    def test_wrist_camera_moves_and_rotates_rigidly_with_gripper(self):
        import mujoco
        c=self.camera;e=self.env;c.observation()
        cam=c.tracker.camera_id;body=e.model.body('gripper').id
        self.assertEqual(c.last['camera_name'],'wrist');self.assertEqual(c.last['camera_mount'],'gripper')
        before=e.data.cam_xpos[cam].copy();rotation=e.data.cam_xmat[cam].reshape(3,3).copy()
        rb=e.data.xmat[body].reshape(3,3).copy()
        offset=rb.T@(before-e.data.xpos[body]);local_rotation=rb.T@rotation
        e.data.qpos[e.qadr[0]]+=.1;e.data.qpos[e.qadr[4]]+=.3
        mujoco.mj_forward(e.model,e.data);c.observation()
        rb=e.data.xmat[body].reshape(3,3)
        self.assertGreater(np.linalg.norm(e.data.cam_xpos[cam]-before),.005)
        self.assertGreater(np.linalg.norm(e.data.cam_xmat[cam].reshape(3,3)-rotation),.1)
        np.testing.assert_allclose(rb.T@(e.data.cam_xpos[cam]-e.data.xpos[body]),offset,atol=1e-8)
        np.testing.assert_allclose(rb.T@e.data.cam_xmat[cam].reshape(3,3),local_rotation,atol=1e-8)
        self.assertLess(np.linalg.norm(np.asarray(c.last['estimated_cube'])-e.cube),.008)

    def test_official_mount_holes_match_actual_wrist_nut_recesses(self):
        import trimesh
        from so101.camera_mount import ROTATION,TRANSLATION,BOARD,BACK,EYE
        from so101.engine import ROBOT_SOURCE
        # Independent source STEP hole coordinates, checked against vertices
        # of the wrist STL actually used by MuJoCo, not just another constant.
        mesh=trimesh.load(ROBOT_SOURCE/'assets/wrist_roll_follower_so101_v1.stl')
        holes=np.array([[-.005,-.020718214,.02435],[.0031,-.020718214,.02435]])
        for centre in holes:
            v=mesh.vertices
            near=v[(np.abs(v[:,1]-centre[1])<1e-6)&(np.linalg.norm(v[:,[0,2]]-centre[[0,2]],axis=1)<.0017)]
            self.assertGreater(len(near),10)
            np.testing.assert_allclose(np.linalg.norm(near[:,[0,2]]-centre[[0,2]],axis=1),.0016,atol=2e-6)
        mount_holes=np.array([[-4,-8.15,10],[-4,-8.15,18.1]])*.001
        transformed=mount_holes@ROTATION.T+TRANSLATION
        wrist_holes=holes*np.array([1,-1,-1])+[0,-.000218214,.000949706]
        np.testing.assert_allclose(transformed[:,[0,2]],wrist_holes[:,[0,2]],atol=1e-8)
        self.assertAlmostEqual(TRANSLATION[1],.024) # outer mating plane
        np.testing.assert_allclose((BOARD-EYE)/.016,BACK,atol=1e-8)

    def test_rotated_cube_estimate_uses_visible_surfaces(self):
        import mujoco
        from scipy.spatial.transform import Rotation
        e=self.env;c=self.camera
        e.reset(cube=[.03,-.21,.03])
        q=Rotation.from_euler('xyz',[.3,.4,.6]).as_quat()
        e.data.qpos[e.cube_qpos+3:e.cube_qpos+7]=q[[3,0,1,2]]
        mujoco.mj_forward(e.model,e.data)
        c.observation()
        self.assertLess(np.linalg.norm(np.asarray(c.last['estimated_cube'])-e.cube),.008)

    def test_spectator_orbit_does_not_change_the_robot_eye(self):
        c=self.camera;e=self.env;c.observation();before=c.tracker.rgb.copy()
        e.camera.azimuth+=90;e.camera.elevation=-80;e.camera.distance=.2
        c.observation()
        np.testing.assert_array_equal(c.tracker.rgb,before)

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
