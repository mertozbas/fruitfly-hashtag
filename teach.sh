#!/bin/zsh
set -euo pipefail
cd -- "${0:A:h}"
rtk proxy .venv/bin/python -u odor_brain.py train "$@"
rtk proxy .venv/bin/python -u evaluate_odor.py
echo 'Sonuçlar: http://127.0.0.1:8765/simulation/'
echo 'Eğitilen modeli canlı açmak için: rtk proxy ./sim.sh --policy trained'
