"""Live SO-101 process. Neural activity is the exact motor-producing forward pass."""
import base64
import hashlib
import io
from pathlib import Path
import queue
import time


def simulate(commands,states,initial_path,initial_id):
    import mujoco
    import numpy as np
    from PIL import Image
    from .engine import CONTROL_DT,DT
    from .task import PickPlaceEnv,OBSERVATION_NAMES
    from .policy import Policy,PHASES,TARGET_CENTER,TARGET_SCALE
    from .perception import CameraObservation
    from .recovery import RetrySupervisor
    states.cancel_join_thread()
    env=None;perception=None
    try:
        env=PickPlaceEnv(seed=9000)
        env.step_limit=1200
        env.model.vis.global_.offwidth=1920
        env.model.vis.global_.offheight=1080
        env.renderer=mujoco.Renderer(env.model,height=1080,width=1920)
        cameras={name:mujoco.MjvCamera() for name in ("body","arena")}
        def home(name):
            c=cameras[name];c.lookat[:]=[.07,-.17,.09]
            c.distance,c.azimuth,c.elevation=(.62,200,-28) if name=="body" else (.63,90,-89)
        for name in cameras:home(name)
        policy=Policy(initial_path)
        recovery=RetrySupervisor(3)
        perception=CameraObservation(env)
        sha=hashlib.sha256(Path(initial_path).read_bytes()).hexdigest()
        model_id=initial_id
        seed,episode,seq=9000,1,0
        obs=perception.observation();decision_obs=obs.copy();action,layers=policy.activity(obs)
        applied=None;sample_time=0.;speed=0.;paused=False;camera="body";auto_loop=True
        successes=completed=unsafe_count=0
        pinned_goal=None
        sensor_mode='camera';sensor_error=None
        preview_key=None;eye_frames=None
        decision_frame_id=perception.tracker.frame_id
        trajectory=[];history=[]
        now=time.monotonic();last_poll=last_frame=next_step=now;hold=0.;frame_steps=0
        def send(payload):
            try:states.put_nowait(payload)
            except queue.Full:
                try:states.get_nowait()
                except queue.Empty:pass
                try:states.put_nowait(payload)
                except queue.Full:pass
        while True:
            reset=False
            while True:
                try:cmd=commands.get_nowait()
                except queue.Empty:break
                op=cmd["op"]
                if op=="shutdown":return
                if op=="heartbeat":last_poll=time.monotonic()
                elif op=="pause":
                    paused=cmd["paused"]
                    if not paused and hold:seed+=1;reset=True
                elif op=="reset":
                    seed=cmd.get("seed",seed)
                    goal=cmd.get("goal")
                    pinned_goal=[goal[0]/1000,goal[1]/1000,0] if goal else None
                    reset=True;paused=False
                elif op=="next":
                    seed+=1;reset=True;paused=False
                elif op=='loop':
                    auto_loop=cmd['enabled']
                    if hold and env.outcome in {'success','timeout','retry_exhausted'}:paused=not auto_loop
                elif op=='sensor':
                    if perception:perception.close();perception=None
                    sensor_mode=cmd['sensor']
                    if sensor_mode=='camera':
                        perception=CameraObservation(env)
                    reset=True
                elif op=="model":
                    candidate=Policy(cmd["path"])
                    policy=candidate;model_id=cmd["id"]
                    sha=hashlib.sha256(Path(cmd["path"]).read_bytes()).hexdigest()
                    successes=completed=unsafe_count=0;reset=True
                elif op=="camera":
                    camera=cmd["camera"];c=cameras[camera]
                    if cmd.get("reset_view"):home(camera)
                    else:
                        c.azimuth+=cmd.get("orbit",0)
                        c.distance+=cmd.get("zoom",0)*.04
                        gesture=cmd.get("gesture")
                        if gesture:
                            env.renderer.update_scene(env.data,camera=c)
                            types={"rotate":mujoco.mjtMouse.mjMOUSE_ROTATE_V,"pan":mujoco.mjtMouse.mjMOUSE_MOVE_V,"zoom":mujoco.mjtMouse.mjMOUSE_ZOOM}
                            mujoco.mjv_moveCamera(env.model,types[gesture],cmd["dx"],cmd["dy"],env.renderer.scene,c)
                        c.distance=float(np.clip(c.distance,.15,2.))
                        c.elevation=float(np.clip(c.elevation,-89,65))
            now=time.monotonic()
            if auto_loop and hold and now>=hold and not paused and now-last_poll<=30:
                seed+=1;reset=True
            if reset:
                obs=env.reset(seed,goal=pinned_goal)
                policy.reset();recovery.reset();preview_key=None;eye_frames=None
                if perception:
                    perception.reset();obs=perception.observation()
                sensor_error=None
                decision_obs=obs.copy();action,layers=policy.activity(obs)
                decision_frame_id=perception.tracker.frame_id if perception else None
                applied=None;sample_time=0.;speed=0.;hold=0.;trajectory=[];history=[]
                next_step=now;episode+=1
            idle=now-last_poll>30
            if not paused and not idle and not hold and now>=next_step:
                if perception:
                    try:obs=perception.observation()
                    except RuntimeError as exc:
                        sensor_error=str(exc);env.outcome='sensor_stale';applied=None
                        completed+=1;hold=now+2.;paused=True;continue
                recovery.observe(obs,float(env.data.time),policy,perception)
                if recovery.exhausted:
                    env.outcome='retry_exhausted';applied=None;completed+=1;hold=now+2.;paused=not auto_loop;continue
                decision_obs=obs.copy();sample_time=float(env.data.time)
                decision_frame_id=perception.tracker.frame_id if perception else None
                action,layers=policy.activity(decision_obs,advance=True)
                before=env.ee
                obs,reward,done,info=env.step(action,action_mode=policy.action_mode)
                applied=action.copy()
                speed=float(np.linalg.norm(env.ee-before)*1000/CONTROL_DT)
                trajectory.append((env.ee[:2]*1000).tolist())
                if done:
                    completed+=1;successes+=int(env.success);unsafe_count+=int(env.unsafe)
                    hold=now+2.;paused=not auto_loop or env.unsafe
                frame_steps+=1
                next_step=max(next_step+CONTROL_DT,now)
            else:time.sleep(.005)
            now=time.monotonic()
            if now-last_frame<(1. if idle else .1):continue
            env.camera=cameras[camera]
            rgb=env.render()
            if perception and preview_key!=perception.tracker.frame_id:
                eye_frames=perception.tracker.previews();preview_key=perception.tracker.frame_id
            buffer=io.BytesIO();Image.fromarray(rgb).save(buffer,format="JPEG",quality=94,subsampling=0)
            holding,inside,contacts=env.sensors()
            distance=float(np.linalg.norm(env.cube[:2]-env.goal[:2])*1000)
            signal=[float(env.cube[2]/.15),float(env.data.qpos[env.qadr[5]])]
            history.append([sample_time,*signal,float(action[2])]);history=history[-120:]
            phase="Tamamlandı" if env.success else "Bırakma / geri çekilme" if env.released else "Taşıma / yerleştirme" if env.lifted else "Kavrama / kaldırma" if env.grasped else "Uzanma"
            if policy.has_memory and not env.success:
                names={'approach':'Küpe yaklaşma','lower':'Alçalma','close':'Kavrama','lift':'Kaldırma',
                       'transport':'Taşıma','place':'Kutuda alçalma','release':'Bırakma','retreat':'Geri çekilme'}
                phase=names[PHASES[int(np.argmax(policy.memory))]]
                if recovery.attempt>1 and not holding and not inside:phase='Toparlanma · '+phase
            seq+=1
            send(dict(seq=seq,behavior="so101",wall_time=time.time(),image=base64.b64encode(buffer.getvalue()).decode(),
                eyes_image=eye_frames['detection'] if eye_frames and perception else None,
                eyes=eye_frames if perception else None,
                model=model_id,model_sha256=sha,circuit_identity=policy.circuit.identity,
                paused=paused,idle=idle,camera=camera,episode=episode,seed=seed,
                render=dict(width=1920,height=1080,jpeg_quality=94,msaa=4,mesh="SO-101 + v3 accessories"),
                camera_pose=dict(azimuth=float(env.camera.azimuth),elevation=float(env.camera.elevation),distance=float(env.camera.distance),lookat=env.camera.lookat.tolist()),
                time_s=float(env.data.time),distance_mm=distance,goal_mm=(env.goal[:2]*1000).round(2).tolist(),
                position_mm=(env.ee*1000).tolist(),speed_mm_s=speed,reward=env.total_reward,
                odor=signal,sensory_now=(decision_obs if perception else obs).tolist(),steering=float(action[2]),outcome=env.outcome,
                successes=successes,completed=completed,falls=unsafe_count,rtf=frame_steps*CONTROL_DT/max(now-last_frame,1e-6),
                activity=np.concatenate(layers).round(6).tolist(),layer_means=[float(a.mean()) for a in layers],
                neural=dict(source="so101.policy.Policy.activity",sample_time_s=sample_time,kind="continuous_forward_response",
                    sensor_frame_id=decision_frame_id,
                    sensor_camera=perception.tracker.camera_name if perception else None,
                    sensor_profile=perception.last['camera_profile'] if perception else None,
                    anatomical_passes=2 if policy.motor_phase_feedback else 1,
                    displayed_pass='motor command',
                    applied_steering=float(applied[2]) if applied is not None else None,
                    applied_action=applied.tolist() if applied is not None else None,decision_applied=applied is not None,policy_connected=True),
                robot=dict(phase=phase,observation_names=OBSERVATION_NAMES,decision_observation=decision_obs.tolist(),action=action.tolist(),
                    recovery=recovery.status(),loop_enabled=auto_loop,awaiting_next=bool(hold and auto_loop and not paused),
                    action_mode=policy.action_mode,
                    progress_supervision=policy.progress_supervision,motor_phase_feedback=policy.motor_phase_feedback,
                    target_mm=((TARGET_CENTER+TARGET_SCALE*action[:3])*1000).tolist() if policy.action_mode=='target' else None,
                    learned_memory=policy.last_memory.tolist() if policy.has_memory else None,
                    learned_phase=PHASES[int(np.argmax(policy.memory))] if policy.has_memory else None,
                    joints=env.data.qpos[env.qadr].tolist(),holding=holding,inside_bin=inside,cube_height_mm=float(env.cube[2]*1000),
                    reward_components=env.reward_components,physics_warnings=int(env.data.warning.number.sum()),
                    sensor_mode=sensor_mode,sensor_error=sensor_error,perception=perception.last if perception else None,
                    sensor_source='Bilek RGB-D · eklem ve temas sensörleri' if perception else 'Fizik sensörleri · kamera algısı kapalı'),
                trajectory=trajectory[-350:],history=history,contacts=int(env.data.ncon),physics_dt=DT,control_dt=CONTROL_DT))
            last_frame=now;frame_steps=0
    except Exception as exc:
        import traceback;traceback.print_exc()
        states.put(dict(error=f"{type(exc).__name__}: {exc}",behavior="so101",wall_time=time.time()))
    finally:
        if perception:perception.close()
        if env:env.close()
