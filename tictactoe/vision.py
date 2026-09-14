"""Calibrated RGB board reading and synthetic RGB-D token localization.

Only camera pixels, camera calibration and configured board coordinates enter
perception. Object body IDs/poses and segmentation buffers are not observations.
"""
import base64
import io
import numpy as np
import mujoco
from PIL import Image,ImageDraw
from .scene import CELLS
from .rules import validate


def jpeg(rgb):
    buffer=io.BytesIO();Image.fromarray(np.asarray(rgb,np.uint8)).save(buffer,format='JPEG',quality=91)
    return base64.b64encode(buffer.getvalue()).decode()


class Eyes:
    def __init__(self,env,width=640,height=480):
        self.env=env;self.width=width;self.height=height
        self.renderer=mujoco.Renderer(env.model,height=height,width=width)
        self.frame_id=0;self.frames={};self.images={};self.last_position=None;self.last_seen=None
        self.trackers={};self.track_prior=None
        if env.token_style=='blocks':
            from so101.perception import RGBDCubeTracker
            for camera in ('top','wrist'):
                self.trackers[camera]=RGBDCubeTracker(env.model,width,height,camera,mask_function=lambda rgb,camera=camera:self.tracked_mask(rgb,camera))

    def project(self,points,camera):
        e=self.env;cid=e.model.camera(camera).id
        rotation=e.data.cam_xmat[cid].reshape(3,3)
        local=(np.asarray(points)-e.data.cam_xpos[cid])@rotation
        f=self.height/(2*np.tan(np.deg2rad(e.model.cam_fovy[cid])/2))
        return np.stack([self.width/2+f*local[:,0]/-local[:,2],self.height/2-f*local[:,1]/-local[:,2]],axis=1)

    def capture(self):
        self.frame_id+=1;option=mujoco.MjvOption();option.geomgroup[3]=0
        for camera in ('top','wrist'):
            self.renderer.disable_depth_rendering();self.renderer.update_scene(self.env.data,camera=camera,scene_option=option)
            rgb=self.renderer.render().copy()
            self.renderer.enable_depth_rendering();depth=self.renderer.render().copy();self.renderer.disable_depth_rendering()
            self.frames[camera]=(rgb,depth);self.images[camera]=jpeg(rgb)
        return self.frame_id

    @staticmethod
    def masks(rgb):
        rgb=rgb.astype(float);r,g,b=np.moveaxis(rgb,-1,0)
        return (r>75)&(r>1.6*g)&(r>1.5*b),(b>150)&(g>130)&(g>1.4*r)&(b>1.5*r)

    @staticmethod
    def block_masks(rgb):
        h,s,v=np.moveaxis(np.asarray(Image.fromarray(rgb).convert('HSV')),-1,0)
        vivid=(s>65)&(v>120)
        return [vivid&((h<10)|(h>245)),vivid&(h>=10)&(h<32),vivid&(h>=32)&(h<60),
                vivid&(h>170)&(h<230),vivid&(h>=60)&(h<115)]

    def board(self):
        rgb,depth=self.frames['top'];red,blue=self.masks(rgb)
        if self.env.token_style=='blocks':red=np.logical_or.reduce(self.block_masks(rgb))
        pixels=self.project(CELLS+[0,0,.004],'top');values=[];counts=[]
        draw_image=Image.fromarray(rgb);draw=ImageDraw.Draw(draw_image)
        f=self.height/(2*np.tan(np.deg2rad(self.env.model.cam_fovy[self.env.model.camera('top').id])/2))
        radius=int(f*.033/.716)
        unknown=False
        for i,(u,v) in enumerate(pixels):
            x,y=int(u),int(v);sl=np.s_[max(0,y-radius):min(self.height,y+radius),max(0,x-radius):min(self.width,x+radius)]
            r,b=int(red[sl].sum()),int(blue[sl].sum());counts.append([r,b])
            if r>20 and b>20:unknown=True
            # Above-table occlusion cannot be silently interpreted as an empty cell.
            near=depth[sl]<.68
            if int(near.sum())>radius*radius*.4:unknown=True
            value=1 if r>20 and r>b*2 else -1 if b>20 and b>r*2 else 0
            values.append(value);draw.rectangle((x-radius,y-radius,x+radius,y+radius),outline=(80,178,174),width=1)
            draw.text((x-radius+2,y-radius+2),str(i+1),fill=(230,235,240))
        try:validate(values)
        except ValueError:unknown=True
        self.images['detection']=jpeg(np.array(draw_image))
        return dict(board=values,valid=not unknown,counts=counts,frame_id=self.frame_id,camera='top',source='calibrated RGB cell colour masks',
                    sample_time_s=float(self.env.data.time))

    def token(self,prior,holding=False):
        """Fuse wrist and top pixels near the configured/last observed token.

        Prior is last camera estimate or contact-conditioned encoder prediction.
        It never comes from a MuJoCo object's true pose.
        """
        if self.trackers:return self.block_token(prior,holding)
        estimates=[];cameras=[]
        for camera in ('wrist','top'):
            rgb,depth=self.frames[camera];red,_=self.masks(rgb)
            if self.env.token_style=='blocks':red=self.block_masks(rgb)[self.env.used['X']]
            v,u=np.nonzero(red & np.isfinite(depth) & (depth>.015) & (depth<1.))
            if len(u)<8:continue
            cid=self.env.model.camera(camera).id;z=depth[v,u]
            f=self.height/(2*np.tan(np.deg2rad(self.env.model.cam_fovy[cid])/2))
            local=np.stack([(u+.5-self.width/2)*z/f,-(v+.5-self.height/2)*z/f,-z],axis=1)
            points=local@self.env.data.cam_xmat[cid].reshape(3,3).T+self.env.data.cam_xpos[cid]
            nearby=(np.linalg.norm(points[:,:2]-np.asarray(prior)[:2],axis=1)<.05)&(points[:,2]>.003)
            points=points[nearby]
            if len(points)<8:continue
            top=np.percentile(points[:,2],90);upper=points[points[:,2]>top-.001]
            center=np.r_[(np.percentile(upper[:,:2],2,axis=0)+np.percentile(upper[:,:2],98,axis=0))/2,top-self.env.token_half]
            estimates.append(center);cameras.append(camera)
        if estimates:
            # Overhead sees the full flat token; wrist confirms close-up contact.
            measured=estimates[-1]
            if holding:measured=.85*np.asarray(prior)+.15*measured
            self.last_position=measured;self.last_seen=float(self.env.data.time)
        age=None if self.last_seen is None else float(self.env.data.time)-self.last_seen
        valid=age is not None and age<=.4
        return dict(position=None if self.last_position is None else self.last_position.copy(),valid=valid,
                    cameras=cameras,frame_id=self.frame_id,age_s=age,sample_time_s=float(self.env.data.time))

    def block_token(self,prior,holding):
        self.track_prior=np.asarray(prior)
        readings={name:t.update(self.env.data,prior=prior,frames=self.frames[name]) for name,t in self.trackers.items()}
        top=readings['top'];wrist=readings['wrist'];position=None;cameras=[]
        if top['visible']:
            mask=self.trackers['top'].mask;v,u=np.nonzero(mask)
            # Require a whole 30 mm top footprint before using a new centroid.
            f=self.height/(2*np.tan(np.deg2rad(self.env.model.cam_fovy[self.env.model.camera('top').id])/2))
            extent=np.array([np.ptp(u),np.ptp(v)])*float(np.median(self.frames['top'][1][mask]))/f
            if np.all(extent>.025):position=top['position'];cameras.append('top')
        if position is None and wrist['visible']:
            position=wrist['position'];cameras.append('wrist')
        if position is None and top['visible']:
            position=np.asarray(prior).copy();cameras.append('top_partial_prior')
        if position is not None:
            if holding:position=.9*np.asarray(prior)+.1*position
            self.last_position=position;self.last_seen=float(self.env.data.time)
        age=None if self.last_seen is None else float(self.env.data.time)-self.last_seen
        return dict(position=self.last_position,valid=age is not None and age<=.4,cameras=cameras,
                    frame_id=self.frame_id,age_s=age,sample_time_s=float(self.env.data.time))

    def tracked_mask(self,rgb,camera):
        # Lighting can move orange pixels into the yellow hue interval. Associate
        # pixels with the configured/last camera location, never a body pose.
        mask=self.block_masks(rgb)[min(4,self.env.used['X'])]
        if self.track_prior is None:return mask
        depth=self.frames[camera][1];v,u=np.nonzero(mask & np.isfinite(depth))
        cid=self.env.model.camera(camera).id;z=depth[v,u]
        f=self.height/(2*np.tan(np.deg2rad(self.env.model.cam_fovy[cid])/2))
        local=np.stack([(u+.5-self.width/2)*z/f,-(v+.5-self.height/2)*z/f,-z],axis=1)
        points=local@self.env.data.cam_xmat[cid].reshape(3,3).T+self.env.data.cam_xpos[cid]
        nearby=np.linalg.norm(points[:,:2]-self.track_prior[:2],axis=1)<.055
        associated=np.zeros_like(mask);associated[v[nearby],u[nearby]]=True
        return associated

    def close(self):
        for t in self.trackers.values():t.close()
        self.renderer.close()
