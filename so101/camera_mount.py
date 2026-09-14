"""Pinned SO-101 hex-nut UVC mount; lengths in metres, local gripper frame.

The STL and mounting transform are mechanical geometry. The 32x32 board,
16 mm lens offset and 90 degree vertical FOV are a simulation lens profile,
not a measured calibration of the user's physical UVC camera.
"""
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np

PROFILE = 'so101-uvc-hexnut-v1-fov90'
MESH = Path(__file__).with_name('assets')/'so101_uvc_hexnut.stl'
MESH_SHA256 = 'e17a626158951ac8cdf8d960962c1a3c8bf23b64635a02f88b62016fe895cef8'
ROTATION = np.array([[0,0,1],[-1,0,0],[0,-1,0]], dtype=float)
TRANSLATION = np.array([-.015,.024,-.031550294])
BOARD = ROTATION @ (np.array([-47.57375,-34.30895,17.5])*.001) + TRANSLATION
BACK = np.array([0,np.sin(np.deg2rad(25)),np.cos(np.deg2rad(25))])
EYE = BOARD - .016*BACK
FOVY = 90.


def install(asset, gripper):
    import hashlib
    if hashlib.sha256(MESH.read_bytes()).hexdigest()!=MESH_SHA256:
        raise ValueError('SO-101 UVC mounting STL checksum mismatch')
    def xyz(a):return ' '.join(map(str,a))
    visual=dict(contype='0',conaffinity='0',mass='0',group='2')
    ET.SubElement(asset,'mesh',name='uvc_hexnut_mount',file=str(MESH),scale='.001 .001 .001')
    ET.SubElement(gripper,'geom',name='wrist_camera_bracket',type='mesh',mesh='uvc_hexnut_mount',
        pos=xyz(TRANSLATION),xyaxes=xyz([*ROTATION[:,0],*ROTATION[:,1]]),rgba='.13 .15 .17 1',**visual)
    # The two M3 axes match the actual wrist's nut recesses. Screws run through
    # the 4 mm plate into the recesses; no invented support rod is present.
    for i,x in enumerate([-.005,.0031]):
        ET.SubElement(gripper,'geom',name=f'wrist_mount_screw_{i}',type='cylinder',
            pos=xyz([x,.0287,-.023400294]),xyaxes='1 0 0 0 0 1',size='.00265 .001',
            rgba='.38 .4 .42 1',**visual)
    mount=ET.SubElement(gripper,'body',name='wrist_camera_mount',pos=xyz(EYE),
        xyaxes=xyz([1,0,0,0,BACK[2],-BACK[1]]))
    ET.SubElement(mount,'camera',name='wrist',mode='fixed',fovy=str(FOVY))
    ET.SubElement(mount,'geom',name='wrist_camera_board',type='box',pos='0 0 .016',size='.016 .016 .0008',
        rgba='.045 .19 .10 1',**visual)
    ET.SubElement(mount,'geom',name='wrist_camera_lens_barrel',type='cylinder',pos='0 0 .008',size='.006 .007',
        rgba='.035 .04 .045 1',**visual)
    ET.SubElement(mount,'geom',name='wrist_camera_lens',type='cylinder',pos='0 0 .0006',size='.0047 .0003',
        rgba='.10 .28 .34 1',**visual)
    for i,(x,y) in enumerate([(-.0135,-.0135),(-.0135,.0135),(.0135,-.0135),(.0135,.0135)]):
        ET.SubElement(mount,'geom',name=f'wrist_board_screw_{i}',type='cylinder',pos=xyz([x,y,.014]),
            size='.0017 .001',rgba='.38 .4 .42 1',**visual)


def configuration():
    return dict(profile=PROFILE,mount='SO-101 32x32 UVC hex-nut adapter',
        mesh_sha256=MESH_SHA256,eye_position_m=EYE.tolist(),fovy_deg=FOVY,
        calibration='CAD-aligned mount; nominal lens profile, physical intrinsics/extrinsics not measured',
        depth_source='synthetic metric depth; physical UVC module supplies RGB only')
