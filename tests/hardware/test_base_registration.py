"""Known physical-frame projections; never connects to a camera or motor."""
import copy
import unittest

import cv2
import numpy as np

from so101.base_registration import estimate_base_pose


POINTS = dict(A=[-.007, -.040, .0476], B=[.049, -.040, .0476],
              C=[-.011, .030, .0476], D=[.053, .030, .0476])
PROFILE = dict(role='top', quality_passed=True, size=[1280, 720],
               camera_matrix=[[700., 0, 640], [0, 705., 360], [0, 0, 1]],
               distortion=[0., 0., 0., 0., 0.])


def fixture(camera=(.03, -.45, .40)):
    camera = np.array(camera)
    target = np.array([.02, -.005, .0476])
    forward = target - camera
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, [0., 0., 1.])
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    rotation = np.array([right, down, forward])
    translation = -rotation @ camera
    pixels = cv2.projectPoints(np.array(list(POINTS.values())), cv2.Rodrigues(rotation)[0],
                               translation, np.array(PROFILE['camera_matrix']), np.zeros(5))[0].reshape(-1, 2)
    return dict(zip(POINTS, pixels.tolist())), rotation, translation, camera


class BaseRegistrationTests(unittest.TestCase):
    def test_metric_inverse_recovers_known_camera_position(self):
        pixels, rotation, translation, camera = fixture()
        result = estimate_base_pose(POINTS, pixels, PROFILE)
        np.testing.assert_allclose(np.array(result['base_from_camera'])[:3, 3], camera, atol=1e-7)
        np.testing.assert_allclose(np.array(result['camera_from_base'])[:3, :3], rotation, atol=1e-7)
        self.assertLess(result['rms_px'], 1e-7)
        self.assertTrue(result['image_geometry_passed'])
        self.assertFalse(result['execution_allowed'])
        self.assertFalse(result['physical_alignment_verified'])
        self.assertFalse(result['table_plane_verified'])

    def test_small_detection_noise_preserves_pose_without_claiming_physical_accuracy(self):
        pixels, _, _, camera = fixture()
        rng = np.random.default_rng(13)
        pixels = {label: (np.array(point) + rng.normal(0, .03, 2)).tolist() for label, point in pixels.items()}
        result = estimate_base_pose(POINTS, pixels, PROFILE)
        self.assertLess(np.linalg.norm(np.array(result['base_from_camera'])[:3, 3] - camera), .005)
        self.assertFalse(result['execution_allowed'])

    def test_nearly_frontal_planar_ambiguity_is_not_hidden_by_low_residual(self):
        pixels, *_ = fixture((.02, -.02, .8))
        result = estimate_base_pose(POINTS, pixels, PROFILE)
        self.assertLess(result['rms_px'], 1e-6)
        self.assertTrue(result['ambiguous'])
        self.assertFalse(result['image_geometry_passed'])
        self.assertFalse(result['execution_allowed'])

    def test_reversed_and_crossed_labels_are_rejected(self):
        pixels, *_ = fixture()
        for mapping in [('B', 'A', 'D', 'C'), ('B', 'A', 'C', 'D')]:
            wrong = dict(zip(('A', 'B', 'C', 'D'), [pixels[label] for label in mapping]))
            with self.assertRaisesRegex(ValueError, 'sırası'):
                estimate_base_pose(POINTS, wrong, PROFILE)

    def test_millimetres_are_not_silently_used_as_metres(self):
        pixels, *_ = fixture()
        with self.assertRaisesRegex(ValueError, 'metre'):
            estimate_base_pose({key: (np.array(value) * 1000).tolist() for key, value in POINTS.items()}, pixels, PROFILE)

    def test_missing_nonfinite_and_out_of_frame_observations_fail(self):
        pixels, *_ = fixture()
        for change in ('missing', 'nan', 'outside'):
            bad = copy.deepcopy(pixels)
            if change == 'missing': del bad['A']
            elif change == 'nan': bad['A'][0] = float('nan')
            else: bad['A'][0] = 1280
            with self.assertRaises(ValueError):
                estimate_base_pose(POINTS, bad, PROFILE)

    def test_unverified_or_wrong_role_lens_cannot_be_used(self):
        pixels, *_ = fixture()
        for update in (dict(quality_passed=False), dict(role='wrist')):
            with self.assertRaisesRegex(ValueError, 'lens profili'):
                estimate_base_pose(POINTS, pixels, {**PROFILE, **update})

    def test_small_and_collinear_image_points_are_rejected(self):
        pixels, *_ = fixture()
        for bad in ({label: [640 + i, 360 + i] for i, label in enumerate(pixels)},
                    {label: (np.array(point) * .01 + [600, 300]).tolist() for label, point in pixels.items()}):
            with self.assertRaises(ValueError):
                estimate_base_pose(POINTS, bad, PROFILE)


if __name__ == '__main__':
    unittest.main()
