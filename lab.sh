#!/bin/zsh
set -euo pipefail
cd -- "${0:A:h}"
if [[ ! -x .venv/bin/jupyter ]]; then
  rtk proxy uv sync --locked
fi
exec rtk proxy .venv/bin/jupyter lab baslangic.ipynb --ip=127.0.0.1 --port=8888 --ServerApp.port_retries=0
