"""Prepare a fresh local dataset and verify actual walking/rendering, without private checkpoints."""
import json
from pathlib import Path


def main():
    from brain import build_graph
    from prepare import prepare_geometry
    from odor_brain import build_circuit, train, MODEL, load_policy
    from lab_graph import prepare
    from fly_sim import OdorNavigationEnv
    from lab_render import detailed_model, sync_render
    import mujoco
    import numpy as np

    build_graph()
    prepare_geometry()
    build_circuit()
    if not all((MODEL / name).is_file() for name in ("trained.npz", "untrained.npz", "training.json")):
        train(steps=3000, seed=42)
    else:
        print("Mevcut başlangıç modeli korunuyor; yeniden eğitilmedi.", flush=True)
    prepare()
    policy = load_policy()
    env = OdorNavigationEnv()
    try:
        observation, _ = env.reset(seed=10)
        for _ in range(5):
            observation, _, done, truncated, _ = env.step(policy(observation))
            if done or truncated:
                raise RuntimeError("Yürüyüş başlangıç kontrolü erken sonlandı")
        model, data, assets = detailed_model(env)
        model.vis.global_.offwidth = 1920
        model.vis.global_.offheight = 1080
        sync_render(env, model, data)
        with mujoco.Renderer(model, height=1080, width=1920) as renderer:
            renderer.update_scene(data)
            frame = renderer.render()
        if frame.shape != (1080, 1920, 3) or not np.isfinite(env.sim.mj_data.qpos).all():
            raise RuntimeError("HD render/fizik kontrolü başarısız")
        report = dict(check="fresh-install-walking-smoke", steps=5, image_shape=list(frame.shape),
                      render_faces=assets["render_faces"], scope="Startup and HD rendering only, not six-goal evaluation")
        (Path(__file__).parent / ".runtime/setup-walking.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
    finally:
        env.close()


if __name__ == "__main__":
    main()
