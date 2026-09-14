"""Deterministic, bounded anatomical subgraphs for two additional modalities.

These are synthetic rate models, not identified biological behavioral circuits.
Only directed MaleCNS contacts are retained. Pruning is computational, not a
claim that the selected paths are the fly's visual or climbing mechanism.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy import sparse

from odor_policy import ROOT


def circuit_directory(task):
    if task not in {"avoidance", "vision", "terrain"}:
        return ROOT / "models/odor_navigation"
    return ROOT / "models" / f"{task}_navigation"


def build(task):
    directory = circuit_directory(task)
    manifest = directory / "circuit.json"
    if manifest.exists():
        return directory
    if task == "avoidance":
        import shutil
        directory.mkdir(parents=True, exist_ok=True)
        for filename in ("circuit.json", "body_ids.npz", "layer0.npz", "layer1.npz", "layer2.npz"):
            shutil.copy2(circuit_directory("odor") / filename, directory / filename)
        return directory
    if task not in {"vision", "terrain"}:
        raise ValueError("Build the original odor circuit first")
    from brain import neurons, graph, CACHE
    n = neurons()
    ids, adjacency = graph()
    if not np.array_equal(ids, n.index):
        raise ValueError("Annotation / graph order mismatch")
    indices = lambda mask: np.flatnonzero(mask.to_numpy())
    def block(a, b):
        return adjacency[a][:, b]
    def strongest(candidates, score, limit):
        # Stable ID ordering resolves ties reproducibly.
        order = np.argsort(-np.asarray(score).ravel(), kind="stable")
        return np.sort(candidates[order[:limit]])
    if task == "vision":
        groups = ("Photoreceptor", "Optic_relay", "Visual_projection", "Descending")
        sensory = indices(n["class"].eq("visual") & n.rootSide.isin(["L", "R"]))
        h1 = indices(n.superclass.eq("ol_intrinsic"))
        h2 = indices(n.superclass.eq("visual_projection"))
        output = indices(n.superclass.eq("descending_neuron"))
        score = np.sqrt(np.asarray(block(sensory, h1).sum(0)).ravel() *
                        np.asarray(block(h1, h2).sum(1)).ravel())
        h1 = strongest(h1, score, 768)
        score = np.sqrt(np.asarray(block(h1, h2).sum(0)).ravel() *
                        np.asarray(block(h2, output).sum(1)).ravel())
        h2 = strongest(h2, score, 512)
        encoding = "bilateral_contrast"
        sensor = "RGB eye cameras -> red target pixel salience per eye -> side-pooled photoreceptor drive; no retinotopy or receptor model"
        motor = "Artificial descending-layer readout -> signed CPG steering"
    else:
        groups = ("Touch", "VNC_relay", "VNC_premotor", "Motor")
        sensory = indices(n["class"].eq("mechanosensory_tactile") &
                          n.superclass.eq("vnc_sensory") & n.rootSide.isin(["L", "R"]) &
                          n.entryNerve.isin(["ProLN", "MesoLN", "MetaLN"]))
        interneurons = indices(n.superclass.eq("vnc_intrinsic"))
        output = indices(n.superclass.eq("vnc_motor"))
        h2 = strongest(interneurons, block(interneurons, output).sum(1), 512)
        h1 = np.setdiff1d(interneurons, h2)
        score = np.sqrt(np.asarray(block(sensory, h1).sum(0)).ravel() *
                        np.asarray(block(h1, h2).sum(1)).ravel())
        h1 = strongest(h1, score, 512)
        encoding = "bilateral_intensity"
        sensor = "Per-side opposing leg contact forces from MuJoCo, normalized and decayed over 100 ms; pooled tactile drive, not receptor physiology"
        motor = "Artificial motor-layer readout -> gain of the existing FlyGym retraction/stumbling correction; CPG remains fixed"
    selected = [sensory, h1, h2, output]
    # Every retained node lies on a complete input-to-output directed path.
    for _ in range(4):
        for i in range(1, 4):
            selected[i] = selected[i][block(selected[i-1], selected[i]).getnnz(0) > 0]
        for i in range(2, -1, -1):
            selected[i] = selected[i][block(selected[i], selected[i+1]).getnnz(1) > 0]
    if any(len(x) == 0 for x in selected):
        raise ValueError("No complete sensory-to-output path")
    directory.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(directory / "body_ids.npz",
        **{g: ids[ix] for g, ix in zip(groups, selected)},
        orn_side=n.iloc[selected[0]].rootSide.eq("R").to_numpy(np.int64))
    layers = []
    for i, (a, b) in enumerate(zip(selected, selected[1:])):
        raw = block(a, b).astype(np.float32)
        sums = np.asarray(raw.sum(0)).ravel()
        matrix = (raw @ sparse.diags(1 / np.maximum(sums, 1))).tocsr()
        path = directory / f"layer{i}.npz"
        sparse.save_npz(path, matrix)
        layers.append(dict(file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                           edges=matrix.nnz, contacts=int(raw.sum()), shape=list(matrix.shape)))
    record = dict(version=1, task=task, dataset="male-cns:v1.0", group_order=list(groups),
        groups={g:len(ix) for g, ix in zip(groups, selected)}, layers=layers,
        body_ids_sha256=hashlib.sha256((directory / "body_ids.npz").read_bytes()).hexdigest(),
        input_encoding=encoding, sensor_adapter=sensor, motor_adapter=motor,
        selection="Class-filtered directed paths, deterministic contact-count ranking, disjoint layers, iterative path pruning",
        graph_sha256=hashlib.sha256((CACHE / "graph.json").read_bytes()).hexdigest(),
        scope="Anatomical IDs and unsigned contacts are real data. Dynamics, pooling, gains and motor decoding are artificial. No spikes, recurrent dynamics, physiological signs or validated biological behavior.")
    manifest.write_text(json.dumps(record, indent=2) + "\n")
    return directory


def initialize(task):
    """Create an explicit untrained model for a newly selected task."""
    from odor_policy import Circuit
    directory = build(task)
    path = directory / "untrained.npz"
    if not path.exists():
        circuit = Circuit(directory)
        base = circuit.layers[2].toarray()
        rng = np.random.default_rng(42)
        np.savez_compressed(path, weight=base,
            decoder=rng.normal(0, .005, (base.shape[1], 1)).astype(np.float32),
            bias=np.zeros(1, dtype=np.float32), task=task, seed=42, circuit_identity=circuit.identity)
    return path
