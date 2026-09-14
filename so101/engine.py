"""SO-101 contact physics. Object poses are assigned only during reset.

The original robot meshes and v3 accessory meshes are loaded from local assets.
The bin uses separate wall collisions: a convex hull would fill its cavity.
No weld, attachment, mocap object, or scripted object transport is used.
"""
from pathlib import Path
import os
import hashlib
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ROBOT_SOURCE = Path(os.environ.get("SO101_MODEL_DIR", Path.home() / ".cache/robot_descriptions/SO-ARM100/Simulation/SO101"))
ACCESSORIES = Path(os.environ.get("SO101_ACCESSORIES_DIR", Path.home() / "so101-aksesuar/v3"))
DT = .001
CONTROL_DT = .05


def finger_collisions(root):
    """Slab-wise convex collision decomposition of the actual finger meshes.

    A single convex hull bridges the finger to the motor housing. These slabs
    retain the opening. This is a collision approximation, not new gripper pads.
    """
    import trimesh
    asset=root.find("asset")
    cache=ROOT/".runtime/so101-collisions"
    cache.mkdir(parents=True,exist_ok=True)
    specs=[("gripper","wrist_roll_follower_so101_v1",2,[-.001,.045,.065,.08,.09,.106]),
           ("moving_jaw_so101_v1","moving_jaw_so101_v1",1,[-.083,-.065,-.045,-.025,.011])]
    for body_name,mesh_name,axis,bounds in specs:
        body=root.find(f".//body[@name='{body_name}']")
        original=next(g for g in body.findall("geom") if g.get("class")=="collision" and g.get("mesh")==mesh_name)
        attrs=original.attrib.copy()
        body.remove(original)
        path=ROBOT_SOURCE/"assets"/(mesh_name+".stl")
        digest=hashlib.sha256(path.read_bytes()+repr((axis,bounds)).encode()).hexdigest()[:12]
        mesh=None
        normal=np.eye(3)[axis]
        for i,(lo,hi) in enumerate(zip(bounds[:-1],bounds[1:])):
            dest=cache/f"{mesh_name}-{digest}-{i}.stl"
            if not dest.exists():
                mesh=trimesh.load(path) if mesh is None else mesh
                part=trimesh.intersections.slice_mesh_plane(mesh,normal,normal*lo)
                part=trimesh.intersections.slice_mesh_plane(part,-normal,normal*hi)
                part.convex_hull.export(dest)
            name=mesh_name+f"_collision_{i}"
            ET.SubElement(asset,"mesh",name=name,file=str(dest))
            ET.SubElement(body,"geom",**{**attrs,"mesh":name,"name":name,"friction":".9 .005 .0001","condim":"3","solref":".012 1"})


