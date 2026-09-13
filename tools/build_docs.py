"""Build one offline HTML guide from the maintained Markdown sources."""
import argparse
from html import escape
from pathlib import Path
import re

import markdown

ROOT = Path(__file__).resolve().parents[1]
PAGES = ["README.md", "docs/installation.md", "docs/usage.md", "docs/training.md",
         "docs/data.md", "docs/troubleshooting.md", "docs/development.md", "THIRD_PARTY_NOTICES.md"]


def render():
    links = {name: "#" + Path(name).stem for name in PAGES}
    sections = []
    for name in PAGES:
        content = (ROOT / name).read_text()
        def local_link(match):
            label, target = match.groups()
            if target.startswith(("http:", "https:", "#")):
                return match.group()
            file, _, anchor = target.partition("#")
            resolved = (Path(name).parent / file).as_posix()
            if resolved in links:
                return f"[{label}](#{anchor})" if anchor else f"[{label}]({links[resolved]})"
            return match.group()
        content = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", local_link, content)
        # Repo-only license paths also work from the offline guide.
        content = content.replace("](LICENSE)", "](../LICENSE)").replace("](ui/vendor/THREE-LICENSE.txt)", "](../ui/vendor/THREE-LICENSE.txt)")
        body = markdown.markdown(content, extensions=["tables", "fenced_code", "toc"])
        sections.append(f'<section id="{Path(name).stem}">{body}</section>')
    nav = "".join(f'<a href="{links[p]}">{escape(t)}</a>' for p, t in zip(PAGES,
        ["Başlangıç", "Kurulum", "UI kullanımı", "Eğitim", "Veriler", "Sorun giderme", "Geliştirme", "Kaynaklar"]))
    return '''<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Rehber · Hashtag Neural Lab</title><link rel="icon" href="data:,"><style>
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:30px}body{margin:0;background:#0c121b;color:#d9e5ee;font:16px/1.75 system-ui,sans-serif}aside{position:fixed;inset:0 auto 0 0;width:220px;padding:28px 22px;border-right:1px solid #263744;background:#101923}aside b{display:block;font-size:14px;letter-spacing:.08em;margin-bottom:25px}aside a{display:block;margin:10px 0}a{color:#7ee3c3}main{margin-left:220px;max-width:1080px;padding:36px 48px}section{padding:0 0 44px;margin-bottom:44px;border-bottom:1px solid #324653}h1{font-size:30px;line-height:1.3}h2{font-size:23px;margin-top:32px}h3{font-size:18px}pre{padding:18px;border:1px solid #2e4455;border-radius:7px;background:#060c13;overflow:auto;line-height:1.5}code{font:13px/1.65 ui-monospace,monospace;overflow-wrap:anywhere}blockquote{border-left:3px solid #7ee3c3;margin-left:0;padding:3px 20px;color:#b6c8d7}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:12px;border:1px solid #293b4a;vertical-align:top}th{background:#162332}li{margin:7px 0}.meta{color:#98adbd;font-size:13px}@media(max-width:760px){aside{position:static;width:auto}aside a{display:inline-block;margin-right:18px}main{margin:0;padding:24px}table{display:block;overflow:auto}}@media print{aside{display:none}main{margin:0;padding:0}body{background:white;color:black}a{color:#064f44}pre{background:#eee}}
</style></head><body><aside><b># HASHTAG<br>NEURAL LAB / REHBER</b>''' + nav + '''<p class="meta">Çevrimdışı kılavuz<br>Sürüm 0.2.0<br>Markdown dosyaları bu dizindedir.</p></aside><main>''' + "\n".join(sections) + "</main></body></html>\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = ROOT / "docs/index.html"
    expected = render()
    if args.check:
        if not output.exists() or output.read_text() != expected:
            raise SystemExit("docs/index.html eski; python tools/build_docs.py çalıştırın")
    else:
        output.write_text(expected)
    print("Offline guide verified" if args.check else f"Built {output}")
