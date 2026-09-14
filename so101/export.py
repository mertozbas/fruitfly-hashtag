"""Self-contained NumPy/SciPy robot inference; excludes hardware execution."""
import hashlib
import io
import json
from pathlib import Path
import zipfile
from .policy import Policy,OBS_SIZE,PHASES,TARGET_CENTER,TARGET_SCALE


def archive(path):
    path=Path(path);policy=Policy(path);root=Path(__file__).resolve().parents[1]
    files={n:(path.parent/n).read_bytes() for n in ("circuit.json","body_ids.npz","layer0.npz","layer1.npz","layer2.npz")}
    files.update({"checkpoint.npz":path.read_bytes(),"odor_policy.py":(root/"odor_policy.py").read_bytes(),
                  "so101/__init__.py":b"","so101/policy.py":(root/"so101/policy.py").read_bytes(),
                  "so101/recovery.py":(root/"so101/recovery.py").read_bytes()})
    files['infer.py']=b'''import argparse,json
from pathlib import Path
from so101.policy import Policy
p=argparse.ArgumentParser(description="30 normalized robot/task features -> bounded four-value action")
p.add_argument("observation",nargs="?",help="JSON array of 30 features; defaults to the included neutral schema example")
a=p.parse_args()
observation=json.loads(a.observation) if a.observation else json.loads(Path(__file__).with_name("example-observation.json").read_text())
policy=Policy(Path(__file__).with_name("checkpoint.npz"))
action,layers=policy.activity(observation,advance=True)
print(json.dumps({"action":action.tolist(),"layer_means":[float(x.mean()) for x in layers],"memory":policy.memory.tolist() if policy.has_memory else None}))
'''
    from .task import OBSERVATION_NAMES
    files['observation-schema.json']=json.dumps(dict(names=OBSERVATION_NAMES,shape=[30],action=['target_x','target_y','target_z','gripper'] if policy.action_mode=='target' else ['dx','dy','dz','gripper'],
        scaling='Input values follow so101/task.py observation(): state ranges, deltas in metres / .15, physical progress flags, previous action. Checkpoint applies its own stored mean and scale.',
        action_mode=policy.action_mode,
        execution='Target metres=center+scale*XYZ; bounded proportional Cartesian tracking then IK and position servos, maximum 3 mm per 50 ms decision. Gripper radians=.08+(u+1)*.41.' if policy.action_mode=='target' else 'XYZ * .003 metres per 50 ms decision; gripper radians=.08+(u+1)*.41; IK and deterministic limits required.',
        target_center_m=TARGET_CENTER.tolist(),target_scale_m=TARGET_SCALE.tolist(),
        learned_memory=list(PHASES) if policy.has_memory else None,
        learned_motor_heads=policy.motor_heads,trainable_anatomical_layers=[0,1,2] if policy.all_core else [2],
        active_external_features=[name for name,enabled in zip(OBSERVATION_NAMES,policy.input_mask[:OBS_SIZE]) if enabled],
        empirical_transition_support=policy.has_transition_graph,
        memory_contract='Call policy.reset() at episode start. Keep one Policy instance and call policy(observation) each decision; its learned phase output feeds the next forward pass. Optional nonzero transition_counts constrain phase choices to transitions observed in training demonstrations; this is an engineered learned task prior, separate from anatomy.'),indent=2).encode()
    files['example-observation.json']=json.dumps(policy.input_mean[:OBS_SIZE].tolist()).encode()
    files['requirements.txt']=b'numpy>=2.2,<3\nscipy>=1.15,<2\n'
    files['README.md']='''# SO-101 sinir ağı çıkarımı

Python, NumPy ve SciPy gerekir:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python infer.py
```

Komut şema örneğinden dört hareket değeri üretir. Örnek, eğitim girdilerinin
ortalamasıdır; çalıştırılabilir bir fizik durumu veya hareket talimatı değildir.
Gerçek gözlem dizisini JSON olarak komuta verebilirsiniz. Gözlem sırası
`observation-schema.json` içindedir.
Ardışık çalışmada aynı `Policy` nesnesini koruyun, bölüm başında `reset()`
çağırın ve her karar için `policy(observation)` kullanın. Bellekli modelde
öğrenilmiş sekizli aşama okuması sonraki karara geri beslenir. Bunlar yapay
bellek değerleridir; anatomik nöron değildir. Şemada
`empirical_transition_support: true` ise gösterimlerden öğrenilmiş geçiş
izinleri de uygulanır. Bu görev önbilgisi anatomik bağlantılardan ayrıdır;
konum, zaman veya hazır hareket yolu içermez.
Bu paket hareket komutunu hesaplar; robot sürücüsü veya fizik çalıştırmaz.
Kamera algısı ve temas ölçümü uygulama tarafında sağlanır. Canlı laboratuvardaki
aynı sahnede tekrar deneme için `so101.recovery.RetrySupervisor` da dahildir.
Her yeni bölümde gözetmeni sıfırlayın. Her karar öncesinde
`retry.observe(observation, time_s, policy)` çağırın; `retry.exhausted` durumunda
motor yürütmesini durdurun. Gözetmen motor komutu üretmez; görev belleğini
sıfırlar. Ayrıca görüntü tazeliği, fizik sınırları ve toplam süre kapıları gerekir.
Checkpoint, anatomik matrisler, giriş adaptörü ve öğrenilmiş bağlantı katsayıları
birlikte taşınır. Canlı sinek beyni veya başka robota doğrudan uyumlu politika değildir.
Gerçek donanım için kalibrasyon, gözlem eşlemesi ve kontrollü doğrulama gerekir.
'''.encode()
    for n in ("LICENSE","THIRD_PARTY_NOTICES.md"):files[n]=(root/n).read_bytes()
    files['manifest.json']=json.dumps(dict(task='so101',circuit_identity=policy.circuit.identity,
        files={n:hashlib.sha256(b).hexdigest() for n,b in files.items()}),indent=2).encode()
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in files.items():z.writestr(n,b)
    return out.getvalue()
