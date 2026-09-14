"""Asset-backed checks; opt in explicitly because robot assets are external."""
import os
import unittest
import numpy as np
from types import SimpleNamespace


class TeacherCorrectionTests(unittest.TestCase):
    def test_correction_teacher_respects_an_already_lifted_cube(self):
        from so101.task import Demonstrator
        env=SimpleNamespace(cube=np.array([.02,-.20,.075]),ee=np.array([.02,-.20,.08]),
            goal=np.array([.145,-.155,.0174]),grasped=True,lifted=True,released=False,contact_dwell=.5,
            sensors=lambda:(True,False,{'gripper','moving_jaw_so101_v1'}))
        teacher=Demonstrator();teacher.phase='lower'
        action=teacher(env)
        self.assertEqual(teacher.phase,'lift')
        self.assertGreater(action[2],0);self.assertEqual(action[3],-1)


@unittest.skipUnless(os.environ.get('SO101_TEST_ASSETS')=='1','requires local robot and accessory assets')
class PhysicsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from so101.task import PickPlaceEnv
        cls.env=PickPlaceEnv()

    @classmethod
    def tearDownClass(cls):cls.env.close()

    def test_gravity_and_no_attachment(self):
        e=self.env;e.reset(55,cube=[0,-.24,.08])
        initial=e.cube[2];e.step(np.zeros(4))
        self.assertLess(e.cube[2],initial-.001)
        self.assertEqual(e.model.neq,0);self.assertEqual(e.model.nmocap,0)
        self.assertTrue(np.all(e.data.xfrc_applied==0));self.assertTrue(np.all(e.data.qfrc_applied==0))

    def test_invalid_actions_cannot_advance_physics(self):
        e=self.env;e.reset(56);before=e.data.qpos.copy()
        for a in ([0,0],np.full(4,np.nan),np.full(4,np.inf)):
            with self.assertRaises(ValueError):e.step(a)
        with self.assertRaises(ValueError):e.step_joints(np.full(6,np.nan))
        np.testing.assert_array_equal(before,e.data.qpos)

    def test_contact_and_success_are_not_proximity_flags(self):
        e=self.env;e.reset(57,cube=[.145,-.155,.09],goal=[.145,-.155,0])
        holding,inside,contacts=e.sensors()
        self.assertTrue(inside);self.assertFalse(holding);self.assertFalse(e.success)
        self.assertNotIn('bin',contacts)

    def test_target_adapter_matches_equivalent_bounded_delta(self):
        from so101.policy import TARGET_CENTER,TARGET_SCALE
        from so101.task import MAX_DELTA
        e=self.env;e.reset(59)
        target=e.ee+np.array([.002,-.001,.001])
        delta=np.r_[np.clip((target-e.ee)*.3/MAX_DELTA,-1,1),1.]
        e.step(delta);wanted=e.data.qpos.copy()
        e.reset(59);action=np.r_[(target-TARGET_CENTER)/TARGET_SCALE,1.]
        e.step(action,action_mode='target')
        np.testing.assert_allclose(e.data.qpos,wanted,atol=1e-7)

if __name__=='__main__':unittest.main()
