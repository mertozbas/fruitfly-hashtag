"""SO-101 and Mert's full-size printed game in MuJoCo.

Virtual-board moves are explicitly scene edits. Robot mode never assigns the
controlled token's pose after reset; only the virtual opponent places O pieces.
"""
import os
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import mujoco
from so101.engine import ArmEnv,scene_xml

ASSETS=Path(os.environ.get('SO101_TICTACTOE_ASSETS',Path(__file__).with_name('assets')))
BOARD_CENTER=np.array([0.,-.18,0.])
CELLS=np.array([BOARD_CENTER+[x,y,0] for y in (.084,0,-.084) for x in (-.084,0,.084)])
SUPPLY=np.array([[-.155,y,.004] for y in (-.085,-.147,-.209)]+[[.155,y,.004] for y in (-.085,-.147)])
BLOCK_SUPPLY=np.array([[-.155,y,.015] for y in (-.085,-.147,-.209)]+[[-.21,y,.015] for y in (-.085,-.147)])


def xml(token_style='printed'):
    if token_style not in {'printed','blocks'}:raise ValueError('Unknown token geometry')
    root=ET.fromstring(scene_xml());world=root.find('worldbody');asset=root.find('asset')
    size=root.find('size')
    if size is None:size=ET.SubElement(root,'size')
    size.set('memory','64M')
    for name in ('cube','bin'):world.remove(world.find(f"body[@name='{name}']"))
    for name in ('board','x-token','o-token'):
        path=ASSETS/(name+'.stl')
        if not path.is_file():raise FileNotFoundError(f'{path}: tic-tac-toe print assets required')
        # MuJoCo requires binary STL; preserve the source geometry and checksum.
        cache=Path(__file__).resolve().parents[1]/'.runtime/tictactoe-meshes'
        cache.mkdir(parents=True,exist_ok=True)
        binary=cache/(name+'-'+hashlib.sha256(path.read_bytes()).hexdigest()[:12]+'.stl')
        if not binary.exists():
            import trimesh
            trimesh.load(path).export(binary,file_type='stl')
        ET.SubElement(asset,'mesh',name='ttt_'+name,file=str(binary),scale='.001 .001 .001')
        if name!='board':ET.SubElement(asset,'mesh',name='mark_'+name,file=str(binary),scale='.00044 .00044 .00012')
    board=ET.SubElement(world,'body',name='game_board',pos=' '.join(map(str,BOARD_CENTER)))
    ET.SubElement(board,'geom',name='board_visual',type='mesh',mesh='ttt_board',rgba='.04 .055 .065 1',contype='0',conaffinity='0',group='2')
    for axis in (0,1):
        for offset in (-.042,.042):
            pos=np.array([0.,0.,.0025]);pos[axis]=offset
            size=[.12,.12,.0025];size[axis]=.007
            ET.SubElement(board,'geom',type='box',pos=' '.join(map(str,pos)),size=' '.join(map(str,size)),group='3')
    ET.SubElement(world,'body',name='bin',pos=' '.join(map(str,CELLS[4])))
    for symbol in ('X','O'):
        for i in range(5 if symbol=='X' else 4):
            name='cube' if symbol=='X' and i==0 else f'{symbol}{i}'
            supply=BLOCK_SUPPLY if token_style=='blocks' else SUPPLY
            initial=np.array(supply[i] if symbol=='X' else [.3,-.12-i*.062,.004]);initial[2]=.015 if token_style=='blocks' else .004
            body=ET.SubElement(world,'body',name=name,pos=' '.join(map(str,initial)))
            ET.SubElement(body,'freejoint',name='cube_free' if name=='cube' else name+'_free')
            color='.84 .08 .10 1' if symbol=='X' else '.10 .55 .78 1'
            if token_style=='blocks':
                if symbol=='X':color=['.84 .06 .08 1','.95 .35 .03 1','.8 .8 .04 1','.55 .05 .85 1','.1 .65 .15 1'][i]
                ET.SubElement(body,'geom',type='box',size='.015 .015 .015',mass='.012',rgba=color,friction='.9 .005 .0001',solref='.012 1',condim='3')
                ET.SubElement(body,'geom',type='mesh',mesh='mark_x-token' if symbol=='X' else 'mark_o-token',pos='0 0 .0145',rgba='.92 .92 .9 1',contype='0',conaffinity='0',mass='0',group='2')
                continue
            ET.SubElement(body,'geom',type='mesh',mesh='ttt_x-token' if symbol=='X' else 'ttt_o-token',pos='0 0 -.004',
                          rgba=color,contype='0',conaffinity='0',mass='0',group='2')
            if symbol=='X':
                for angle in (-45,45):
                    ET.SubElement(body,'geom',type='box',size=f'{(.052*np.sqrt(2)-.010)/2} .005 .004',euler=f'0 0 {np.deg2rad(angle)}',
                        mass='.004',friction='1 .005 .0001',condim='3',solref='.012 1',group='3')
            else:
                for j in range(12):
                    angle=2*np.pi*j/12;next_angle=angle+2*np.pi/12
                    a=[.0225*np.cos(angle),.0225*np.sin(angle),0]
                    b=[.0225*np.cos(next_angle),.0225*np.sin(next_angle),0]
                    ET.SubElement(body,'geom',type='capsule',fromto=' '.join(map(str,a+b)),
                        size='.0035',mass=str(.008/12),friction='1 .005 .0001',group='3')
    top=world.find("camera[@name='top']");top.set('pos','0 -.18 .72');top.set('fovy','48')
    return ET.tostring(root,encoding='unicode')


