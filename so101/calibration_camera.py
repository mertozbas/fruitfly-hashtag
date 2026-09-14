"""USB RGB lens and marked-board geometry calibration; no synthetic depth."""
import json
from pathlib import Path
import time
import cv2
import numpy as np
from .calibration_contract import atomic_json,digest

BOARD=dict(squares=[6,8],square_m=.020,marker_m=.014,dictionary='DICT_4X4_50')


def board():
    return cv2.aruco.CharucoBoard((6,8),.020,.014,cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))


def transform(rvec,tvec):
    result=np.eye(4);result[:3,:3]=cv2.Rodrigues(np.asarray(rvec,dtype=float))[0];result[:3,3]=np.asarray(tvec).reshape(3)
    return result


def base_board(pose):
    if len(pose)!=6 or not np.isfinite(pose).all():raise ValueError('Taban pozunda 6 sonlu değer gerekli')
    x,y,z,roll,pitch,yaw=pose
    if max(abs(x),abs(y),abs(z))>2000 or max(abs(roll),abs(pitch),abs(yaw))>180:raise ValueError('Masa pozu sınır dışında')
    a,b,c=np.deg2rad([roll,pitch,yaw]);ca,sa=np.cos(a),np.sin(a);cb,sb=np.cos(b),np.sin(b);cc,sc=np.cos(c),np.sin(c)
    rx=np.array([[1,0,0],[0,ca,-sa],[0,sa,ca]]);ry=np.array([[cb,0,sb],[0,1,0],[-sb,0,cb]]);rz=np.array([[cc,-sc,0],[sc,cc,0],[0,0,1]])
    t=np.eye(4);t[:3,:3]=rz@ry@rx;t[:3,3]=np.array([x,y,z])/1000;return t


