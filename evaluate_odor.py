"""Compare saved policies under identical, held-out MuJoCo conditions."""

import json
from pathlib import Path
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from fly_sim import OUTPUT, json_default, rollout, teacher
from odor_brain import MODEL, load_policy


def evaluate():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    policies = {"untrained": load_policy("untrained"), "trained": load_policy("trained")}
    cases = [(12, 4), (12, -4), (10, 5), (10, -5), (14, 3), (14, -3)]
    results = []
    started = time.monotonic()
    for i, goal in enumerate(cases):
        for name, policy in policies.items():
            video = OUTPUT / f"{name}.mp4" if i == 0 else None
            result = rollout(policy, seed=10 + i, goal=goal, seconds=2.5, video=video)
            result.update(policy=name, seed=10 + i)
            results.append(result)
            print(f"{name}, goal={goal}, distance={result['final_distance_mm']:.2f}mm, success={result['success']}, fallen={result['fallen']}", flush=True)
    reference = rollout(teacher, seed=10, goal=cases[0], seconds=2.5, video=OUTPUT / "teacher.mp4")
    reference["policy"] = "teacher"
    results.append(reference)
    summary = {}
    for name in policies:
        subset = [r for r in results if r["policy"] == name]
        summary[name] = dict(episodes=len(subset), success_count=sum(r["success"] for r in subset),
                             falls=sum(r["fallen"] for r in subset),
                             mean_final_distance_mm=float(np.mean([r["final_distance_mm"] for r in subset])))
    payload = dict(summary=summary, results=results, wall_seconds=time.monotonic() - started,
                   heldout_conditions="Six goal positions and CPG seeds not used for supervised optimization",
                   limitations="Small deterministic synthetic-odor benchmark; no biological validation or robustness claim")
    (OUTPUT / "evaluation.json").write_text(json.dumps(payload, default=json_default, indent=2) + "\n")
    plot_results(results)
    page(summary)
    print(json.dumps(summary, indent=2), flush=True)
    return payload


def plot_results(results):
    fig, axes = plt.subplots(2, 3, figsize=(12, 7), constrained_layout=True)
    for ax, goal in zip(axes.ravel(), [(12, 4), (12, -4), (10, 5), (10, -5), (14, 3), (14, -3)]):
        for name, color in [("untrained", "#64748b"), ("trained", "#008f84")]:
            r = next(r for r in results if r["policy"] == name and np.allclose(r["goal_mm"], goal))
            xy = np.vstack([r["start_mm"], *[s["position_mm"] for s in r["trace"]]])[:, :2]
            ax.plot(xy[:, 0], xy[:, 1], label="Eğitim öncesi" if name == "untrained" else "Eğitim sonrası", color=color)
        ax.add_patch(plt.Circle(goal, 1.5, color="#ea580c", alpha=.2))
        ax.scatter(*goal, color="#ea580c", marker="*", s=80)
        ax.set(title=f"Hedef: {goal} mm", xlabel="x (mm)", ylabel="y (mm)")
        ax.set_aspect("equal", adjustable="datalim")
        ax.grid(alpha=.2)
    axes[0, 0].legend()
    fig.savefig(OUTPUT / "paths.png", dpi=160)
    plt.close(fig)


def page(summary):
    training = json.loads((MODEL / "training.json").read_text())
    circuit = json.loads((MODEL / "circuit.json").read_text())
    a, b = summary["untrained"], summary["trained"]
    content = f'''<!doctype html><html lang="tr"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Sanal sinek · Kokuya yönelme</title>
<style>body{{margin:30px auto;padding:0 22px;max-width:1320px;background:#111722;color:#dce6ef;font:16px system-ui;line-height:1.6}}
h1{{font-size:30px}}h2{{font-size:20px}}p{{max-width:1100px;color:#b9c8d7}}a{{color:#79d9c6}}
.pair{{display:grid;grid-template-columns:1fr 1fr;gap:22px}}video,img{{width:100%;border-radius:8px;background:#000}}.metric{{color:#82dcc9;font-size:21px}}
@media(max-width:800px){{.pair{{grid-template-columns:1fr}}}}</style>
<a href="../index.html">3B beyin anatomisi</a><h1>Sanal sinek · Kokuya yönelme</h1>
<p>MuJoCo fizik simülasyonundan gerçek kayıtlar. Turuncu küre kokulu hedef; hedefe 1,5 mm yaklaşmak başarı sayılır.
Videolar 5 kat yavaş oynar. Canlı ve döndürülebilir MuJoCo penceresi için <code>rtk proxy ./sim.sh --policy trained</code>.</p>
<p class="metric">Altı ayrı hedefte: eğitim öncesi {a['success_count']}/{a['episodes']} → eğitim sonrası {b['success_count']}/{b['episodes']} başarı</p>
<p>MaleCNS'ten {sum(circuit['groups'].values()):,} nöron içeren ORN → ALPN → Kenyon hücresi → MBON alt devresi.
Mevcut KC→MBON bağlantılarının katsayıları ve motor çıkış katmanı, örnek koku yönlendirme komutlarıyla eğitildi.
Gövdenin bacaklarını FlyGym'in hazır CPG yürüyüş kontrolcüsü çalıştırıyor.</p>
<div class="pair"><div><h2>Eğitim öncesi · Arena</h2><video controls muted loop preload="metadata" src="untrained-arena.mp4"></video></div>
<div><h2>Eğitim sonrası · Arena</h2><video controls muted loop preload="metadata" src="trained-arena.mp4"></video></div></div>
<div class="pair"><div><h2>Eğitim öncesi · Yakın görünüm</h2><video controls muted loop preload="metadata" src="untrained.mp4"></video></div>
<div><h2>Eğitim sonrası · Yakın görünüm</h2><video controls muted loop autoplay preload="auto" src="trained.mp4"></video></div></div>
<h2>Aynı koşullarda izlenen yollar</h2><img src="paths.png" alt="Altı hedef için eğitim öncesi ve sonrası fizik simülasyonu yolları">
<details><summary>Referans kontrolcü ve deneyin sınırları</summary>
<p>Referans, iki antenin koku yoğunluğu farkından dönüş komutu çıkaran elle yazılmış bir kuraldır. Eğitim, bu kuralın örneklerini taklit eder.
Yeni hedefler ve motor başlangıç tohumları eğitimde kullanılmadı. Başarılar küçük bir sentetik koku görevine aittir.</p>
<video controls muted loop preload="metadata" src="teacher.mp4"></video>
<p>Bu, tüm MaleCNS beyninin veya taranan aynı bireyin biyolojik dijital ikizi değildir. Nöron dinamikleri, duyusal kodlama ve motor eşleme varsayımsaldır.
Gerçek sinaptik işaretler, nöronların ateşlemesi, tekrarlayan devreler ve biyolojik ödül/plastisite mekanizması bu modelde yoktur.</p>
<p>512 ayrılmış sentetik örnekte hata: {training['before_mse']:.4f} → {training['after_mse']:.4f}.
Değişen mevcut bağlantı katsayısı: {training['changed_existing_synaptic_gains']:,}. Anatomik maske dışına eklenen bağlantı: 0.</p></details>
<p><a href="evaluation.json">Fizik deneyi kayıtları</a> · <a href="https://neuromechfly.org/">FlyGym / NeuroMechFly</a> · <a href="https://male-cns.janelia.org/download/">MaleCNS verisi</a></p></html>'''
    (OUTPUT / "index.html").write_text(content)


if __name__ == "__main__":
    evaluate()
