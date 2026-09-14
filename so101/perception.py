"""Calibrated synthetic RGB-D cube tracking, without object-state reads.

The known destination is a workspace target. RGB colour and metric depth are
camera measurements; no segmentation IDs, body poses or contact truth enter
the tracker. A stale estimate must stop execution, not silently use truth.
"""
import mujoco
import numpy as np


class RGBDCubeTracker:
    def __init__(self,model,width=640,height=480,camera='wrist'):
        self.model=model
        self.width,self.height=width,height
        self.renderer=mujoco.Renderer(model,height=height,width=width)
        if camera not in {'wrist','front'}:raise ValueError('Expected wrist or front camera')
        self.camera_name=camera
        self.camera_id=model.camera(self.camera_name).id
        self.depth_range=(.02,.45) if camera=='wrist' else (.2,1.)
        self.position=None
        self.last_seen=None
        self.visible=False
        self.pixels=0
        self.rgb=None;self.depth=None;self.mask=None;self.frame_id=0;self.sample_time_s=0.

    def reset(self):
        self.position=None;self.last_seen=None;self.visible=False
        self.rgb=None;self.depth=None;self.mask=None;self.frame_id=0;self.pixels=0

    def update(self,data):
        option=mujoco.MjvOption();option.geomgroup[3]=0
        self.renderer.disable_depth_rendering()
        self.renderer.update_scene(data,camera=self.camera_name,scene_option=option)
        self.rgb=self.renderer.render().copy()
        rgb=self.rgb.astype(float)
        self.renderer.enable_depth_rendering()
        depth=self.renderer.render().copy()
        self.renderer.disable_depth_rendering()
        mask=(rgb[:,:,0]>75)&(rgb[:,:,0]>1.65*rgb[:,:,1])&(rgb[:,:,0]>1.5*rgb[:,:,2])&np.isfinite(depth)&(depth<1.)
        self.depth=depth;self.mask=mask;self.frame_id+=1;self.sample_time_s=float(data.time)
        v,u=np.nonzero(mask);self.pixels=len(u);self.visible=len(u)>=8
        if self.visible:
            z=depth[v,u]
            f=self.height/(2*np.tan(np.deg2rad(self.model.cam_fovy[self.camera_id])/2))
            # MuJoCo camera local axes: +X right, +Y up, -Z forward.
            local=np.stack([(u+.5-self.width/2)*z/f,-(v+.5-self.height/2)*z/f,-z],axis=1)
            rotation=data.cam_xmat[self.camera_id].reshape(3,3)
            points=local@rotation.T+data.cam_xpos[self.camera_id]
            # Robust top surface estimate for the upright 30 mm cube. Partial
            # finger occlusion can bias XY; quality is measured independently.
            top=np.percentile(points[:,2],90)
            upper=points[points[:,2]>top-.0008]
            centre=np.r_[(np.percentile(upper[:,:2],2,axis=0)+np.percentile(upper[:,:2],98,axis=0))/2,top-.015]
            self.position=centre;self.last_seen=float(data.time)
        age=float('inf') if self.last_seen is None else float(data.time)-self.last_seen
        return dict(position=None if self.position is None else self.position.copy(),visible=self.visible,
                    pixels=self.pixels,age_s=age if np.isfinite(age) else None,
                    valid=self.position is not None and age<=.5,
                    frame_id=self.frame_id,sample_time_s=self.sample_time_s,camera_name=self.camera_name,
                    camera_position_m=data.cam_xpos[self.camera_id].tolist(),
                    camera_rotation=data.cam_xmat[self.camera_id].reshape(3,3).tolist(),
                    camera_mount='gripper' if self.camera_name=='wrist' else 'world',
                    bbox=[int(u.min()),int(v.min()),int(u.max()),int(v.max())] if self.visible else None)

    def previews(self):
        """Encode the already consumed measurement, never render a newer frame."""
        import base64
        import io
        from PIL import Image,ImageDraw
        if self.rgb is None:return None
        rgb=Image.fromarray(self.rgb)
        detected=rgb.copy();draw=ImageDraw.Draw(detected)
        v,u=np.nonzero(self.mask)
        if self.visible:
            box=(int(u.min()),int(v.min()),int(u.max()),int(v.max()))
            draw.rectangle(box,outline=(98,216,208),width=2)
            draw.text((box[0],max(0,box[1]-14)),"RED CUBE",fill=(98,216,208))
        # Fixed metric scale, not per-frame min/max that hides distance changes.
        lower,upper=self.depth_range
        near=np.clip((upper-self.depth)/(upper-lower),0,1)
        colors=np.stack([30+65*near,40+175*near,65+150*near],axis=-1).astype(np.uint8)
        colors[~np.isfinite(self.depth)]=0
        result={}
        for key,im in [('rgb',rgb),('detection',detected),('depth',Image.fromarray(colors))]:
            buffer=io.BytesIO();im.save(buffer,format='JPEG',quality=88)
            result[key]=base64.b64encode(buffer.getvalue()).decode()
        return result

    def close(self):
        self.renderer.close()


class CameraObservation:
    """RGB-D pose + joint encoders + simulated tactile sensors + known goal.

    The evaluator may use true state to score the task, but this observation
    builder never reads the cube's body position or orientation.
    """
    def __init__(self,env,camera='wrist'):
        self.env=env;self.tracker=RGBDCubeTracker(env.model,camera=camera)
        self.lifted=False;self.held_offset=None;self.last=None

    def reset(self):
        self.tracker.reset();self.lifted=False;self.held_offset=None;self.last=None

    def observation(self):
        e=self.env;measurement=self.tracker.update(e.data)
        self.last=dict(source='synthetic RGB-D + joint encoders + tactile contacts + calibrated destination',
            **{k:v for k,v in measurement.items() if k!='position'},
            estimated_cube=None,kinematic_prediction=False,
            goal_source='calibrated workspace destination',width=self.tracker.width,height=self.tracker.height,
            depth_range_m=list(self.tracker.depth_range))
        contacts=set(e.contacts())
        holding={'gripper','moving_jaw_so101_v1'}<=contacts
        cube=measurement['position']
        if not measurement['valid']:
            raise RuntimeError('RGB-D cube measurement stale; stop this episode')
        if holding:
            if self.held_offset is None:
                self.held_offset=cube-e.ee
            # Contact-conditioned kinematic prediction reduces occlusion bias.
            # This estimates pose only; it applies no forces or attachment.
            prediction=e.ee+self.held_offset
            cube=.85*prediction+.15*cube
        else:
            self.held_offset=None
        self.lifted|=bool(holding and cube[2]>.07)
        goal=e.goal # a configured, calibrated workspace destination
        inside=bool(np.all(np.abs(cube[:2]-goal[:2])+.015<.0356))
        obs=np.asarray([
            *(e.data.qpos[e.qadr]/[2,2,2,2,3,1]),*np.clip(e.data.qvel[e.dadr],-2,2),
            *((e.ee-[.06,-.18,.06])/.15),*((cube-e.ee)/.15),*((goal-cube)/.15),cube[2]/.15,
            float(holding),float(self.lifted),float(inside),min(e.contact_dwell/.5,1),*e.last_action,
        ],dtype=np.float32)
        self.last.update(estimated_cube=cube.tolist(),kinematic_prediction=holding)
        return obs

    def close(self):self.tracker.close()
