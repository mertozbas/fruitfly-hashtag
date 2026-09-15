"""Frame-local RGB observations, with no guessed depth or actuator targets.

The v2/v3 accessory tag maps assign tag36h11 200 to the 30 mm red cube,
and 211 to the sorting bin. Tag centres are not grasp/drop coordinates.
"""
import cv2
import numpy as np

ACCESSORY_TAGS={200:('cube_red','KUP'),211:('sort_bin','KUTU')}


class AccessoryVision:
    def __init__(self):
        parameters=cv2.aruco.DetectorParameters()
        parameters.cornerRefinementMethod=cv2.aruco.CORNER_REFINE_SUBPIX
        self.detector=cv2.aruco.ArucoDetector(
            cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11),parameters)

    def observe(self,bgr,sequence):
        if not isinstance(bgr,np.ndarray) or bgr.dtype!=np.uint8 or bgr.ndim!=3 or bgr.shape[2]!=3:
            raise ValueError('Expected an RGB camera frame in uint8 BGR order')
        if type(sequence) is not int or sequence<1:raise ValueError('Expected a positive frame sequence')
        height,width=bgr.shape[:2]
        corners,ids,_=self.detector.detectMarkers(bgr)
        detections=[]
        for marker,points in zip(ids.ravel() if ids is not None else [],corners):
            marker=int(marker)
            if marker not in ACCESSORY_TAGS:continue
            points=np.asarray(points).reshape(4,2)
            if not np.isfinite(points).all() or np.any(points<0) or np.any(points[:,0]>=width) or np.any(points[:,1]>=height):continue
            if abs(cv2.contourArea(points.astype(np.float32)))<36:continue
            detections.append(dict(id=marker,object=ACCESSORY_TAGS[marker][0],
                corners_px=points.round(2).tolist(),center_px=points.mean(0).round(2).tolist()))
        duplicates={d['id'] for d in detections if sum(other['id']==d['id'] for other in detections)>1}
        for d in detections:d['unique']=d['id'] not in duplicates
        # No previous-frame position survives a lost marker or ambiguity.
        return dict(source='physical_rgb_apriltag',family='tag36h11',frame_sequence=sequence,
            detections=detections,duplicate_ids=sorted(duplicates),
            cube_visible=any(d['id']==200 and d['unique'] for d in detections),
            bin_visible=any(d['id']==211 and d['unique'] for d in detections),
            coordinate_frame='image_pixels',metric_pose_valid=False,robot_pose=None,
            policy_input_ready=False,brain_connected=False,
            note='Piksel tespiti; kamera/robot konum dönüşümü ve kavrama geri bildirimi gerekli.')

    @staticmethod
    def annotate(frame,observation):
        for d in observation['detections']:
            points=np.rint(d['corners_px']).astype(np.int32)
            color=(180,220,90) if d['unique'] else (60,160,240)
            cv2.polylines(frame,[points],True,color,2,cv2.LINE_AA)
            x,y=points.min(axis=0)
            cv2.putText(frame,f"{ACCESSORY_TAGS[d['id']][1]} {d['id']}"+(' ?' if not d['unique'] else ''),
                (max(0,int(x)),max(18,int(y)-8)),cv2.FONT_HERSHEY_SIMPLEX,.55,color,2,cv2.LINE_AA)
        return frame
