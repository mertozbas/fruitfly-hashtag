"""Small inference archive; does not ship training teachers or robot assets."""
import hashlib
import io
import json
from pathlib import Path
import zipfile
from .policy import Policy


def archive(path):
    path=Path(path);policy=Policy(path);root=Path(__file__).resolve().parents[1]
    files={name:(path.parent/name).read_bytes() for name in ('circuit.json','body_ids.npz','layer0.npz','layer1.npz','layer2.npz')}
    files['checkpoint.npz']=path.read_bytes()
    for name in ('odor_policy.py','LICENSE','THIRD_PARTY_NOTICES.md','tictactoe/__init__.py','tictactoe/policy.py','tictactoe/rules.py'):
        files[name]=(root/name).read_bytes()
    files['infer.py']=b'''from pathlib import Path
import argparse,json
from tictactoe.policy import Policy
p=argparse.ArgumentParser(description="Nine cells: 0=empty, 1=X, -1=O")
p.add_argument("cells",nargs=9,type=int)
a=p.parse_args();move,layers,details=Policy(Path(__file__).with_name("checkpoint.npz")).activity(a.cells)
print(json.dumps({"cell_zero_based":move,"cell_one_based":move+1,"decision":details}))
'''
    files['README.md']='''# Tic-tac-toe strateji modeli

Python ortamında `pip install numpy scipy` ardından:

```bash
python infer.py 0 0 0 0 0 0 0 0 0
```

Kareler soldan sağa, yukarıdan aşağıya sıralıdır. 0 boş, 1 X, -1 O.
X başlar. Çıktı yalnızca seçilen karedir; robot motor komutu değildir.
Hamle skorları MaleCNS anatomik alt ağından gelir. Çıkarımda minimax,
arama tablosu veya LLM bulunmaz. Anatomik maske ve dosya kimlikleri doğrulanır.
Bu yapay giriş/çıkışlarla eğitilmiş bir hesaplamalı modeldir; yaşayan beyin değildir.
'''.encode()
    files['manifest.json']=json.dumps(dict(task='tictactoe',circuit_identity=policy.circuit.identity,
        files={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}),indent=2).encode()
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items():z.writestr(name,data)
    return buffer.getvalue()
