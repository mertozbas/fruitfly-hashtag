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
            assert tmp.stat().st_size==size, name
            tmp.replace(path)
        content=path.read_bytes()
        assert len(content)==size
        if md5:assert hashlib.md5(content).hexdigest()==md5
        directory=DEST/path.stem
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            for member in archive.infolist():
                target=(directory/member.filename).resolve()
                assert target.is_relative_to(directory.resolve()), member.filename
            archive.extractall(directory)
        records.append(dict(file_id=file_id,url=url,name=name,bytes=size,source_md5=md5,sha256=hashlib.sha256(content).hexdigest()))
        print(f"Verified {name}: {size/1e6:.1f} MB",flush=True)
    manifest=dict(source="https://doi.org/10.25378/janelia.25309105.v4",files=records,
                  extracted=[dict(path=str(p.relative_to(DEST)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in DEST.rglob("*") if p.is_file() and p.suffix not in {".zip",".json"}])
    (DEST/"manifest.json").write_text(json.dumps(manifest,indent=2))

if __name__=="__main__":main()
