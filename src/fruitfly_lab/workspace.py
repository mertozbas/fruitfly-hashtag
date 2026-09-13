"""Materialize a versioned, explicit code bundle without copying user data."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path

from . import __version__


def home_path(value=None):
    return Path(value or os.environ.get("FRUITFLY_HOME", "~/.fruitfly-hashtag")).expanduser().resolve()


def bundle_files():
    package = Path(__file__).parent
    bundle = package / "bundle"
    if bundle.is_dir():
        return {p.relative_to(bundle).as_posix(): p for p in bundle.rglob("*") if p.is_file()}
    # Source checkout / editable installation uses the identical explicit wheel map.
    import tomllib
    root = package.parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text())
    mapping = config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    return {target.removeprefix("fruitfly_lab/bundle/"): root / source
            for source, target in mapping.items()}


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


@contextmanager
def workspace_lock(home):
    if os.name != "posix":
        raise RuntimeError("Bu sürüm macOS ve Linux içindir. Windows için docs/installation.md rehberini okuyun.")
    import fcntl
    home.mkdir(parents=True, exist_ok=True)
    with (home / ".fruitfly.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Bu çalışma dizininde bir UI veya kurulum zaten açık. Önce o terminalde Ctrl+C kullanın.") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def materialize(home):
    home = home.resolve()
    if (home / ".git").exists():
        raise RuntimeError("--home bir Git deposu olamaz. Ayrı bir veri dizini seçin; varsayılan ~/.fruitfly-hashtag.")
    record = home / ".fruitfly-bundle.json"
    previous = json.loads(record.read_text()) if record.exists() else {"files": {}}
    files = bundle_files()
    hashes = {name: digest(source) for name, source in files.items()}
    for name, source in files.items():
        target = home / name
        if target.is_symlink() or not target.resolve().is_relative_to(home):
            raise RuntimeError(f"Yönetilen kod yolu sembolik bağlantı olamaz: {name}")
        if target.exists() and digest(target) not in {hashes[name], previous["files"].get(name)}:
            raise RuntimeError(f"Yerel değişiklik korunuyor: {target}. Dosyayı yedekleyip ayrı bir --home seçin.")
    for name, source in files.items():
        target = home / name
        if target.exists() and digest(target) == hashes[name]:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".fruitfly-tmp")
        temporary.write_bytes(source.read_bytes())
        temporary.replace(target)
    record.write_text(json.dumps({"version": __version__, "files": hashes}, indent=2) + "\n")
    (home / ".runtime").mkdir(exist_ok=True)
    return home


def status(home):
    walking = [".venv/bin/python", "models/odor_navigation/trained.npz",
               "models/odor_navigation/untrained.npz", "models/odor_navigation/circuit.json",
               "artifacts/lab/graph.json", "artifacts/lab/anatomy.json", "artifacts/lab/anatomy.f32",
               "data/male-cns-v1.0/derived/adjacency.npz", ".runtime/setup-walking.json"]
    flight = ["flight/.venv/bin/python", "data/flybody/trained-fly-policies/flight/saved_model.pb",
              "data/flybody/datasets_flight-imitation/wing_pattern_fmech.npy", ".runtime/setup-flight.json"]
    missing = lambda names: [name for name in names if not (home / name).is_file()]
    walk_missing, flight_missing = missing(walking), missing(flight)
    return {"version": __version__, "home": str(home), "walking_ready": not walk_missing,
            "flight_ready": not flight_missing, "walking_missing": walk_missing,
            "flight_missing": flight_missing}
