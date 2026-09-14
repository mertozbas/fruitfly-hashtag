"""Known-projection camera fixtures; no camera is opened."""
from pathlib import Path
import tempfile
import time
import unittest
import cv2
import numpy as np
from so101.calibration_camera import CameraCalibration,base_board,board,pose_fit,solve_lens,transform


def camera_samples():
    rng=np.random.default_rng(92);objects=board().getChessboardCorners();samples=[];k=np.array([[910.,0,640],[0,900,360],[0,0,1]])
    d=np.array([.03,-.02,.001,-.0005,0.])
    while len(samples)<24:
        r=rng.uniform(-.6,.6,3);t=np.array([rng.uniform(-.18,.10),rng.uniform(-.16,.04),rng.uniform(.35,.55)])
        pixels=cv2.projectPoints(objects,r,t,k,d)[0]
        if pixels[:,:,0].min()<15 or pixels[:,:,0].max()>1265 or pixels[:,:,1].min()<15 or pixels[:,:,1].max()>705:continue
        samples.append(dict(objects=objects.copy(),pixels=(pixels+rng.normal(0,.035,pixels.shape)).astype(np.float32),ids=np.arange(35),size=(1280,720)))
    return samples,k,d


class CameraCalibrationTests(unittest.TestCase):
    def test_lens_solution_matches_known_camera_and_heldout_views(self):
        samples,k,_=camera_samples();result=solve_lens(samples,(1280,720));actual=np.array(result['camera_matrix'])
        self.assertLess(result['rms_px'],.15);self.assertLess(max(result['holdout_rms_px']),.2)
        np.testing.assert_allclose(actual[[0,1],[0,1]],k[[0,1],[0,1]],rtol=.02)
        self.assertEqual(result['holdout_samples'],4);self.assertEqual(result['training_samples'],20)

    def test_insufficient_repeated_and_blurred_observations_rejected(self):
        samples,_,_=camera_samples()
        with self.assertRaises(ValueError):solve_lens(samples[:10],(1280,720))
        with self.assertRaises(ValueError):solve_lens([samples[0]]*24,(1280,720))
        with tempfile.TemporaryDirectory() as temp:
            c=CameraCalibration(temp,'wrist',0);c.enabled=True;c.size=(1280,720);c.frame_time=time.monotonic();c.frame_id=1
            c.corners=samples[0]['pixels'];c.ids=samples[0]['ids'][:,None];c.area=.1;c.sharpness=2
            with self.assertRaisesRegex(ValueError,'bulanık'):c.command(dict(op='capture',command_id='1'))
            c.sharpness=100;c.command(dict(op='capture',command_id='2'))
            with self.assertRaisesRegex(ValueError,'benziyor'):c.command(dict(op='capture',command_id='3'))

    def test_marked_board_detected_and_rgb_pose_composes_in_right_direction(self):
        with tempfile.TemporaryDirectory() as temp:
            c=CameraCalibration(temp,'wrist',0);c.command(dict(op='enable',device_label='OFFLINE',command_id='1',confirmed=True))
            raster=board().generateImage((600,800));frame=np.full((1000,900,3),255,np.uint8);frame[100:900,150:750]=cv2.cvtColor(raster,cv2.COLOR_GRAY2BGR)
            c.observe(frame,1);self.assertEqual(c.state()['detected_corners'],35)
            samples,k,d=camera_samples();r,t,error=pose_fit(samples[1]['objects'],samples[1]['pixels'],k,d)
            c.saved=dict(session='original',size=[900,1000]);c.live_pose=dict(camera_from_board=transform(r,t).tolist(),reprojection_px=error);c.frame_time=time.monotonic()
            pose=[125.,-170.,20.,0.,0.,90.]
            c.command(dict(op='workspace',confirmed=True,base_pose=pose,command_id='2'))
            got=np.array(c.workspace['base_from_camera'])@np.array(c.workspace['camera_from_board'])
            np.testing.assert_allclose(got,base_board(pose),atol=1e-9)
            self.assertFalse(c.workspace['hand_eye_calibrated']);self.assertFalse(c.workspace['physical_alignment_verified'])

    def test_pose_requires_current_detection_and_finite_anchor(self):
        for pose in ([0]*5,[float('nan')]*6,[99999,0,0,0,0,0]):
            with self.assertRaises(ValueError):base_board(pose)
        with tempfile.TemporaryDirectory() as temp:
            c=CameraCalibration(temp,'top',0);c.enabled=True
            with self.assertRaises(ValueError):c.command(dict(op='workspace',confirmed=True,command_id='1'))

    def test_profile_identity_and_resolution_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            c=CameraCalibration(temp,'wrist',0)
            with self.assertRaises(ValueError):c.command(dict(op='enable',command_id='1',device_label='UVC'))
            c.saved=dict(device_label='UVC',size=[1280,720])
            with self.assertRaises(ValueError):c.command(dict(op='enable',command_id='2',device_label='OTHER',confirmed=True))
            c.command(dict(op='enable',command_id='3',device_label='UVC',confirmed=True))
            c.observe(np.zeros((480,640,3),np.uint8),1)
            self.assertIsNone(c.live_pose);self.assertIsNone(c.ids);self.assertIn('Çözünürlük',c.warning)


if __name__=='__main__':unittest.main()
