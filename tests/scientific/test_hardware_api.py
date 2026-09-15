"""HTTP validation for physical commissioning, using an entirely offline manager."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
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

    def test_screen_calibration_requires_finite_measured_scale_or_explicit_unknown(self):
        body=dict(session='a'*32,role='top',op='enable',device_label='top',confirmed=True,target_medium='screen')
        with patch.object(self.hardware.commissioning,'camera_command',return_value={}) as command:
            for value in (True,'9',0,101):
                self.assertEqual(self.client.post('/api/hardware/camera/calibration',json=dict(body,target_square_mm=value)).status_code,422)
            command.assert_not_called()
            for value in (None,9.5):
                self.assertEqual(self.client.post('/api/hardware/camera/calibration',json=dict(body,target_square_mm=value)).status_code,200)
                self.assertEqual(command.call_args.args[2]['target_square_mm'],value)

    def test_calibration_absence_paths_and_schemas_fail_closed(self):
        with patch('subprocess.Popen') as popen:
            self.assertEqual(self.client.post('/api/hardware/calibration/start',json=dict(port='/dev/random',robot_id='follower')).status_code,409)
            for body in [dict(port='x',robot_id='../outside'),dict(port='x',robot_id='ok',backup_id='../x')]:
                self.assertEqual(self.client.post('/api/hardware/calibration/start',json=body).status_code,422)
            for body in [dict(session='a'*32,revision=1,op='torque_on'),dict(session='a'*32,revision=1,op='release',supported='true')]:
                self.assertEqual(self.client.post('/api/hardware/calibration/command',json=body).status_code,422)
            self.assertEqual(self.client.post('/api/hardware/camera/calibration',json=dict(session='a'*32,role='wrist',op='enable',device_label='UVC')).status_code,422)
            self.assertEqual(self.client.post('/api/hardware/camera',json=dict(role='wrist',index=0,profile_id='../../secret',device_verified=True)).status_code,409)
            self.assertEqual(self.client.get('/api/hardware/calibration/report',params=dict(kind='motor',record_id='../../secret')).status_code,409)
            popen.assert_not_called()

    def test_session_revision_and_one_pending_command(self):
        worker=Mock();worker.session='a'*32;worker.pending_revision=None;worker.kind='calibration'
        current=dict(running=True,fresh=True,revision=1);worker.snapshot.side_effect=lambda:dict(current)
        self.hardware.processes['calibration']=worker
        body=dict(session=worker.session,revision=1,op='release',supported=True)
        with patch.object(self.hardware,'state',return_value={}):
            self.assertEqual(self.client.post('/api/hardware/calibration/command',json=dict(body,session='b'*32)).status_code,409)
            self.assertEqual(self.client.post('/api/hardware/calibration/command',json=body).status_code,200)
            self.assertEqual(self.client.post('/api/hardware/calibration/command',json=body).status_code,409)
            worker.send.assert_called_once()
            current.update(revision=2,fresh=False)
            self.assertEqual(self.client.post('/api/hardware/calibration/command',json=dict(body,revision=2)).status_code,409)
            self.assertEqual(self.client.post('/api/hardware/calibration/command',json=dict(body,op='cancel')).status_code,200)
        self.hardware.processes.clear()

    def test_failed_backup_is_listed_for_recovery(self):
        import json
        d=self.hardware.commissioning.root/'motors'/('a'*32);d.mkdir(parents=True)
        (d/'backup.json').write_text(json.dumps(dict(target='/tmp/follower.json',created=1)))
        (d/'status.json').write_text(json.dumps(dict(stage='failed',warning='USB disconnected')))
        self.assertTrue(self.hardware.commissioning.histories()[0]['recovery_needed'])


if __name__=='__main__':unittest.main()
