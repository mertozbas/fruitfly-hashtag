"""Install hardware diagnostics without changing the scientific Python runtime."""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    uv=shutil.which('uv')
    if not uv:raise SystemExit('uv bulunamadı. Önce Neural Lab kurulumunu tamamla.')
    environment=ROOT/'.runtime/hardware-venv'
    python=environment/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    if not python.exists():subprocess.run([uv,'venv','--python',sys.executable,str(environment)],check=True)
    subprocess.run([uv,'pip','install','--python',str(python),'-r',str(ROOT/'so101/hardware-requirements.txt')],check=True)
    subprocess.run([str(python),'-m','so101.hardware_worker','inventory'],cwd=ROOT,check=True)
    print('Donanım ortamı hazır. Envanter sorgusu motorlara bağlanmaz ve kamera açmaz.')


if __name__=='__main__':main()
