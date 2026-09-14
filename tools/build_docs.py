"""Build the offline guide and PyPI description from maintained Markdown."""
import argparse
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import posixpath
import re
import tomllib
from urllib.parse import unquote, urlsplit

import markdown
from markdown.extensions.toc import slugify_unicode

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
REPO = "https://github.com/mertozbas/fruitfly-hashtag"
RAW = "https://raw.githubusercontent.com/mertozbas/fruitfly-hashtag"
PAGES = {
    "README.md": "Proje ve görüntüler", "docs/README.md": "Rehber dizini",
    "docs/installation.md": "Kurulum", "LAB.md": "Laboratuvar turu",
    "docs/usage.md": "UI kullanımı", "docs/training.md": "Eğitim",
    "SIMULATION.md": "Yürüyüş", "flight/README.md": "Uçuş",
    "docs/local-tasks.md": "Yeni yerel görevler", "docs/experiments.md": "Deney kayıtları", "docs/data.md": "Veriler",
    "docs/troubleshooting.md": "Sorun giderme", "docs/development.md": "Geliştirme",
    "docs/media/README.md": "Medya kökeni", "THIRD_PARTY_NOTICES.md": "Kaynaklar",
}


def section_id(name):
    return str(Path(name).with_suffix("")).replace("/", "-")


def source_target(name, target):
    parts = urlsplit(target)
    if parts.scheme or parts.netloc:
        return None
    file = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(parts.path))) if parts.path else name
    return file, unquote(parts.fragment)


class OfflineHTML(HTMLParser):
    """Resolve links after Markdown parsing, including raw HTML figures."""
    def __init__(self, name):
        super().__init__(convert_charrefs=False)
        self.name, self.output = name, []

    def url(self, target):
        parsed = source_target(self.name, target)
        if parsed is None:
            return target
        file, anchor = parsed
        if file in PAGES:
            return "#" + section_id(file) + ("--" + anchor if anchor else "")
        if file == "docs/index.html":
            return "#README"
        if file.startswith("docs/") or file in {"LICENSE", "ui/vendor/THREE-LICENSE.txt"}:
            return posixpath.relpath(file, "docs") + ("#" + anchor if anchor else "")
        return f"{REPO}/blob/v{VERSION}/{file}" + ("#" + anchor if anchor else "")

    def handle_starttag(self, tag, attrs):
        values = []
        for key, value in attrs:
            if key in {"src", "href", "poster"} and value is not None:
                value = self.url(value)
            elif key == "id" and value:
                value = section_id(self.name) + "--" + value
            values.append(key if value is None else f'{key}="{escape(value, quote=True)}"')
        self.output.append("<" + tag + (" " + " ".join(values) if values else "") + ">")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        self.output.append(f"</{tag}>")

    def handle_data(self, data):
        self.output.append(data)

    def handle_entityref(self, name):
        self.output.append(f"&{name};")

    def handle_charref(self, name):
        self.output.append(f"&#{name};")


def render():
    sections = []
    for name in PAGES:
        content = (ROOT / name).read_text()
        content = re.sub(r"<!-- online-badges -->.*?<!-- /online-badges -->", "", content, flags=re.S)
        body = markdown.markdown(content, extensions=["tables", "fenced_code", "toc"],
                                 extension_configs={"toc": {"slugify": slugify_unicode}})
        parser = OfflineHTML(name)
        parser.feed(body)
        sections.append(f'<section id="{section_id(name)}">' + "".join(parser.output) + "</section>")
    nav = "".join(f'<a href="#{section_id(p)}">{escape(t)}</a>' for p, t in PAGES.items())
    css = (ROOT / "docs/guide.css").read_text()
    head = f'<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Rehber · Hashtag Neural Lab</title><link rel="icon" href="data:,"><style>{css}</style></head>'
    sidebar = f'<aside><b># HASHTAG<br>NEURAL LAB / REHBER</b>{nav}<p class="meta">Çevrimdışı kılavuz<br>Sürüm {VERSION}<br>Görseller ve kısa videolar dahildir.</p></aside>'
    return "<!doctype html>" + head + "<body>" + sidebar + "<main>" + "\n".join(sections) + "</main></body></html>\n"


def pypi_readme():
    content = (ROOT / "README.md").read_text()
    def url(target, image=False):
        parsed = source_target("README.md", target)
        if parsed is None:
            return target
        file, anchor = parsed
        base = f"{RAW}/v{VERSION}" if image else f"{REPO}/blob/v{VERSION}"
        return base + "/" + file + ("#" + anchor if anchor else "")
    content = re.sub(r'(!?)\[([^\]]*)\]\(([^)]+)\)', lambda m: f'{m[1]}[{m[2]}]({url(m[3], bool(m[1]))})', content)
    return re.sub(r'(src|href)="([^"]+)"', lambda m: f'{m[1]}="{url(m[2], m[1] == "src")}"', content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, expected in [("docs/index.html", render()), ("docs/PYPI.md", pypi_readme())]:
        output = ROOT / name
        if args.check:
            if not output.exists() or output.read_text() != expected:
                raise SystemExit(f"{name} eski; python tools/build_docs.py çalıştırın")
        else:
            output.write_text(expected)
    print("Rehber ve PyPI açıklaması doğrulandı" if args.check else "Rehber ve PyPI açıklaması üretildi")


if __name__ == "__main__":
    main()
