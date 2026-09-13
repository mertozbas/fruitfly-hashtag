#!/bin/zsh
set -euo pipefail
cd -- "${0:A:h}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
exec rtk proxy .venv/bin/python -u lab_server.py