class GameEnv(ArmEnv):
    def __init__(self,seed=0,token_style='printed'):
        self.tool_yaw=0.
        self.tool_pitch=0.
        self.token_style=token_style;self.token_half=.015 if token_style=='blocks' else .004
        self.supply=BLOCK_SUPPLY if token_style=='blocks' else SUPPLY
        super().__init__(seed=seed,xml=xml(token_style))
        self.token_ids={s:[self.model.body('cube' if s=='X' and i==0 else f'{s}{i}').id for i in range(5 if s=='X' else 4)] for s in ('X','O')}
        self.reset(seed)

    def ik(self,target,q=None,iterations=40):
        a=self.tool_yaw;c,s=np.cos(a),np.sin(a)
        p=self.tool_pitch;cp,sp=np.cos(p),np.sin(p)
        rotation=np.array([[c,-s,0],[s,c,0],[0,0,1]])@np.array([[cp,0,sp],[0,1,0],[-sp,0,cp]])@np.array([[0,0,1],[-1,0,0],[0,-1,0]])
        return super().ik(target,q,iterations,tool_rotation=rotation)

    def reset(self,seed=0,cube=None,goal=None):
        # ArmEnv invokes reset before token_ids has been constructed.
        super().reset(seed,cube=[*self.supply[0][:2],self.token_half],goal=CELLS[4])
        if not hasattr(self,'token_ids'):return
        self.board=(0,)*9;self.used={'X':0,'O':0};self.placements=0;self.placement_attempts=0
        self.active_token=None;self.target_cell=None
        for symbol,ids in self.token_ids.items():
            for i,body_id in enumerate(ids):
                pos=[*self.supply[i][:2],self.token_half] if symbol=='X' else [ .30,-.13-i*.062,self.token_half]
                self._set_token(body_id,pos)
        mujoco.mj_forward(self.model,self.data)
        self.qtarget=self.ik([.17,0,.13],iterations=200);self.qtarget[5]=.9
        self.observation_joints=self.qtarget.copy()
        self.data.qpos[self.qadr]=self.qtarget;mujoco.mj_forward(self.model,self.data)

    def _set_token(self,body_id,pos):
        jid=self.model.body_jntadr[body_id];qa=self.model.jnt_qposadr[jid];da=self.model.jnt_dofadr[jid]
        self.data.qpos[qa:qa+7]=[*pos,1,0,0,0];self.data.qvel[da:da+6]=0

    def virtual_move(self,cell,player):
        from .rules import play
        next_board=play(self.board,cell,player);symbol='X' if player==1 else 'O'
        body_id=self.token_ids[symbol][self.used[symbol]]
        self._set_token(body_id,CELLS[cell]+[0,0,self.token_half]);self.used[symbol]+=1
        self.board=next_board;mujoco.mj_forward(self.model,self.data)

    def begin_placement(self,cell):
        from .rules import play
        play(self.board,cell,1) # Check legality without changing logical state.
        self.active_token=self.token_ids['X'][self.used['X']];self.cube_id=self.active_token
        self.target_cell=cell;self.model.body_pos[self.bin_id]=CELLS[cell]
        self.placement_attempts+=1

    def complete_placement(self,observed_board):
        from .rules import play
        expected=play(self.board,self.target_cell,1)
        if tuple(observed_board)!=expected:raise ValueError('Camera did not confirm the expected move')
        self.board=expected;self.used['X']+=1;self.placements+=1;self.active_token=None

    @property
    def goal(self):return self.model.body_pos[self.bin_id].copy()+[0,0,self.token_half]
