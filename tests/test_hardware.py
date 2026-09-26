"""Offline commissioning contracts. Never opens a physical port or camera."""
import copy
from contextlib import redirect_stderr,redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock,patch

from so101.hardware import DiagnosticProcess,HardwareLab
from so101.hardware_contract import JOINTS,assert_read_packet,calibration,joint_value,readiness,signed_magnitude


def saved_motors():
    return {name:dict(id=i,drive_mode=0,homing_offset=-188,range_min=700,range_max=3400) for i,name in enumerate(JOINTS,1)}


def packet(instruction,params=(),motor=1):
    body=[motor,len(params)+2,instruction,*params]
    return bytes([255,255,*body,(~sum(body))&255])


class ContractTests(unittest.TestCase):
    def test_read_packets_only(self):
        for motor in range(1,7):
            for p in (packet(1,motor=motor),packet(2,[56,2],motor)):
                self.assertEqual(assert_read_packet(p),p)
        for p in (packet(3,[40,1]),packet(3,[42,0,8]),packet(4,[40,1]),packet(5),packet(6),
                  packet(0x83,[40,1,1,1],254),packet(2,[56,2],254),packet(2,[56,0]),
                  packet(2,[70,16]),packet(1,motor=7),b'bad',packet(2,[56,2])[:-1]+b'\x00'):
            with self.assertRaises(PermissionError):assert_read_packet(p)

    def test_calibration_identity_and_ranges(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'cal.json';motors=saved_motors();path.write_text(json.dumps(motors))
            initial=calibration(path);self.assertTrue(initial['valid'])
            for field,value in [('id',2),('drive_mode',3),('range_min',3500),('homing_offset',9999),('id',True)]:
                bad=copy.deepcopy(motors);bad['shoulder_pan'][field]=value;path.write_text(json.dumps(bad))
                self.assertFalse(calibration(path)['valid']);self.assertNotEqual(calibration(path)['sha256'],initial['sha256'])
            path.write_text('{}')
            with self.assertRaises(ValueError):calibration(path)

    def test_real_degrees_do_not_subtract_offset_again(self):
        cal=saved_motors()['shoulder_pan']
        value,unit=joint_value('shoulder_pan',2050,cal);self.assertEqual((value,unit),(0,'°'))
        self.assertAlmostEqual(joint_value('shoulder_pan',2460,cal)[0],410*360/4095)
        self.assertEqual(joint_value('gripper',700,cal),(0,'%'))
        self.assertEqual(joint_value('gripper',700,dict(cal,drive_mode=1)),(100,'%'))
        self.assertGreater(joint_value('gripper',4095,cal)[0],100)
        self.assertEqual(signed_magnitude(2048+188,11),-188)

    def test_preparation_never_claims_motion_is_commissioned(self):
        checks=readiness(dict(valid=True),dict(connected=True,motors=[{}]*6,calibration_match=True),
                         {role:dict(fresh=True) for role in ('wrist','top')})
        self.assertEqual(sum(c['passed'] for c in checks),5)
        self.assertTrue(all(not c['passed'] for c in checks[-4:]))

    def test_fresh_marker_and_joint_ranges_are_separate_from_calibration(self):
        arm=dict(connected=True,calibration_match=True,motors=[dict(name=n,in_calibrated_range=True) for n in JOINTS])
        cameras={r:dict(fresh=True,sequence=10,perception=dict(frame_sequence=10,cube_visible=True,bin_visible=True)) for r in ('wrist','top')}
        def checks():return {c['id']:c['passed'] for c in readiness(dict(valid=True),arm,cameras)}
        self.assertTrue(checks()['joint_ranges']);self.assertTrue(checks()['cube_marker']);self.assertTrue(checks()['bin_marker'])
        arm['motors'][2]['in_calibrated_range']=False
        self.assertFalse(checks()['joint_ranges']);self.assertTrue(checks()['live_calibration'])
        cameras['top']['sequence']=11
        self.assertFalse(checks()['bin_marker']);self.assertTrue(checks()['cube_marker'])
        cameras['wrist']['fresh']=False
        self.assertFalse(checks()['cube_marker']);self.assertFalse(checks()['vision_geometry'])

    def test_tray_and_ambiguous_container_readiness(self):
        camera=dict(fresh=True,sequence=8,perception=dict(frame_sequence=8,container_visible=True,bin_visible=False))
        def ready():return {c['id']:c['passed'] for c in readiness(None,{},dict(top=camera,wrist={}))}
        self.assertTrue(ready()['bin_marker']);self.assertFalse(ready()['vision_geometry'])
        camera['perception'].update(container_visible=False,bin_visible=True)
        self.assertFalse(ready()['bin_marker']) # Two containers must not fall back to the old bin flag.
        camera['perception']['container_visible']=True;camera['fresh']=False
        self.assertFalse(ready()['bin_marker'])


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);calroot=self.root/'cal';(calroot/'so_follower').mkdir(parents=True)
        self.calfile=calroot/'so_follower/test.json';self.calfile.write_text(json.dumps(saved_motors()))
        self.lab=HardwareLab(self.root,calroot);self.addCleanup(self.lab.close)

    def test_inventory_missing_environment_and_no_device_open(self):
        with patch('subprocess.Popen') as popen:
            state=self.lab.inventory();popen.assert_not_called()
        self.assertFalse(state['environment_ready']);self.assertEqual(state['inventory']['ports'],[])
        self.assertFalse(state['autonomous_ready']);self.assertEqual(len(state['calibrations']),1)
        self.assertFalse(state['simulation_connected_to_hardware'])

    def test_arbitrary_port_and_calibration_paths_rejected(self):
        self.lab.cached_inventory['ports']=[dict(device='/dev/cu.usbTEST')]
        with patch.object(self.lab,'inventory'),patch('so101.hardware.DiagnosticProcess') as process:
            for port,cal in [('/dev/cu.secret','so_follower/test.json'),('/dev/cu.usbTEST','../../secret.json')]:
                with self.assertRaises(ValueError):self.lab.connect(port,cal)
            process.assert_not_called()

    def test_camera_selection_rejects_duplicate_roles_and_bad_indices(self):
        for index in (-1,16,1.5,True):
            with self.assertRaises(ValueError):self.lab.camera('wrist',index)
        worker=Mock(index=2);worker.snapshot.return_value=dict(running=True)
        self.lab.processes['wrist']=worker
        with self.assertRaisesRegex(ValueError,'zaten'):self.lab.camera('top',2)

    def test_calibration_edit_invalidates_match(self):
        self.lab.selected=self.lab.calibrations()[0]
        worker=Mock();worker.snapshot.return_value=dict(connected=True,running=True,calibration_match=True,motors=[{}]*6,
                            calibration_sha256=self.lab.selected['sha256'])
        self.lab.processes['arm']=worker
        self.assertTrue(next(c for c in self.lab.state()['checks'] if c['id']=='live_calibration')['passed'])
        motors=saved_motors();motors['shoulder_pan']['homing_offset']=10;self.calfile.write_text(json.dumps(motors))
        self.assertFalse(next(c for c in self.lab.state()['checks'] if c['id']=='live_calibration')['passed'])

    def test_idle_lease_closes_worker_without_motion(self):
        worker=Mock(started=time.monotonic());worker.process.poll.return_value=None
        self.lab.processes['arm']=worker;self.lab.last_poll=time.monotonic()-100
        self.lab.start()
        self.assertTrue(worker.stop.call_count==0)
        deadline=time.monotonic()+3
        while not worker.stop.called and time.monotonic()<deadline:time.sleep(.05)
        worker.stop.assert_called_once();self.assertEqual(self.lab.processes,{})

    def test_finished_or_stale_camera_never_displays_as_live(self):
        process=DiagnosticProcess([sys.executable,'-u','-c',
            'import json,time;print(json.dumps(dict(kind="camera",image="fixture",perception={"cube_visible":True})),flush=True);time.sleep(5)'],self.root,'camera')
        self.addCleanup(process.stop)
        deadline=time.monotonic()+3
        while not process.snapshot()['fresh'] and time.monotonic()<deadline:time.sleep(.02)
        self.assertTrue(process.snapshot()['fresh'])
        with process.lock:process.received=time.monotonic()-3
        self.assertNotIn('image',process.snapshot());self.assertFalse(process.snapshot()['fresh'])
        self.assertNotIn('perception',process.snapshot())
        process.stop();self.assertFalse(process.snapshot()['running'])


class LauncherTests(unittest.TestCase):
    def test_physical_start_requires_explicit_robot_identity_before_subprocesses(self):
        from tools import run_neural_lab
        for args in ([],['--serial','test-follower'],['--calibration','test.json']):
            with self.subTest(args=args),patch.dict(os.environ,{},clear=True),patch.object(sys,'argv',['neural.sh',*args]),patch.object(run_neural_lab.subprocess,'check_output') as inventory,redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:run_neural_lab.main()
                self.assertEqual(result.exception.code,2)
                inventory.assert_not_called()

    def test_status_check_does_not_require_or_inspect_robot_identity(self):
        from tools import run_neural_lab
        with patch.dict(os.environ,{},clear=True),patch.object(sys,'argv',['neural.sh','--check']),patch.object(run_neural_lab,'read',return_value={'status':'ok'}) as read,patch.object(run_neural_lab.subprocess,'check_output') as inventory,redirect_stdout(io.StringIO()):
            run_neural_lab.main()
            self.assertEqual(read.call_count,2)
            inventory.assert_not_called()


if __name__=='__main__':unittest.main()
