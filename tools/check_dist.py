"""Audit both release artifacts; only code, docs and source manifests may ship."""
from pathlib import Path
import tarfile
import zipfile

FORBIDDEN = {"data", "models", "artifacts", ".runtime", ".venv", ".git", ".env", "__pycache__"}
SUFFIXES = (".npz", ".npy", ".feather", ".swc", ".pyc", ".pem", ".key", ".pb", ".hdf5")


def main():
    paths = sorted(Path("dist").glob("fruitfly_hashtag-*"))
    assert len(paths) == 2, "Expected one wheel and one sdist"
    for path in paths:
        if path.suffix == ".whl":
            with zipfile.ZipFile(path) as archive:
                records = [(p.filename, p.file_size) for p in archive.infolist()]
                assert b"fruitfly = fruitfly_lab.cli:main" in archive.read(next(n for n in archive.namelist() if n.endswith("entry_points.txt")))
        else:
            with tarfile.open(path) as archive:
                records = [(p.name, p.size) for p in archive.getmembers()]
        for name, size in records:
            assert not FORBIDDEN.intersection(Path(name).parts), name
            assert not name.endswith(SUFFIXES), name
            assert size < 4_000_000, name
        assert any(name.endswith("docs/index.html") for name, _ in records)
        assert any(name.endswith("THREE-LICENSE.txt") for name, _ in records)
        assert path.stat().st_size < 8_000_000  # Offline screenshots and short simulation recordings.
        print(f"{path.name}: {path.stat().st_size:,} bytes, {len(records)} entries; no brain/model/user data")


if __name__ == "__main__":
    main()
