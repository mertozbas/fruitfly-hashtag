"""Download only the official flight references and published policy archive."""
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT / "data/flybody"
FILES=[(44815195,"trained-fly-policies.zip",6537720,None),
       (51196859,"datasets_flight-imitation.zip",12880076,"bb35ce27e07c4ffbd3d56ff6dec90905")]
SHA256={"trained-fly-policies.zip":"2d9937c9af2baafad1690c1b318791bde417b4d26dd96d4385ab6723d5d58582",
        "datasets_flight-imitation.zip":"0d152331e38f2ca6bb1f3286c2500eab49b5ccef93c51a9cc9cff9bb6cd368d0"}

def main():
    DEST.mkdir(parents=True,exist_ok=True)
    records=[]
    for file_id,name,size,md5 in FILES:
        path=DEST/name
        url=f"https://ndownloader.figshare.com/files/{file_id}"
        if not path.exists():
            tmp=path.with_suffix(".part")
            with urllib.request.urlopen(url,timeout=60) as response,tmp.open("wb") as out:
                while block:=response.read(1024*1024):out.write(block)
            if tmp.stat().st_size!=size or hashlib.sha256(tmp.read_bytes()).hexdigest()!=SHA256[name]:
                raise ValueError(f"Flight archive size/SHA256 mismatch: {name}")
            tmp.replace(path)
        content=path.read_bytes()
        if len(content)!=size or hashlib.sha256(content).hexdigest()!=SHA256[name]:
            raise ValueError(f"Cached flight archive size/SHA256 mismatch: {name}")
        if md5 and hashlib.md5(content).hexdigest()!=md5:
            raise ValueError(f"Flight archive MD5 mismatch: {name}")
        directory=DEST/path.stem
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise ValueError(f"Corrupt ZIP: {name}")
            for member in archive.infolist():
                target=(directory/member.filename).resolve()
                if not target.is_relative_to(directory.resolve()):
                    raise ValueError(f"Unsafe archive member: {member.filename}")
            archive.extractall(directory)
        records.append(dict(file_id=file_id,url=url,name=name,bytes=size,source_md5=md5,sha256=hashlib.sha256(content).hexdigest()))
        print(f"Verified {name}: {size/1e6:.1f} MB",flush=True)
    manifest=dict(source="https://doi.org/10.25378/janelia.25309105.v4",files=records,
                  extracted=[dict(path=str(p.relative_to(DEST)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in DEST.rglob("*") if p.is_file() and p.suffix not in {".zip",".json"}])
    (DEST/"manifest.json").write_text(json.dumps(manifest,indent=2))

if __name__=="__main__":main()