def pose_fit(objects,pixels,k,d):
    ok,r,t=cv2.solvePnP(np.asarray(objects,dtype=np.float32),np.asarray(pixels,dtype=np.float32),k,d,flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:raise ValueError('Pano pozu çözülemedi')
    projected=cv2.projectPoints(objects,r,t,k,d)[0].reshape(-1,2)
    error=float(np.sqrt(np.mean(np.sum((projected-np.asarray(pixels).reshape(-1,2))**2,axis=1))))
    camera_points=(cv2.Rodrigues(r)[0]@np.asarray(objects).T).T+t.reshape(3)
    if not np.isfinite(error) or np.min(camera_points[:,2])<=0:raise ValueError('Geçersiz pano geometrisi')
    return r,t,error


def solve_lens(samples,size):
    if len(samples)<18:raise ValueError('En az 18 farklı, net pano görüntüsü gerekli')
    holdout=[s for i,s in enumerate(samples) if i%6==5];train=[s for i,s in enumerate(samples) if i%6!=5]
    centres=np.array([s['pixels'].reshape(-1,2).mean(0)/size for s in samples])
    if np.any(np.ptp(centres,axis=0)<.15):raise ValueError('Panoyu görüntünün farklı yatay ve dikey bölgelerinde göster')
    rms,k,d,rotations,translations=cv2.calibrateCamera([s['objects'] for s in train],[s['pixels'] for s in train],tuple(size),None,None,flags=cv2.CALIB_FIX_K3)
    normals=np.array([cv2.Rodrigues(r)[0][:,2] for r in rotations])
    if np.any(np.std(normals[:,:2],axis=0)<.06):raise ValueError('Pano eğimi yetersiz; iki eksende farklı açılar gerekli')
    validation=[pose_fit(s['objects'],s['pixels'],k,d)[2] for s in holdout]
    if not np.isfinite(k).all() or not np.isfinite(d).all() or not np.isfinite(rms):raise ValueError('Sonlu kamera çözümü bulunamadı')
    if not (.2*size[0]<k[0,0]<5*size[0] and .2*size[1]<k[1,1]<5*size[0] and 0<k[0,2]<size[0] and 0<k[1,2]<size[1]):raise ValueError('Kamera matrisi fiziksel kontrol sınırlarını geçmedi')
    if rms>.8 or max(validation)>1.2 or np.max(abs(d))>2:raise ValueError(f'Hata yüksek: eğitim {rms:.2f} px, ayrı kare {max(validation):.2f} px; yeni kareler topla')
    return dict(schema=1,board=BOARD,size=list(size),camera_matrix=k.tolist(),distortion=d.reshape(-1).tolist(),
                rms_px=float(rms),holdout_rms_px=validation,samples=len(samples),training_samples=len(train),holdout_samples=len(holdout),
                model='OpenCV pinhole + k1,k2,p1,p2; k3 fixed',quality_passed=True)


class CameraCalibration:
    def __init__(self,directory,role,index,profile=None):
        self.directory=Path(directory);self.role=role;self.index=index;self.samples=[];self.size=None
        self.board=board();self.detector=cv2.aruco.CharucoDetector(self.board)
        self.enabled=False;self.corners=None;self.ids=None;self.frame_time=0.;self.frame_id=None
        self.sharpness=0.;self.area=0.;self.warning=None;self.candidate=None;self.saved=None;self.workspace=None
        self.last_command_id=None;self.live_pose=None;self.revision=0;self.label=None
        if profile:
            self.saved=json.loads(Path(profile).read_text());self.label=self.saved['device_label']

    def observe(self,frame,sequence):
        self.size=(frame.shape[1],frame.shape[0]);self.frame_id=sequence;self.frame_time=time.monotonic()
        self.live_pose=None
        if self.saved and list(self.size)!=self.saved['size']:
            self.warning='Çözünürlük profil ile uyuşmuyor; geometri kullanılmıyor';self.corners=self.ids=None;return frame
        if not self.enabled:return frame
        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        self.corners,self.ids,_,_=self.detector.detectBoard(gray)
        self.sharpness=float(cv2.Laplacian(gray,cv2.CV_64F).var());self.area=0
        if self.ids is not None and len(self.ids)>=12:
            points=self.corners.reshape(-1,2);self.area=float(cv2.contourArea(cv2.convexHull(points)))/(self.size[0]*self.size[1])
            output=frame.copy();cv2.aruco.drawDetectedCornersCharuco(output,self.corners,self.ids,(70,220,200))
            if self.saved:
                try:
                    objects=self.board.getChessboardCorners()[self.ids.flatten()]
                    k=np.array(self.saved['camera_matrix']);d=np.array(self.saved['distortion'])
                    r,t,error=pose_fit(objects,self.corners,k,d)
                    if error<=1.2:
                        self.live_pose=dict(camera_from_board=transform(r,t).tolist(),reprojection_px=error,frame_id=sequence)
                        cv2.drawFrameAxes(output,k,d,r,t,.04)
                except (ValueError,cv2.error):pass
            return output
        return frame

    def state(self):
        return dict(enabled=self.enabled,role=self.role,session=self.directory.name,revision=self.revision,device_label=self.label,
            detected_corners=0 if self.ids is None else len(self.ids),sample_count=len(self.samples),required_samples=18,max_samples=30,
            coverage=self.area,sharpness=self.sharpness,warning=self.warning,candidate=self.candidate,saved=self.saved,
            workspace=self.workspace,live_pose=self.live_pose,last_command_id=self.last_command_id)

    def command(self,command):
        self.last_command_id=command['command_id'];self.warning=None;self.revision+=1
        op=command['op']
        if op=='enable':
            if command.get('confirmed') is not True or not command.get('device_label','').strip():raise ValueError('Fiziksel kamera kimliği doğrulanmalı')
            if self.saved and command['device_label']!=self.saved['device_label']:raise ValueError('Ad kayıtlı kamera profiliyle eşleşmiyor; aynı kamerayı doğrula veya yeni lens ölçümü başlat')
            self.enabled=True;self.label=command['device_label'];return
        if op=='reset':
            self.samples=[];self.candidate=None;self.saved=None;self.workspace=None;self.warning='Yeni lens ölçümü başlatıldı; önceki kayıt korunuyor.';return
        if not self.enabled:raise ValueError('Önce kamera kimliğini doğrulayıp pano algılamasını aç')
        if op=='capture':
            if self.candidate:raise ValueError('Yeni kareler için önce ölçümü sıfırla')
            if len(self.samples)>=30:raise ValueError('En fazla 30 kare kaydedilebilir')
            if self.ids is None or len(self.ids)<12 or time.monotonic()-self.frame_time>1:raise ValueError('Güncel karede en az 12 pano köşesi görünmeli')
            if self.sharpness<35 or self.area<.015:raise ValueError('Pano küçük veya bulanık; yaklaştırıp netleştir')
            pixels=self.corners.copy();ids=self.ids.flatten().copy()
            if self.samples and self.samples[0]['size']!=self.size:raise ValueError('Çözünürlük değişti; ölçümü sıfırla')
            for s in self.samples:
                common,a,b=np.intersect1d(ids,s['ids'],return_indices=True)
                if len(common)>=10 and np.mean(np.linalg.norm(pixels.reshape(-1,2)[a]-s['pixels'].reshape(-1,2)[b],axis=1))<.025*np.hypot(*self.size):
                    raise ValueError('Bu açı önceki kareye çok benziyor; panoyu taşı veya eğ')
            self.samples.append(dict(objects=self.board.getChessboardCorners()[ids].copy(),pixels=pixels,ids=ids,size=self.size))
            atomic_json(self.directory/'observations.json',dict(board=BOARD,frames=[{k:v.tolist() if isinstance(v,np.ndarray) else v for k,v in s.items()} for s in self.samples]))
        elif op=='solve':
            self.candidate=solve_lens(self.samples,self.size)
            self.candidate.update(device_label=self.label,role=self.role,index_at_capture=self.index,created=time.time(),session=self.directory.name)
        elif op=='save':
            if not self.candidate or command.get('confirmed') is not True:raise ValueError('Önce geçerli sonucu hesaplayıp onayla')
            if (self.directory/'calibration.json').exists():raise ValueError('Bu oturumun kaydı zaten mevcut; yeni kalibrasyon için yeni kamera oturumu aç')
            atomic_json(self.directory/'calibration.json',self.candidate);self.saved=self.candidate
        elif op=='workspace':
            if not self.saved or not self.live_pose or time.monotonic()-self.frame_time>1:raise ValueError('Kaydedilmiş lens profili ve güncel pano pozu gerekli')
            if command.get('confirmed') is not True:raise ValueError('Pano ölçüsü ve masaya sabitliği doğrulanmalı')
            camera_from_board=np.array(self.live_pose['camera_from_board']);anchor=command.get('base_pose')
            self.workspace=dict(schema=1,board=BOARD,role=self.role,camera_profile_session=self.saved['session'],
                frame_id=self.frame_id,camera_from_board=camera_from_board.tolist(),reprojection_px=self.live_pose['reprojection_px'],
                base_from_board=None if anchor is None else base_board(anchor).tolist(),
                base_from_camera=None if anchor is None else (base_board(anchor)@np.linalg.inv(camera_from_board)).tolist(),
                anchor_source='not_supplied' if anchor is None else 'operator_measured_mm_deg',
                mounting='eye_in_hand' if self.role=='wrist' else 'fixed_camera',
                validity='Board and camera must stay fixed; wrist pose requires current board detection',
                hand_eye_calibrated=False,physical_alignment_verified=False,created=time.time())
            atomic_json(self.directory/'workspace.json',self.workspace)
        else:raise ValueError('Geçersiz kamera kalibrasyon işlemi')
