"""Capture failure/geometry boundaries, without opening a camera or serial port."""
import unittest
from unittest.mock import Mock,patch

import numpy as np

from so101.hardware_worker import read_camera_frame


class CameraCaptureTests(unittest.TestCase):
    def setUp(self):
        self.now=0.
        self.frame=np.zeros((720,1280,3),dtype=np.uint8)
        self.clock=patch('so101.hardware_worker.time.monotonic',side_effect=lambda:self.now)
        self.sleep=patch('so101.hardware_worker.time.sleep',side_effect=self.advance)
        self.clock.start();self.sleep.start()
        self.addCleanup(self.clock.stop);self.addCleanup(self.sleep.stop)

    def advance(self,seconds):
        self.now+=seconds

    def test_transient_failure_does_not_reuse_failed_frame(self):
        stale=np.ones_like(self.frame)
        camera=Mock();camera.read.side_effect=[(False,stale),(True,None),(True,self.frame)]
        frame,stats=read_camera_frame(camera,10)
        self.assertIs(frame,self.frame)
        self.assertEqual(stats,dict(read_failures=2,resolution_mismatches=0))

    def test_initial_wrong_resolution_is_discarded_not_scaled(self):
        wrong=np.zeros((1080,1920,3),dtype=np.uint8)
        camera=Mock();camera.read.side_effect=[(True,wrong),(True,self.frame)]
        frame,stats=read_camera_frame(camera,10)
        self.assertIs(frame,self.frame)
        self.assertEqual(stats['resolution_mismatches'],1)

    def test_persistent_wrong_resolution_fails(self):
        camera=Mock();camera.read.return_value=(True,np.zeros((480,640,3),dtype=np.uint8))
        with self.assertRaisesRegex(OSError,'çözünürlüğü'):
            read_camera_frame(camera,10)
        self.assertEqual(camera.read.call_count,30)

    def test_persistent_loss_stops_at_attempt_limit(self):
        camera=Mock();camera.read.return_value=(False,None)
        with self.assertRaises(OSError):read_camera_frame(camera,10)
        self.assertEqual(camera.read.call_count,30)

    def test_late_frame_cannot_cross_session_deadline(self):
        def read():
            self.advance(.2)
            return True,self.frame
        camera=Mock();camera.read.side_effect=read
        with self.assertRaises(OSError):read_camera_frame(camera,.1)
        self.assertEqual(camera.read.call_count,1)

    def test_slow_failures_stop_at_time_limit(self):
        def read():
            self.advance(1.01)
            return False,None
        camera=Mock();camera.read.side_effect=read
        with self.assertRaises(OSError):read_camera_frame(camera,10)
        self.assertEqual(camera.read.call_count,3)

    def test_expired_session_does_not_read_device(self):
        camera=Mock()
        with self.assertRaises(OSError):read_camera_frame(camera,0)
        camera.read.assert_not_called()


if __name__=='__main__':unittest.main()
