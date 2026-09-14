"""Live camera-observed board strategy. Minimax is absent from this process."""
import hashlib
from pathlib import Path
import queue
import time


def simulate(commands,states,initial_path,initial_id):
    import numpy as np
    import mujoco
    from .policy import Policy
    from .rules import winner,turn,play
    from .scene import GameEnv
    from .vision import Eyes,jpeg
    from .motor import Motor,Controller,PHASES
    from collections import deque
    states.cancel_join_thread();env=eyes=None
    try:
        policy=Policy(initial_path);motor=Motor(policy,initial_path) if policy.has_motor else None
        execution='robot' if motor else 'virtual_board'
        def create_environment():
            nonlocal env,eyes
            if eyes:eyes.close()
            if env:env.close()
            env=GameEnv(token_style='blocks' if execution=='robot' else 'printed');eyes=Eyes(env)
            env.model.vis.global_.offwidth=1920;env.model.vis.global_.offheight=1080
            env.renderer=mujoco.Renderer(env.model,height=1080,width=1920)
        create_environment()
        model_id=initial_id;sha=hashlib.sha256(Path(initial_path).read_bytes()).hexdigest()
        cameras={key:mujoco.MjvCamera() for key in ('body','arena')}
        def home(key):
            c=cameras[key];c.lookat[:]=[0,-.17,.025]
            c.distance,c.azimuth,c.elevation=(.82,135,-42) if key=='body' else (.73,90,-89)
        for key in cameras:home(key)
        seed=51;rng=np.random.default_rng(seed);seq=0;episode=1;camera='body';paused=False;auto_loop=True
        opponent='human';agent=1;error=None;hold=0.;wins=draws=losses=0;next_move=time.monotonic()+1
        last_poll=time.monotonic();last_frame=0.;clock=0.;last_tick=last_poll
        last_decision=None;layers=None;decision_board=None;decision_time=0.;decision_frame=0;move_log=[]
        observed=None;decision_images={};controller=None;motor_record=None;pass_kind='strategy';next_step=0.;applied=False
        history=deque(maxlen=120);speed=0.
        def send(payload):
            try:states.put_nowait(payload)
            except queue.Full:
                try:states.get_nowait()
                except queue.Empty:pass
                try:states.put_nowait(payload)
                except queue.Full:pass
        def terminal():return winner(env.board) or 0 not in env.board
        def record_move(cell,player,source,check):
            nonlocal hold,wins,draws,losses,next_move,error,observed,paused
            if not check['valid'] or tuple(check['board'])!=env.board:
                observed=check;error='Yerleştirme görüntüden doğrulanamadı; oyun duraklatıldı';paused=True;return
            observed=check
            move_log.append(dict(cell=cell,player=player,source=source,frame_id=check['frame_id']))
            next_move=time.monotonic()+1.3;error=None
            if terminal():
                w=winner(env.board);wins+=int(w==agent);draws+=int(w==0);losses+=int(w==-agent);hold=time.monotonic()+3
        def move(cell,player,source):
            env.virtual_move(cell,player);eyes.capture();record_move(cell,player,source,eyes.board())
        while True:
            now=time.monotonic();reset=False;rebuild=False
            if not paused and now-last_poll<=30:clock+=now-last_tick
            last_tick=now
            while True:
                try:cmd=commands.get_nowait()
                except queue.Empty:break
                op=cmd['op']
                if op=='shutdown':return
                if op=='heartbeat':last_poll=now
                elif op=='pause':paused=cmd['paused']
                elif op in ('reset','next'):seed=cmd.get('seed',seed+1);reset=True
                elif op=='loop':auto_loop=cmd['enabled']
                elif op=='game':
                    wanted=cmd.get('execution','virtual_board')
                    if wanted=='robot' and (motor is None or cmd['agent']!=1):
                        error='Robot modu motor okuması bulunan model ve X tarafı gerektirir';continue
                    rebuild=wanted!=execution;execution=wanted
                    opponent=cmd['opponent'];agent=cmd['agent'];reset=True;paused=False
                elif op=='game_move':
                    try:
                        if paused or terminal() or opponent!='human' or turn(env.board)==agent:raise ValueError('Şu anda senin sıran değil')
                        if cmd['episode']!=episode or tuple(cmd['board'])!=env.board:raise ValueError('Tahta değişti; güncel kareyi seç')
                        move(cmd['cell'],-agent,'human_virtual_placement')
                    except ValueError as exc:error=str(exc)
                elif op=='model':
                    policy=Policy(cmd['path']);model_id=cmd['id'];sha=hashlib.sha256(Path(cmd['path']).read_bytes()).hexdigest();reset=True
                    motor=Motor(policy,cmd['path']) if policy.has_motor else None
                    if execution=='robot' and motor is None:execution='virtual_board';rebuild=True
                elif op=='camera':
                    camera=cmd['camera'];c=cameras[camera]
                    if cmd.get('reset_view'):home(camera)
                    else:
                        c.azimuth+=cmd.get('orbit',0);c.distance+=cmd.get('zoom',0)*.04
                        if cmd.get('gesture'):
                            env.renderer.update_scene(env.data,camera=c)
                            types={'rotate':mujoco.mjtMouse.mjMOUSE_ROTATE_V,'pan':mujoco.mjtMouse.mjMOUSE_MOVE_V,'zoom':mujoco.mjtMouse.mjMOUSE_ZOOM}
                            mujoco.mjv_moveCamera(env.model,types[cmd['gesture']],cmd['dx'],cmd['dy'],env.renderer.scene,c)
                        c.distance=float(np.clip(c.distance,.3,2));c.elevation=float(np.clip(c.elevation,-89,65))
            if hold and now>=hold and auto_loop and not paused and opponent!='human':reset=True;seed+=1
            if reset:
                if rebuild:create_environment()
                env.reset(seed);rng=np.random.default_rng(seed);episode+=1;hold=0.;error=None;move_log=[]
                last_decision=layers=decision_board=None;next_move=now+1;clock=0.;decision_images={}
                controller=motor_record=None;pass_kind='strategy';next_step=now;applied=False
                history.clear();speed=0.
            idle=now-last_poll>30
            if controller is not None and not paused and not idle and now>=next_step:
                previous_ee=env.ee.copy();controller.step();next_step=time.monotonic()+.05
                speed=float(np.linalg.norm(env.ee-previous_ee)*1000/.05)
                if controller.layers is not None:
                    layers=controller.layers;pass_kind='motor';decision_time=controller.action_sample_time;decision_frame=controller.action_frame_id
                    decision_images=dict(top=controller.action_images['top'],wrist=controller.action_images['wrist'],detection=controller.action_images['wrist'])
                    motor_record=dict(phase=PHASES[controller.applied_phase],phase_index=controller.applied_phase,attempt=controller.attempt,
                        action=controller.last_action.tolist(),coordinates=controller.coordinates.tolist(),inputs=controller.inputs.tolist(),
                        elapsed_s=controller.elapsed,sample_time_s=controller.action_sample_time,sensor_cameras=controller.measurement['cameras'],
                        prediction=controller.measurement.get('prediction'),observation_age_s=controller.measurement.get('age_s'),
                        holding=bool({'gripper','moving_jaw_so101_v1'}<=set(env.contacts())),
                        estimated_token=controller.position.tolist(),outcome=controller.outcome,success=controller.success,error=controller.error,
                        target_cell=env.target_cell,placements=env.placements)
                    applied=controller.action_applied
                if controller.done:
                    if controller.success:
                        record_move(env.target_cell,1,'connectome_motor_contact_physics',controller.verification['observed'])
                        decision_board=None
                    else:error=controller.error;paused=True
                    controller=None
            if now-last_frame<(.8 if idle else .15):time.sleep(.01);continue
            if controller is None:
                eyes.capture();observed=eyes.board()
            if controller is not None:pass
            elif error and paused:pass
            elif not observed['valid'] or tuple(observed['board'])!=env.board:
                error='Tahta görüntüsü belirsiz; karar bekletiliyor'
            elif not terminal():
                error=None
                board=tuple(observed['board'])
                if decision_board!=board:
                    _,layers,last_decision=policy.activity(board);decision_board=board
                    decision_time=clock;decision_frame=eyes.frame_id;decision_images=eyes.images.copy()
                    pass_kind='strategy'
                if not paused and not idle and now>=next_move:
                    player=turn(board)
                    if player==agent or opponent=='self':
                        if execution=='robot' and player==1:
                            controller=Controller(env,eyes,motor,last_decision['chosen_cell']);next_step=now
                        else:move(last_decision['chosen_cell'],player,'connectome_strategy');applied=True
                    elif opponent=='random':move(int(rng.choice(last_decision['legal_cells'])),player,'random_virtual_opponent')
            if layers is None:
                _,layers,last_decision=policy.activity((0,)*9);decision_frame=eyes.frame_id;decision_time=clock;decision_images=eyes.images.copy()
            if not paused and not idle:history.append([clock,float(layers[0].mean()),float(layers[-1].mean())])
            env.camera=cameras[camera];image=jpeg(env.render());seq+=1
            w=winner(env.board);outcome=('draw' if not w else 'won' if w==agent else 'lost') if terminal() else 'running'
            waiting=controller is None and not terminal() and opponent=='human' and turn(env.board)!=agent
            send(dict(seq=seq,behavior='tictactoe',wall_time=time.time(),model=model_id,model_sha256=sha,circuit_identity=policy.circuit.identity,
                image=image,eyes=dict(rgb=decision_images['wrist'] if pass_kind=='motor' else eyes.images['wrist'],detection=decision_images['detection'],depth=decision_images['top']),
                eyes_image=decision_images['detection'],paused=paused,idle=idle,camera=camera,episode=episode,seed=seed,
                render=dict(width=1920,height=1080,jpeg_quality=91,msaa=4,mesh='SO-101 + 240 mm board / '+('30 mm training cubes' if execution=='robot' else '52 mm printed tokens')),
                time_s=float(env.data.time) if execution=='robot' else clock,distance_mm=0.,speed_mm_s=speed if controller is not None and not paused else 0.,reward=float(w*agent),goal_mm=[0,0],position_mm=(env.ee*1000).tolist(),
                camera_pose=dict(azimuth=float(env.camera.azimuth),elevation=float(env.camera.elevation),distance=float(env.camera.distance),lookat=env.camera.lookat.tolist()),
                odor=[sum(v==1 for v in env.board)/5,sum(v==-1 for v in env.board)/4],steering=float(last_decision['chosen_cell']),
                outcome=outcome,successes=wins+draws,completed=wins+draws+losses,falls=0,rtf=float(env.data.time/max(clock,.001)) if execution=='robot' else 0.,contacts=env.data.ncon,physics_dt=.001,control_dt=.05 if execution=='robot' else .15,
                activity=np.concatenate(layers).round(6).tolist(),layer_means=[float(a.mean()) for a in layers],history=list(history),trajectory=[],
                neural=dict(source='tictactoe.motor.Motor.activity' if pass_kind=='motor' else 'tictactoe.policy.Policy.activity',kind='continuous_forward_response',sample_time_s=decision_time,
                    sensor_frame_id=decision_frame,sensor_camera='wrist + top' if pass_kind=='motor' else 'top',displayed_pass=pass_kind,
                    applied_action=(motor_record['action'] if pass_kind=='motor' else last_decision['chosen_cell']) if applied else None,
                    decision_applied=applied,policy_connected=True),
                game=dict(board=list(env.board),observed=observed,decision=last_decision,waiting_for_human=waiting,opponent=opponent,agent=agent,
                    wins=wins,draws=draws,losses=losses,loop_enabled=auto_loop,error=error,move_log=move_log,
                    execution=execution,robot_ready=motor is not None,motor=motor_record,motor_running=controller is not None,
                    robot_note='30 mm eğitim küpleri · SO-101 X taşlarını fizik ile taşır; O sanal rakiptir.' if execution=='robot' else 'Sanal taş yerleştirme · Robot hareketi uygulanmaz.',
                    live_eye_frame_id=eyes.frame_id,decision_age_s=0. if pass_kind=='motor' else max(0.,clock-decision_time))))
            last_frame=now;applied=False
    except Exception as exc:
        import traceback;traceback.print_exc()
        states.put(dict(error=f'{type(exc).__name__}: {exc}',behavior='tictactoe',wall_time=time.time()))
    finally:
        if eyes:eyes.close()
        if env:env.close()
