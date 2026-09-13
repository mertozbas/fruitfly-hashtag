#!/bin/zsh
set -euo pipefail
cd -- "${0:A:h}"
exec rtk proxy .venv/bin/mjpython fly_sim.py --live "$@"
