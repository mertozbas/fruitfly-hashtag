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
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else MODEL
        manifest = self.directory / "circuit.json"
        if not manifest.exists():
            if self.directory != MODEL:
                raise FileNotFoundError(f"Missing circuit manifest: {manifest}")
            from odor_brain import build_circuit
            build_circuit()
        self.metadata = json.loads(manifest.read_text())
        self.identity = hashlib.sha256(manifest.read_bytes()).hexdigest()
        self.groups = tuple(self.metadata.get("group_order", GROUPS))
        self.encoding = self.metadata.get("input_encoding", "bilateral_contrast")
        for record in self.metadata["layers"]:
            if hashlib.sha256((self.directory / record["file"]).read_bytes()).hexdigest() != record["sha256"]:
                raise ValueError("Circuit file hash mismatch")
        self.layers = [sparse.load_npz(self.directory / f"layer{i}.npz") for i in range(3)]
        ids_path = self.directory / "body_ids.npz"
        if self.metadata.get("body_ids_sha256") and hashlib.sha256(ids_path.read_bytes()).hexdigest() != self.metadata["body_ids_sha256"]:
            raise ValueError("Neuron identity file hash mismatch")
        with np.load(ids_path, allow_pickle=False) as ids:
            self.side = ids["orn_side"].copy()

    def sensory_activity(self, odor):
        x = np.asarray(odor, dtype=np.float32).reshape(-1, 2)
        if not np.isfinite(x).all() or (x < 0).any():
            raise ValueError("Sensory values must be finite and nonnegative")
        if self.encoding == "bilateral_intensity":
            channels = x.clip(0, 1)
        elif self.encoding == "bilateral_contrast":
            contrast = (x[:, 0] - x[:, 1]) / (x.sum(axis=1) + 1e-6)
            channels = np.stack([.5 + 5 * contrast, .5 - 5 * contrast], axis=1).clip(0, 1)
        else:
            raise ValueError("Unknown sensory encoding")
        return channels[:, self.side]

    def kc_features(self, odor):
        """Features at the third layer (KC in the original odor circuit)."""
        activity = self.sensory_activity(odor)
        for layer in self.layers[:2]:
            activity = np.tanh(2 * (layer.T @ activity.T).T)
        return np.asarray(activity, dtype=np.float32)


class Policy:
    def __init__(self, path):
        path = Path(path)
        self.circuit = Circuit(path.parent if (path.parent / "circuit.json").exists() else MODEL)
        with np.load(path, allow_pickle=False) as state:
            if str(state["circuit_identity"]) != self.circuit.identity:
                raise ValueError("Checkpoint belongs to a different circuit")
            self.weight = state["weight"].copy()
            self.decoder = state["decoder"].copy()
            self.bias = state["bias"].copy()
            self.task = str(state["task"]) if "task" in state else "odor"
        circuit_task = self.circuit.metadata.get("task", "odor")
        if self.task not in {"odor", "flight", "avoidance", "vision", "terrain"} or (
            circuit_task in {"vision", "terrain"} and self.task != circuit_task
        ) or (self.task in {"vision", "terrain"} and circuit_task != self.task):
            raise ValueError("Checkpoint task and anatomical modality do not match")
        base = self.circuit.layers[2].toarray()
        if self.weight.shape != base.shape or np.any(self.weight[base == 0] != 0):
            raise ValueError("Checkpoint introduced connections outside the anatomical mask")
        ratios = self.weight[base != 0] / base[base != 0]
        if (ratios < np.exp(-1.5)-1e-5).any() or (ratios > np.exp(1.5)+1e-5).any():
            raise ValueError("Checkpoint gains are outside the training bounds")
        if not all(np.isfinite(a).all() for a in (self.weight, self.decoder, self.bias)):
            raise ValueError("Non-finite checkpoint parameters")
        if self.decoder.shape != (base.shape[1], 1) or self.bias.shape != (1,):
            raise ValueError("Invalid motor readout shape")

    def __call__(self, odor):
        if np.asarray(odor).shape != (2,):
            raise ValueError("Policy requires exactly two sensor values")
        # Live rendering, physics evaluation and portable replay use one path.
        return self.activity(odor)[0]

    def activity(self, odor):
        """Exact forward activations for instrumentation; no simulated spikes."""
        orn = self.circuit.sensory_activity(np.asarray(odor).reshape(2))[0]
        alpn = np.tanh(2 * (self.circuit.layers[0].T @ orn))
        kc = np.tanh(2 * (self.circuit.layers[1].T @ alpn))
        mbon = np.tanh(2 * (kc @ self.weight))
        turn = float(np.tanh(mbon @ self.decoder + self.bias).item())
        return turn, [orn, alpn, kc, mbon]
