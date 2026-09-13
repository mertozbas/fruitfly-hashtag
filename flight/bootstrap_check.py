"""Verify checkpoint loading and a few real flight steps during installation."""
import json
from pathlib import Path
from navigation import BrainFlight


def main():
    root = Path(__file__).resolve().parents[1]
    flight = BrainFlight(root / "models/odor_navigation/trained.npz")
    flight.reset(seed=10, goal=(25, 8))
    for _ in range(5):
        flight.step()
    print("FlyBody uçuş politikası yüklendi; 5 fizik kontrol adımı tamamlandı.", flush=True)
    (root / ".runtime/setup-flight.json").write_text(json.dumps({"check": "flight-startup", "steps": 5}))


if __name__ == "__main__":
    main()
