"""Resumable, generation-pinned MaleCNS downloads, verified before promotion."""
import json
from pathlib import Path
import time
import urllib.request

from .workspace import digest


def fetch(record, destination, *, emit=print):
    target = destination / record["file"]
    if target.exists():
        if target.stat().st_size != record["size"] or digest(target) != record["sha256"]:
            raise ValueError(f"Dosya doğrulanamadı; otomatik üzerine yazılmadı: {target}. Dosyayı başka yere taşıyıp yeniden deneyin.")
        emit(f"SHA256 doğrulandı: {target.name}")
        return
    part = target.with_suffix(target.suffix + ".part")
    offset = part.stat().st_size if part.exists() else 0
    if offset > record["size"]:
        part.unlink()
        offset = 0
    if offset < record["size"]:
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        request = urllib.request.Request(record["download_url"], headers=headers)
        with urllib.request.urlopen(request, timeout=60) as response:
            if offset and response.status == 206:
                if not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                    raise ValueError("Sunucu beklenen indirme aralığını döndürmedi")
            elif response.status == 200:
                offset = 0
            else:
                raise ValueError(f"Beklenmeyen indirme yanıtı: {response.status}")
            last = 0
            with part.open("ab" if offset else "wb") as output:
                for block in iter(lambda: response.read(1024 * 1024), b""):
                    output.write(block)
                    offset += len(block)
                    if offset > record["size"]:
                        raise ValueError("İndirme beklenen boyutu aştı")
                    if time.monotonic() - last > 2:
                        emit(f"{target.name}: {offset / 1e6:.1f} / {record['size'] / 1e6:.1f} MB")
                        last = time.monotonic()
    if part.stat().st_size != record["size"] or digest(part) != record["sha256"]:
        part.unlink()
        raise ValueError(f"SHA256/boyut uyuşmuyor: {target.name}. Yeniden deneyin.")
    part.replace(target)
    emit(f"SHA256 doğrulandı: {target.name}")


def download_brain(home):
    manifest = json.loads((Path(__file__).parent / "sources.json").read_text())
    destination = home / "data/male-cns-v1.0"
    destination.mkdir(parents=True, exist_ok=True)
    for record in manifest["files"]:
        fetch(record, destination, emit=lambda message: print(message, flush=True))
    # Preserve any previously verified skeleton entries, never replace user models.
    path = destination / "manifest.json"
    existing = json.loads(path.read_text()) if path.exists() else {"files": []}
    manifest["files"] += [r for r in existing["files"] if r["file"].endswith(".swc")]
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n")
    temporary.replace(path)
