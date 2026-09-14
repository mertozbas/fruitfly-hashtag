"""Shared task contracts; all scientific scope is explicit and task-specific."""
TASKS = {
    "so101": dict(title="SO-101 · Al ve yerleştir", goal=[145.,-155.],
        sensor="Robot konumu ve fiziksel temas → 30 özellik → MaleCNS alt devresi",
        motor="ΔXYZ ve kavrayıcı → sınırlandırılmış ters kinematik",
        success="Küp kutu içinde serbest ve durgun; kol en az 65 mm uzakta · 0,5 s"),
    "odor": dict(title="Kokuya yönelme", goal=[12., 4.],
        sensor="Sol / sağ antenin sentetik koku yoğunluğu", motor="CPG yön komutu",
        success="Hedefe uzaklık < 1,5 mm"),
    "avoidance": dict(title="Kokudan kaçınma", goal=[6., 2.],
        sensor="Sol / sağ antenin sentetik koku yoğunluğu", motor="CPG yön komutu",
        success="3 mm tehlike alanına girmeden kaynaktan başlangıca göre 8 mm uzaklaşma"),
    "vision": dict(title="Görsel yönelme", goal=[12., 4.],
        sensor="İki gözün RGB görüntüsündeki kırmızı hedef belirginliği", motor="CPG yön komutu",
        success="Görüntüden yönelerek hedefe uzaklık < 1,5 mm"),
    "terrain": dict(title="Engel aşma", goal=[12., 0.],
        sensor="MuJoCo bacak temas kuvvetleri · iki taraflı, 100 ms sönümlü",
        motor="Sabit CPG üzerindeki takılma / geri çekme düzeltmesinin kazancı",
        success="Engele fiziksel temas edip gövdeyi arka kenarın 3 mm ötesine taşıma · |Y| < 5 mm"),
    "flight": dict(title="Beyin ile uçuş", goal=[22., 6.],
        sensor="Sol / sağ sanal antenin koku yoğunluğu", motor="FlyBody yön hedefi",
        success="Geçerli uçuşta hedefe XY uzaklık < 2 mm"),
}


def compatible(task, model_task):
    return task == model_task or {task, model_task} <= {"odor", "flight"}


def cases(task):
    if task == "avoidance":
        goals = [(6,2),(6,-2),(5,2),(5,-2),(7,2),(7,-2)]
    elif task == "terrain":
        return [dict(seed=10+i, goal=(12,0), options=dict(barrier_height=h, barrier_x=5.0))
                for i,h in enumerate([.25,.25,.35,.35,.45,.45])]
    else:
        goals = [(12,4),(12,-4),(10,5),(10,-5),(14,3),(14,-3)]
    return [dict(seed=10+i, goal=g) for i,g in enumerate(goals)]


def evaluate(directory, task, event=lambda **x: None, controls=True):
    """Paired held-out physics cases, including causal readout ablation.

    Silencing sets the learned motor command to zero, retaining the body, fixed
    CPG, task and seed. This establishes dependence on the learned output, not
    biological validity or an advantage over a hand-written controller.
    """
    import hashlib
    import json
    from pathlib import Path
    from odor_policy import Policy
    from fly_sim import rollout, json_default
    directory = Path(directory)
    variants = ["trained", "untrained", "silenced"] if controls else ["trained"]
    reports, progress = {}, 0
    total = len(variants) * 6
    for variant in variants:
        policy = Policy(directory / ("untrained.npz" if variant == "untrained" else "trained.npz"))
        if not compatible(task, policy.task):
            raise ValueError("Evaluation task does not match checkpoint modality")
        if variant == "silenced":
            policy.decoder[:] = 0
            policy.bias[:] = 0
        results = []
        for case in cases(task):
            result = rollout(policy, task=task, seconds=2.5, **case)
            result["seed"] = case["seed"]
            result["options"] = case.get("options", {})
            results.append(result)
            progress += 1
            event(status="evaluating", evaluated=progress, evaluation_total=total, variant=variant,
                  success_count=sum(r["success"] for r in results))
        reports[variant] = dict(episodes=6, success_count=sum(r["success"] for r in results),
            falls=sum(r["fallen"] for r in results), unsafe_count=sum(r["unsafe"] for r in results),
            mean_final_distance_mm=sum(r["final_distance_mm"] for r in results)/6, results=results)
    report = dict(**reports["trained"], task=task, criterion=TASKS[task]["success"],
        checkpoint_sha256=hashlib.sha256((directory / "trained.npz").read_bytes()).hexdigest(),
        baseline_sha256=hashlib.sha256((directory / "untrained.npz").read_bytes()).hexdigest(),
        controls={k:v for k,v in reports.items() if k != "trained"},
        motor_adapter=dict(steering_authority=1.1 if task == "avoidance" else .55,
                           terrain_max_correction=80, control_dt_s=.01),
        scope="Six deterministic held-out physics conditions; supervised synthetic training. Readout ablation, not biological validation or generalization proof.")
    path = directory / "evaluation.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, default=json_default, indent=2) + "\n")
    temporary.replace(path)
    return report


if __name__ == "__main__":
    import argparse
    from lab_train import event
    parser = argparse.ArgumentParser(description="Paired physics evaluation of a saved walking-task model")
    parser.add_argument('--model', required=True, help='Run directory containing both checkpoints and circuit')
    parser.add_argument('--task', required=True, choices=['odor','avoidance','vision','terrain'])
    args = parser.parse_args()
    evaluate(args.model, args.task, event)