def scene_xml():
    required=[ROBOT_SOURCE/'so101_new_calib.xml',*[ACCESSORIES/'stl'/f'{name}.stl' for name in ('cube_red_red','cube_red_black','sort_bin_black','sort_bin_white')]]
    missing=[str(p) for p in required if not p.is_file()]
    if missing:
        raise FileNotFoundError('SO-101 local assets missing: '+', '.join(missing)+'; see docs/so101-local.md')
    root = ET.parse(ROBOT_SOURCE / "so101_new_calib.xml").getroot()
    root.find("compiler").set("meshdir", str(ROBOT_SOURCE / "assets"))
    ET.SubElement(root, "option", timestep=str(DT), integrator="implicitfast", cone="elliptic", solver="PGS", iterations="100")
    visual = ET.SubElement(root, "visual")
    ET.SubElement(visual, "global", offwidth="1600", offheight="1000")
    ET.SubElement(visual, "quality", shadowsize="2048", offsamples="4")
    asset, world = root.find("asset"), root.find("worldbody")
    finger_collisions(root)
    gripper_actuator=root.find("actuator/position[@name='6']")
    gripper_actuator.set("forcerange","-.25 .25")
    # Upstream `gripper` site is on the fixed finger's inner face. For the
    # 30 mm cube the task TCP is 15 mm into the opening, at the pad centre.
    fixed = world.find(".//body[@name='gripper']")
    ET.SubElement(fixed, "site", name="grasp_tcp", pos=".0071 -.000218121 -.09", quat=".5 -.5 .5 -.5", group="3")
    from .camera_mount import install
    install(asset,fixed)
    ET.SubElement(asset, "texture", name="table_tex", type="2d", builtin="checker", width="512", height="512", rgb1=".10 .14 .18", rgb2=".12 .16 .20")
    ET.SubElement(asset, "material", name="table_mat", texture="table_tex", texrepeat="10 10", reflectance=".05")
    ET.SubElement(world, "light", pos="0 -.2 1.1", dir="0 0 -1", diffuse=".8 .8 .8", ambient=".35 .35 .35", castshadow="true")
    ET.SubElement(world, "light", pos=".5 .3 .6", dir="-.5 -.3 -.6", diffuse=".45 .45 .5", castshadow="false")
    ET.SubElement(world, "geom", name="table", type="plane", size=".6 .6 .02", material="table_mat", friction=".8 .005 .0001")
    ET.SubElement(world, "camera", name="front", pos=".42 -.58 .42", xyaxes=".81 .58 0 -.30 .42 .855", fovy="45")
    ET.SubElement(world, "camera", name="top", pos=".06 -.17 .8", xyaxes="1 0 0 0 1 0", fovy="45")
    for name in ("cube_red_red", "cube_red_black", "sort_bin_black", "sort_bin_white"):
        ET.SubElement(asset, "mesh", name=name, file=str(ACCESSORIES / "stl" / (name + ".stl")), scale=".001 .001 .001")
    cube = ET.SubElement(world, "body", name="cube", pos=".02 -.20 .015")
    ET.SubElement(cube, "freejoint", name="cube_free")
    ET.SubElement(cube, "geom", name="cube_collision", type="box", size=".015 .015 .015", mass=".012", group="3", friction=".9 .005 .0001", condim="3", solref=".012 1")
    for name, color in (("cube_red_red", ".82 .10 .12 1"), ("cube_red_black", ".025 .025 .025 1")):
        ET.SubElement(cube, "geom", type="mesh", mesh=name, pos="0 0 -.015", rgba=color, contype="0", conaffinity="0", mass="0", group="2")
    box = ET.SubElement(world, "body", name="bin", pos=".15 -.15 0")
    for name,color in (("sort_bin_black", ".06 .065 .075 1"), ("sort_bin_white", ".92 .93 .91 1")):
        ET.SubElement(box, "geom", type="mesh", mesh=name, rgba=color, contype="0", conaffinity="0", group="2")
    parts = [("floor", (0,0,.0012), (.038,.038,.0012)),
             ("left",(-.0368,0,.0142),(.0012,.038,.0118)),
             ("right",(.0368,0,.0142),(.0012,.038,.0118)),
             ("back",(0,.0368,.0142),(.0356,.0012,.0118)),
             ("front",(0,-.0368,.0142),(.0356,.0012,.0118)),
             ("tag",(0,.049,.0012),(.012,.012,.0012))]
    for name,pos,size in parts:
        ET.SubElement(box, "geom", name="bin_"+name, type="box", pos=" ".join(map(str,pos)), size=" ".join(map(str,size)), group="3", friction=".8 .005 .0001")
    return ET.tostring(root, encoding="unicode")


