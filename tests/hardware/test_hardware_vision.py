"""Synthetic marker tests only; no serial port or camera is opened."""
import unittest
from unittest.mock import Mock
import cv2
import numpy as np
from so101.hardware_vision import AccessoryVision


def scene(ids):
    frame=np.full((320,640,3),230,np.uint8)
    dictionary=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    for i,marker in enumerate(ids):
        image=cv2.aruco.generateImageMarker(dictionary,marker,120)
        frame[100:220,50+i*180:170+i*180]=image[:,:,None]
    return frame


class VisionTests(unittest.TestCase):
    def test_real_dictionary_ids_are_not_metric_pose_or_brain_input(self):
        result=AccessoryVision().observe(scene([200,211]),1)
        self.assertTrue(result['cube_visible']);self.assertTrue(result['bin_visible'])
        self.assertEqual([d['object'] for d in sorted(result['detections'],key=lambda d:d['id'])],['cube_red','sort_bin'])
        self.assertFalse(result['metric_pose_valid']);self.assertFalse(result['policy_input_ready'])
        self.assertFalse(result['brain_connected']);self.assertIsNone(result['robot_pose'])
        cube=next(d for d in result['detections'] if d['id']==200)
        np.testing.assert_allclose(cube['center_px'],[109.5,159.5],atol=1)

    def test_missing_marker_never_reuses_last_position(self):
        detector=AccessoryVision();self.assertTrue(detector.observe(scene([200]),1)['cube_visible'])
        result=detector.observe(scene([]),2)
        self.assertFalse(result['cube_visible']);self.assertEqual(result['detections'],[])
        self.assertEqual(result['frame_sequence'],2)

    def test_duplicate_ids_are_ambiguous(self):
        result=AccessoryVision().observe(scene([200,200]),1)
        self.assertEqual(result['duplicate_ids'],[200]);self.assertFalse(result['cube_visible'])
        self.assertTrue(all(not d['unique'] for d in result['detections']))

    def test_unknown_tag_not_misidentified_as_bin(self):
        result=AccessoryVision().observe(scene([201]),1)
        self.assertEqual(result['detections'],[]);self.assertFalse(result['bin_visible'])

    def test_invalid_or_tiny_corners_do_not_pass(self):
        detector=AccessoryVision();detector.detector=Mock()
        for points in (np.array([[1,1],[2,1],[2,2],[1,2]],float),np.full((4,2),float('nan')),
                       np.array([[-1,0],[100,0],[100,100],[-1,100]],float)):
            detector.detector.detectMarkers.return_value=([points],np.array([[200]]),[])
            self.assertEqual(detector.observe(scene([]),1)['detections'],[])

    def test_annotation_does_not_change_observations(self):
        detector=AccessoryVision();frame=scene([200]);result=detector.observe(frame,1)
        before=frame.copy();copy=detector.annotate(frame.copy(),result)
        np.testing.assert_array_equal(frame,before);self.assertFalse(np.array_equal(frame,copy))


if __name__=='__main__':unittest.main()
