"""Portable inference-only export of the selected local checkpoint."""
import hashlib
import io
import json
from pathlib import Path
import zipfile

from lab_tasks import TASKS
from odor_policy import Policy


def archive(path):
    path = Path(path)
    policy = Policy(path)  # Reject mismatched, corrupt or out-of-mask weights.
    task = TASKS[policy.task]
    files = {name:(policy.circuit.directory / name).read_bytes() for name in
             ("circuit.json", "body_ids.npz", "layer0.npz", "layer1.npz", "layer2.npz")}
    files["checkpoint.npz"] = path.read_bytes()
    files["odor_policy.py"] = Path(__file__).with_name("odor_policy.py").read_bytes()
    files["infer.py"] = b'''from pathlib import Path
import argparse
import json
from odor_policy import Policy
p = argparse.ArgumentParser(description="Two sensor values -> learned model command")
p.add_argument("left", type=float)
p.add_argument("right", type=float)
a = p.parse_args()
policy = Policy(Path(__file__).with_name("checkpoint.npz"))
print(json.dumps({"task": policy.task, "command": policy([a.left, a.right])}))
'''
    files["README.md"] = f'''# Taşınabilir MaleCNS alt devre modeli

Görev: **{task['title']}**. Bu arşiv yaşayan bir beyin veya tam beyin emülasyonu içermez.
MaleCNS kaynaklı nöron kimlikleri, seçilmiş anatomik bağlantılar ve eğitilmiş yapay katsayılar içerir.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install numpy scipy
python infer.py 0.10 0.12
```

Girdi: {task['sensor']}. İki sonlu, negatif olmayan değer gerekir.
Çıktı: [-1, 1] aralığında öğrenilmiş skaler. Eşleme: {task['motor']}.
Koku/görme yürüyüşü: sol/sağ CPG sürüşü [0.9 - 0.55*u, 0.9 + 0.55*u].
Kaçınma: daha sıkı dönüş için aynı eşlemede 0.55 yerine 1.1.
Engel: max_correction = 80 * clip(u, 0, 1); CPG sürüşü [0.9, 0.9].
Uçuş: nötr okuma çıkarılır, yön hızı clip(60*clip(u-neutral,-1,1),-8,8) rad/s olur.

Bu paket yalnızca çıkarım yapar. FlyGym/FlyBody gövdesi, motor kontrolcüsü ve sensör
işleyicileri dahil değildir. Yeni ortamda bunları uyarlamalı ve yeniden değerlendirmelisin.
Görmede girdiler göz görüntülerinden kırmızı piksel belirginliğidir; hedef koordinatı değildir.
Temas girdileri MuJoCo karşı kuvvetlerinin tanh(force/5) ile normalizasyonu ve 100 ms sönümüdür.
Tam sensör ve fizik uygulaması ana projenin fly_sim.py dosyasındadır.
Görevler ayrı ağırlık dosyalarıdır; tek modelde birikmiş çoklu beceri veya sürekli öğrenme yoktur.

Anatomi kaynağı: [MaleCNS v1.0](https://male-cns.janelia.org/), CC-BY.
Kaynak atıfları THIRD_PARTY_NOTICES.md içindedir. Yazılım lisansı LICENSE dosyasındadır.
manifest.json arşivdeki dosyaların SHA-256 değerlerini verir.
'''.encode()
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        files[name] = Path(__file__).with_name(name).read_bytes()
    files["manifest.json"] = json.dumps(dict(task=policy.task, circuit_identity=policy.circuit.identity,
        files={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}), indent=2).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipped:
        for name, data in files.items():
            zipped.writestr(name, data)
    return buffer.getvalue()