class ArmEnv:
    def __init__(self, seed=0, render=False, xml=None):
        self.model = mujoco.MjModel.from_xml_string(scene_xml() if xml is None else xml)
        self.data = mujoco.MjData(self.model)
        self.ik_data = mujoco.MjData(self.model)
        self.gravity_data = mujoco.MjData(self.model)
        self.site = self.model.site("grasp_tcp").id
        self.cube_id, self.bin_id = self.model.body("cube").id, self.model.body("bin").id
        self.cube_qpos = int(self.model.jnt_qposadr[self.model.joint("cube_free").id])
        self.joints = np.array([self.model.joint(str(i)).id for i in range(1,7)])
        self.qadr = self.model.jnt_qposadr[self.joints]
        self.dadr = self.model.jnt_dofadr[self.joints]
        if not (np.array_equal(self.qadr,np.arange(6)) and np.array_equal(self.dadr,np.arange(6))):
            raise ValueError('SO-101 asset joint order changed; expected arm 1..5 and gripper 6 before cube_free')
        self.limits = self.model.jnt_range[self.joints].copy()
        self.renderer = mujoco.Renderer(self.model, height=800, width=1280) if render else None
        self.camera = mujoco.MjvCamera()
        self.camera.lookat[:] = [.065,-.16,.11]
        self.camera.distance = .65
        self.camera.azimuth, self.camera.elevation = 125, -28
        self.reset(seed)

    @property
    def ee(self):
        return self.data.site_xpos[self.site].copy()

    @property
    def cube(self):
        return self.data.xpos[self.cube_id].copy()

    @property
    def goal(self):
        return self.model.body_pos[self.bin_id].copy() + [0,0,.0174]

    def ik(self, target, q=None, iterations=40, tool_rotation=None):
        """Position + downward tool-axis IK; only the five arm DOFs participate."""
        d = self.ik_data
        d.qpos[:] = self.data.qpos
        d.qpos[self.qadr] = self.data.qpos[self.qadr] if q is None else q
        jp, jr = np.zeros((3,self.model.nv)), np.zeros((3,self.model.nv))
        for _ in range(iterations):
            mujoco.mj_forward(self.model,d)
            rotation = d.site_xmat[self.site].reshape(3,3)
            desired=np.array([[0,0,1],[-1,0,0],[0,-1,0]]) if tool_rotation is None else np.asarray(tool_rotation)
            rotation_error=.5*sum(np.cross(rotation[:,i],desired[:,i]) for i in range(3))
            error = np.r_[np.asarray(target)-d.site_xpos[self.site], .06*rotation_error]
            if np.linalg.norm(error) < 2e-5:
                break
            mujoco.mj_jacSite(self.model,d,jp,jr,self.site)
            j = np.vstack((jp[:,:5], .06*jr[:,:5]))
            dq = j.T @ np.linalg.solve(j@j.T + 1e-5*np.eye(6),error)
            d.qpos[self.qadr[:5]] = np.clip(d.qpos[self.qadr[:5]] + np.clip(dq,-.15,.15),self.limits[:5,0]+.01,self.limits[:5,1]-.01)
        return d.qpos[self.qadr].copy()

    def reset(self, seed=0, cube=None, goal=None):
        rng=np.random.default_rng(seed)
        mujoco.mj_resetData(self.model,self.data)
        self.data.qpos[self.qadr] = [0,-.3,1.2,1.2,-1.57,.9]
        c=np.array([.015,-.205,.015]) if cube is None else np.asarray(cube,float)
        self.data.qpos[self.cube_qpos:self.cube_qpos+7] = [*c,1,0,0,0]
        self.model.body_pos[self.bin_id] = [.145,-.155,0] if goal is None else goal
        mujoco.mj_forward(self.model,self.data)
        self.qtarget=self.ik([.025,-.22,.10],iterations=150)
        self.qtarget[5]=.9
        self.data.qpos[self.qadr]=self.qtarget
        mujoco.mj_forward(self.model,self.data)
        self.steps=0
        self.seed=seed
        return self.ee

    def step_joints(self, targets):
        if np.shape(targets)!=(6,) or not np.isfinite(targets).all():
            raise ValueError('Expected six finite joint targets in radians')
        target=np.clip(np.asarray(targets),self.limits[:,0],self.limits[:,1])
        self.qtarget=np.clip(target,self.qtarget-.04,self.qtarget+.04)
        self.gravity_data.qpos[:]=self.data.qpos
        self.gravity_data.qvel[:]=0
        mujoco.mj_forward(self.model,self.gravity_data)
        compensation=np.clip(self.gravity_data.qfrc_bias[self.dadr]/self.model.actuator_gainprm[:,0],-.15,.15)
        compensation[5]=0
        for _ in range(round(CONTROL_DT/DT)):
            # Realizable gravity feed-forward via position-servo offset. No
            # body gravcomp or object forces; actuator force limits stay active.
            self.data.ctrl[:]=np.clip(self.qtarget+compensation,self.limits[:,0],self.limits[:,1])
            mujoco.mj_step(self.model,self.data)
            if self.data.warning.number.sum():
                break
        self.steps+=1

    def move(self, target, gripper, steps=30):
        start=self.ee
        for i in range(steps):
            t=(i+1)/steps
            q=self.ik(start+(np.asarray(target)-start)*(3*t*t-2*t*t*t),iterations=12)
            q[5]=gripper
            self.step_joints(q)

    def contacts(self):
        pairs=[]
        for c in self.data.contact:
            bodies=[int(self.model.geom_bodyid[g]) for g in (c.geom1,c.geom2)]
            if self.cube_id in bodies:
                other=bodies[1] if bodies[0]==self.cube_id else bodies[0]
                pairs.append(mujoco.mj_id2name(self.model,mujoco.mjtObj.mjOBJ_BODY,other))
        return pairs

    def render(self):
        if self.renderer is None:
            self.renderer=mujoco.Renderer(self.model,height=800,width=1280)
        option=mujoco.MjvOption()
        option.geomgroup[3]=0
        self.renderer.update_scene(self.data,camera=self.camera,scene_option=option)
        return self.renderer.render()

    def close(self):
        if self.renderer is not None:
            self.renderer.close()
