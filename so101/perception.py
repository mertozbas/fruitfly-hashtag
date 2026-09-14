"""Calibrated synthetic RGB-D cube tracking, without object-state reads.

The known destination is a workspace target. RGB colour and metric depth are
camera measurements; no segmentation IDs, body poses or contact truth enter
the tracker. A stale estimate must stop execution, not silently use truth.
"""
import mujoco
import numpy as np


class RGBDCubeTracker:
    def __init__(self,model,width=640,height=480):
        self.model=model
        self.width,self.height=width,height
        self.renderer=mujoco.Renderer(model,height=height,width=width)
        self.camera_name='front'
        self.camera_id=model.camera(self.camera_name).id
        self.position=None
        self.last_seen=None
        self.visible=False
        self.pixels=0

    def reset(self):
        self.position=None;self.last_seen=None;self.visible=False

    def update(self,data):
        option=mujoco.MjvOption();option.geomgroup[3]=0
        self.renderer.disable_depth_rendering()
        self.renderer.update_scene(data,camera=self.camera_name,scene_option=option)
        rgb=self.renderer.render().astype(float)
        self.renderer.enable_depth_rendering()
        depth=self.renderer.render().copy()
        self.renderer.disable_depth_rendering()
        mask=(rgb[:,:,0]>75)&(rgb[:,:,0]>1.65*rgb[:,:,1])&(rgb[:,:,0]>1.5*rgb[:,:,2])&np.isfinite(depth)&(depth<1.)
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
                    pixels=self.pixels,age_s=age,valid=self.position is not None and age<=.5)

    def close(self):
        self.renderer.close()


class CameraObservation:
    """RGB-D pose + joint encoders + simulated tactile sensors + known goal.

    The evaluator may use true state to score the task, but this observation
    builder never reads the cube's body position or orientation.
    """
    def __init__(self,env):
        self.env=env;self.tracker=RGBDCubeTracker(env.model)
        self.lifted=False;self.held_offset=None;self.last=None

    def reset(self):
        self.tracker.reset();self.lifted=False;self.held_offset=None;self.last=None

    def observation(self):
        e=self.env;measurement=self.tracker.update(e.data)
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
        self.last=dict(source='synthetic RGB-D + joint encoders + tactile contacts + calibrated destination',
            visible=measurement['visible'],pixels=measurement['pixels'],age_s=measurement['age_s'],
            estimated_cube=cube.tolist(),kinematic_prediction=holding)
        return obs

    def close(self):self.tracker.close()
