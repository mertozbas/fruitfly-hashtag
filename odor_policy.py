"""Shared NumPy/SciPy MaleCNS inference for walking and isolated flight."""
import hashlib
import json
import os
from pathlib import Path
import numpy as np
from scipy import sparse

ROOT = Path(__file__).resolve().parent
MODEL = Path(os.environ.get("FRUITFLY_MODEL_DIR", ROOT / "models" / "odor_navigation"))
GROUPS = ("ORN", "ALPN", "Kenyon_Cell", "MBON")


class Circuit:
    def __init__(self):
        manifest = MODEL / "circuit.json"
        if not manifest.exists():
            from odor_brain import build_circuit
            build_circuit()
        self.metadata = json.loads(manifest.read_text())
        self.identity = hashlib.sha256((MODEL / "circuit.json").read_bytes()).hexdigest()
        for record in self.metadata["layers"]:
            if hashlib.sha256((MODEL / record["file"]).read_bytes()).hexdigest() != record["sha256"]:
                raise ValueError("Circuit file hash mismatch")
        self.layers = [sparse.load_npz(MODEL / f"layer{i}.npz") for i in range(3)]
        with np.load(MODEL / "body_ids.npz", allow_pickle=False) as ids:
            self.side = ids["orn_side"].copy()

    def kc_features(self, odor):
        x = np.asarray(odor, dtype=np.float32).reshape(-1, 2)
        if not np.isfinite(x).all() or (x < 0).any():
            raise ValueError("Odor concentrations must be finite and nonnegative")
        contrast = (x[:, 0] - x[:, 1]) / (x.sum(axis=1) + 1e-6)
        channels = np.stack([.5 + 5 * contrast, .5 - 5 * contrast], axis=1).clip(0, 1)
        activity = channels[:, self.side]
        for layer in self.layers[:2]:
            activity = np.tanh(2 * (layer.T @ activity.T).T)
        return np.asarray(activity, dtype=np.float32)


class Policy:
    def __init__(self, path):
        self.circuit = Circuit()
        with np.load(path, allow_pickle=False) as state:
            if str(state["circuit_identity"]) != self.circuit.identity:
                raise ValueError("Checkpoint belongs to a different circuit")
            self.weight = state["weight"].copy()
            self.decoder = state["decoder"].copy()
            self.bias = state["bias"].copy()
        base = self.circuit.layers[2].toarray()
        if self.weight.shape != base.shape or np.any(self.weight[base == 0] != 0):
            raise ValueError("Checkpoint introduced connections outside the anatomical mask")
        if not all(np.isfinite(a).all() for a in (self.weight, self.decoder, self.bias)):
            raise ValueError("Non-finite checkpoint parameters")

    def __call__(self, odor):
        kc = self.circuit.kc_features(odor)
        mbon = np.tanh(2 * kc @ self.weight)
        return float(np.tanh(mbon @ self.decoder + self.bias).reshape(-1)[0])

    def activity(self, odor):
        """Exact forward activations for instrumentation; no simulated spikes."""
        x = np.asarray(odor, dtype=np.float32).reshape(2)
        if not np.isfinite(x).all() or (x < 0).any():
            raise ValueError("Invalid odor concentrations")
        contrast = (x[0] - x[1]) / (x.sum() + 1e-6)
        channels = np.clip([.5 + 5 * contrast, .5 - 5 * contrast], 0, 1)
        orn = channels[self.circuit.side].astype(np.float32)
        alpn = np.tanh(2 * (self.circuit.layers[0].T @ orn))
        kc = np.tanh(2 * (self.circuit.layers[1].T @ alpn))
        mbon = np.tanh(2 * (kc @ self.weight))
        turn = float(np.tanh(mbon @ self.decoder + self.bias).item())
        return turn, [orn, alpn, kc, mbon]

