#!/bin/zsh
set -euo pipefail
cd -- "${0:A:h}"
exec rtk proxy .venv/bin/python tools/run_neural_lab.py "$@"
