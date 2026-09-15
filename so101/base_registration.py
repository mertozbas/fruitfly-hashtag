"""Camera-to-model-base measurement candidates from labelled fixed landmarks.

This module does not open hardware or authorize motion. Image residuals do not
verify printed-part dimensions, marker placement, joint zeros, or the table plane.
"""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from .calibration_camera import lens_geometry, transform
from .calibration_contract import atomic_json

LABELS = ('A', 'B', 'D', 'C')  # Around the flange, counterclockwise in model XY.


def estimate_base_pose(landmarks, pixels, profile):
    """Return a metric candidate and expose competing planar-pose solutions."""
    if set(landmarks) != set(LABELS) or set(pixels) != set(LABELS):
        raise ValueError('A, B, C ve D noktalarının tamamı gerekli')
    objects = np.array([landmarks[label] for label in LABELS], dtype=float)
    image = np.array([pixels[label] for label in LABELS], dtype=float)
    if objects.shape != (4, 3) or image.shape != (4, 2):
        raise ValueError('Model noktaları XYZ, görüntü noktaları UV olmalı')
    if not np.isfinite(objects).all() or not np.isfinite(image).all():
        raise ValueError('Sonlu nokta koordinatları gerekli')
    span = np.ptp(objects, axis=0)
    if np.any(span[:2] < .02) or np.any(span[:2] > .3) or span[2] > 1e-5:
        raise ValueError('Model noktaları metre cinsinden aynı montaj düzleminde olmalı')
    size = np.array(profile['size'])
    if size.shape != (2,) or not np.isfinite(size).all() or np.any(size <= 0):
        raise ValueError('Geçerli görüntü boyutu gerekli')
    if np.any(image < 0) or np.any(image >= size):
        raise ValueError('Noktalar profilin görüntü sınırları içinde olmalı')
    if profile.get('quality_passed') is not True or profile.get('role') != 'top':
        raise ValueError('Doğrulanmış üst kamera lens profili gerekli')
    for points, sign in ((objects[:, :2], 1), (image, -1)):
        contour = points.astype(np.float32)
        if not cv2.isContourConvex(contour) or sign * cv2.contourArea(contour, oriented=True) <= 0:
            raise ValueError('Nokta sırası ters veya kesişiyor; A/B/C/D eşleşmesini kontrol et')
    if abs(cv2.contourArea(image.astype(np.float32))) < 150 or np.any(np.ptp(image, axis=0) < 15):
        raise ValueError('Taban noktaları görüntüde çok küçük veya birbirine çok yakın')
    k = np.array(profile['camera_matrix'], dtype=float)
    distortion = np.array(profile['distortion'], dtype=float)
    lens_geometry(k, distortion, tuple(size))
    solved, rotations, translations, _ = cv2.solvePnPGeneric(
        objects, image, k, distortion, flags=cv2.SOLVEPNP_IPPE)
    if not solved:
        raise ValueError('Taban pozu çözülemedi')
    candidates = []
    for rotation, translation in zip(rotations, translations):
        camera_from_base = transform(rotation, translation)
        base_from_camera = np.linalg.inv(camera_from_base)
        camera_points = objects @ camera_from_base[:3, :3].T + translation.reshape(3)
        if np.any(camera_points[:, 2] <= .05):
            continue
        if base_from_camera[2, 3] <= objects[0, 2] + .05:
            continue
        if not .12 <= np.linalg.norm(base_from_camera[:3, 3] - objects.mean(0)) <= 2:
            continue
        projected = cv2.projectPoints(objects, rotation, translation, k, distortion)[0].reshape(-1, 2)
        residuals = np.linalg.norm(projected - image, axis=1)
        candidates.append(dict(camera_from_base=camera_from_base.tolist(),
                               base_from_camera=base_from_camera.tolist(),
                               rms_px=float(np.sqrt(np.mean(residuals ** 2))),
                               max_residual_px=float(residuals.max()),
                               projected_pixels={label: point.tolist() for label, point in zip(LABELS, projected)}))
    if not candidates:
        raise ValueError('Kamera montaj düzleminin üstünde geçerli bir poz vermedi')
    candidates.sort(key=lambda item: item['rms_px'])
    best = candidates[0]
    if best['rms_px'] > 1 or best['max_residual_px'] > 1.5:
        raise ValueError('Taban eşleme hatası yüksek; nokta merkezlerini kontrol et')
    gap = candidates[1]['rms_px'] - best['rms_px'] if len(candidates) > 1 else None
    ambiguous = gap is not None and gap < .25
    return dict(schema=1, kind='fixed_base_landmark_candidate', coordinate_frame='mujoco_model_base',
                units='metres', **best, alternate_candidates=candidates[1:],
                ambiguity_gap_px=gap, ambiguous=ambiguous, image_geometry_passed=not ambiguous,
                observed_pixels=pixels, model_landmarks_m=landmarks,
                physical_alignment_verified=False, hand_eye_calibrated=False,
                table_plane_verified=False, execution_allowed=False,
                note='CAD identity, marker centring and an independent physical check remain necessary. '
                     'This model-base frame is not the table or shoulder-pan origin.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observations', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Önceki ölçümün üzerine yazılmaz; yeni bir çıktı yolu kullan')
    raw = args.observations.read_bytes()
    observation = json.loads(raw)
    manifest_path = Path(observation['landmarks_path'])
    manifest = json.loads(manifest_path.read_bytes())
    model = Path(manifest['model_path'])
    mesh = model.parent / 'assets/base_so101_v2.stl'
    if (hashlib.sha256(model.read_bytes()).hexdigest() != manifest['model_sha256'] or
            hashlib.sha256(mesh.read_bytes()).hexdigest() != manifest['mesh_sha256']):
        raise ValueError('Ölçüm noktalarının kaynak 3B modeli değişmiş')
    profile_path = Path(observation['profile_path'])
    profile_raw = profile_path.read_bytes()
    result = estimate_base_pose(manifest['points_m'], observation['pixels'], json.loads(profile_raw))
    result.update(observations_sha256=hashlib.sha256(raw).hexdigest(),
                  landmarks_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                  profile_sha256=hashlib.sha256(profile_raw).hexdigest(),
                  source_frame=observation.get('source_frame'))
    atomic_json(args.output, result)
    print(json.dumps({key: result[key] for key in ('rms_px', 'ambiguous', 'image_geometry_passed', 'execution_allowed')}))


if __name__ == '__main__':
    main()
