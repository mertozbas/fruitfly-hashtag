"""Documentation must remain navigable without network or scientific data."""
from collections import Counter
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import unittest
from urllib.parse import unquote, urlsplit

from tools import build_docs

ROOT = Path(__file__).resolve().parents[1]


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.urls, self.images = [], [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        for key in ["href", "src", "poster"]:
            if key in attrs:
                self.urls.append(attrs[key])
        if tag in ["img", "video", "source"] and "src" in attrs:
            self.images.append(attrs["src"])


class DocumentationTests(unittest.TestCase):
    def test_offline_links_and_media(self):
        page = Links()
        page.feed(build_docs.render())
        self.assertFalse([key for key, n in Counter(page.ids).items() if n > 1])
        for url in page.urls:
            parts = urlsplit(url)
            if parts.scheme or parts.netloc:
                continue
            if not parts.path:
                self.assertIn(unquote(parts.fragment), page.ids, url)
            else:
                self.assertTrue((ROOT / "docs" / unquote(parts.path)).is_file(), url)
        self.assertGreater(len(page.images), 10)
        for url in page.images:
            self.assertFalse(urlsplit(url).scheme, f"Offline media requires network: {url}")

    def test_media_manifest_matches(self):
        records = json.loads((ROOT / "docs/media/manifest.json").read_text())["files"]
        for record in records:
            path = ROOT / "docs/media" / record["file"]
            self.assertEqual(path.stat().st_size, record["bytes"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"])

    def test_pypi_uses_versioned_absolute_images(self):
        import markdown
        page = Links()
        page.feed(markdown.markdown(build_docs.pypi_readme()))
        for url in page.urls:
            self.assertTrue(url.startswith("https://"), url)
        local = [url for url in page.images if "raw.githubusercontent.com" in url]
        self.assertGreater(len(local), 5)
        self.assertTrue(all(f"/v{build_docs.VERSION}/" in url for url in local))


if __name__ == "__main__":
    unittest.main()
