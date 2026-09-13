"""Console entry point; importing it never imports scientific dependencies."""
import argparse
import json
import os
import subprocess
import sys
import webbrowser

from . import __version__
from .workspace import home_path, materialize, status, workspace_lock


def main():
    parser = argparse.ArgumentParser(description="Hashtag Neural Lab · yerel beyin ve sinek laboratuvarı")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--home", help="Veri/ortam dizini; varsayılan ~/.fruitfly-hashtag (Git deposundan ayrı)")
    commands = parser.add_subparsers(dest="command")
    ui = commands.add_parser("ui", help="UI aç; eksik kurulum varsa indirme ekranını göster")
    ui.add_argument("--port", type=int, default=8766)
    ui.add_argument("--no-browser", action="store_true")
    ui.add_argument("--setup", action="store_true", help="Kurulum yöneticisini yeniden aç")
    setup = commands.add_parser("setup", help="Bilimsel ortam ve kaynakları kur")
    setup.add_argument("component", choices=["walking", "flight", "all"], nargs="?", default="walking")
    commands.add_parser("doctor", help="Kurulum yollarını ve eksik bileşenleri göster; veri indirmez")
    commands.add_parser("docs", help="Paketle gelen çevrimdışı rehberi aç")
    args = parser.parse_args()
    home = home_path(args.home)
    command = args.command or "ui"
    try:
        if command == "doctor":
            print(json.dumps(status(home), ensure_ascii=False, indent=2))
            return
        with workspace_lock(home):
            materialize(home)
            if command == "docs":
                guide = home / "docs/index.html"
                print(guide)
                webbrowser.open(guide.as_uri())
            elif command == "setup":
                from .setup import install
                install(home, args.component)
            else:
                from .portal import serve
                from .setup import runtime_env
                port = getattr(args, "port", 8766)
                if not 1024 <= port <= 65535:
                    raise ValueError("Port 1024–65535 arasında olmalı")
                browser = not getattr(args, "no_browser", False)
                if getattr(args, "setup", False) or not status(home)["walking_ready"]:
                    if not serve(home, port, open_browser=browser):
                        return
                    browser = False
                url = f"http://127.0.0.1:{port}/"
                print(f"Neural Lab: {url}\nDurdurmak için Ctrl+C.", flush=True)
                if browser:
                    webbrowser.open(url)
                env = runtime_env()
                env["FRUITFLY_PORT"] = str(port)
                result = subprocess.run([str(home / ".venv/bin/python"), "-u", "lab_server.py"], cwd=home, env=env)
                if result.returncode:
                    raise RuntimeError(f"Laboratuvar durdu (kod {result.returncode}). fruitfly ui --setup ile onarın; docs/troubleshooting.md.")
    except KeyboardInterrupt:
        print("\nDurduruldu. İndirilen veriler ve eğitimler korundu.")
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
