"""HTTP validation for physical commissioning, using an entirely offline manager."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from so101.hardware import HardwareLab
from so101.hardware_api import router


class HardwareAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.hardware=HardwareLab(Path(self.temp.name),Path(self.temp.name)/'cal')
        self.addCleanup(self.hardware.close)
        app=FastAPI();app.include_router(router(self.hardware))
        self.client=TestClient(app);self.addCleanup(self.client.close)

    def test_absent_hardware_is_explicit_and_motion_always_locked(self):
        with patch('subprocess.Popen') as popen:
            s=self.client.get('/api/hardware/inventory').json()
            self.assertFalse(s['autonomous_ready']);self.assertFalse(s['environment_ready'])
            self.assertEqual(self.client.post('/api/hardware/motion',json={'targets':[1]*6}).status_code,423)
            self.assertEqual(self.client.post('/api/hardware/connect',json=dict(port='/dev/random',calibration_id='x')).status_code,409)
            popen.assert_not_called()

    def test_invalid_camera_and_extra_fields_never_spawn(self):
        with patch('subprocess.Popen') as popen:
            for body in [dict(role='wrist',index=-1),dict(role='top',index=16),dict(role='wrist',index=True),
                         dict(role='wrist',index='0'),dict(role='other',index=0),dict(role='wrist',index=0,move=True)]:
                self.assertEqual(self.client.post('/api/hardware/camera',json=body).status_code,422)
            self.assertEqual(self.client.post('/api/hardware/connect',json=dict(port='x',calibration_id='y',torque=True)).status_code,422)
            popen.assert_not_called()


if __name__=='__main__':unittest.main()
