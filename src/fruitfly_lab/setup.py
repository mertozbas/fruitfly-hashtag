"""Bounded installation of separate scientific runtimes in the user's workspace."""
import os
import platform
import shutil
import subprocess
import sys

from .download import download_brain


def runtime_env():
    env = dict(os.environ)
    # A caller's virtualenv/model selection must not leak into a fresh installation.
    for key in ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "FRUITFLY_MODEL_DIR", "UV_PROJECT_ENVIRONMENT"):
        env.pop(key, None)
    env.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1", PYTHONUNBUFFERED="1")
    if sys.platform == "linux":
        env.setdefault("MUJOCO_GL", "egl")
    return env


def run(args, home, timeout=3600):
    print("→ " + " ".join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=home, env=runtime_env(), check=True, timeout=timeout)


def install(home, component):
    if sys.platform not in {"darwin", "linux"}:
        raise RuntimeError("Simülasyon kurulumu macOS/Linux gerektirir; docs/installation.md dosyasını okuyun.")
    if shutil.disk_usage(home).free < 5 * 1024**3:
        raise RuntimeError("En az 5 GiB boş disk gerekli; temiz kurulum için 15 GiB veya fazlasını ayırın.")
    import uv
    executable = uv.find_uv_bin()
    if component in {"walking", "all"}:
        print("1/4 · Python 3.12 ve yürüyüş/eğitim ortamı", flush=True)
        run([executable, "sync", "--locked", "--python", "3.12", "--project", home], home)
        print("2/4 · MaleCNS kaynakları (yaklaşık 1,11 GB); yarım indirmeler devam eder", flush=True)
        download_brain(home)
        print("3/4 · Anatomi, devre ve ilk yerel eğitim hazırlanıyor", flush=True)
        run([home / ".venv/bin/python", "-u", "bootstrap_runtime.py"], home)
        print("4/4 · Yürüyüş kurulumu tamamlandı", flush=True)
    if component in {"flight", "all"}:
        if not (home / "models/odor_navigation/trained.npz").is_file():
            raise RuntimeError("Önce yürüyüş + beyin kurulumunu tamamlayın.")
        if sys.platform == "darwin" and platform.machine() != "arm64":
            raise RuntimeError("Bu uçuş kilidi Apple Silicon macOS içindir. Intel Mac uçuşu bu sürümde desteklenmiyor.")
        print("Uçuş · Ayrı Python 3.11 / TensorFlow ortamı (Git gerekli)", flush=True)
        run([executable, "sync", "--locked", "--python", "3.11", "--project", home / "flight"], home)
        run([home / "flight/.venv/bin/python", "-u", "flight/download_assets.py"], home)
        run([home / "flight/.venv/bin/python", "-u", "flight/bootstrap_check.py"], home)
    print("Kurulum doğrulandı. Laboratuvarı açabilirsiniz.", flush=True)


if __name__ == "__main__":
    # Internal portal child; its parent owns the workspace lock and process group.
    import argparse
    from .workspace import home_path
    parser = argparse.ArgumentParser()
    parser.add_argument("home")
    parser.add_argument("component", choices=["walking", "flight", "all"])
    arguments = parser.parse_args()
    install(home_path(arguments.home), arguments.component)
