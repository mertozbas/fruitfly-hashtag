#!/bin/zsh
set -euo pipefail
cd -- "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  rtk proxy uv sync --locked
fi
if [[ ! -f artifacts/index.html ]]; then
  rtk proxy .venv/bin/python prepare.py
fi
echo 'Yerel 3B görünümler: http://127.0.0.1:8765'
echo 'Durdurmak için Ctrl+C.'
exec rtk proxy .venv/bin/python -m http.server 8765 --bind 127.0.0.1 --directory artifacts
