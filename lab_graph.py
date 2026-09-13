"""Export model connectivity and the same verified anatomy as the local atlas."""
import hashlib
import json
from pathlib import Path
import numpy as np
from brain import neurons, context_mesh, load_neuron, CACHE, DATA
from odor_brain import Circuit, GROUPS, MODEL

ROOT = Path(__file__).resolve().parent
VERSION = 2

def prepare(*, force=False):
    target = ROOT / "artifacts/lab/graph.json"
    anatomy = target.with_name("anatomy.json")
    segments = target.with_name("anatomy.f32")
    if not force and target.exists() and anatomy.exists() and segments.exists():
        if json.loads(target.read_text()).get("version") == VERSION:
            return target
    n = neurons().set_index("bodyId")
    circuit = Circuit()
    records, offset, by_id, model_index, groups = [], 0, {}, {}, []
    with np.load(MODEL / "body_ids.npz", allow_pickle=False) as ids:
        for group in GROUPS:
            located = 0
            for i, body_id in enumerate(ids[group]):
                model_index[str(body_id)] = offset + i
                row = n.loc[body_id]
                if row.somaLocation is not None and not isinstance(row.somaLocation, float):
                    pos = (np.asarray(row.somaLocation) * .008).round(3).tolist()
                    record = dict(id=str(body_id), group=group, index=offset + i, position=pos,
                                  label=str(row.get("type") or group),
                                  region=row.somaNeuromere if isinstance(row.somaNeuromere, str) else None)
                    by_id[(group, i)] = len(records)
                    records.append(record)
                    located += 1
            groups.append(dict(name=group, start=offset, count=len(ids[group]), located=located))
            offset += len(ids[group])
    edges, layer_counts = [], []
    for level, matrix in enumerate(circuit.layers):
        coo = matrix.tocoo()
        shown = 0
        # Every existing link with two real soma locations, no strongest-260 sampling.
        for row, col, weight in zip(coo.row, coo.col, coo.data):
            a = by_id.get((GROUPS[level], int(row)))
            b = by_id.get((GROUPS[level + 1], int(col)))
            if a is not None and b is not None:
                edges.append(dict(a=a, b=b, layer=level, row=int(row), col=int(col), weight=float(weight)))
                shown += 1
        layer_counts.append(dict(total=matrix.nnz, located=shown))
    vertices, faces = context_mesh()
    target.parent.mkdir(parents=True, exist_ok=True)
    graph_record = dict(version=VERSION, circuit_identity=circuit.identity,
        nodes=records, edges=edges, vertices=vertices.round(3).ravel().tolist(), faces=faces.ravel().tolist(),
        groups=circuit.metadata["groups"], group_ranges=groups, layer_counts=layer_counts, total=offset,
        scope="True soma locations in micrometers. All located model links, drawn soma-to-soma, not axons. Missing coordinates are never invented.")
    skeletons, arrays, segment_offset = [], [], 0
    for entry in json.loads((CACHE / "selected-skeletons.json").read_text()):
        body_id = entry["bodyId"]
        neuron = load_neuron(body_id)  # Verifies original SWC checksum, uses atlas's 8 nm conversion.
        nodes = neuron.nodes.set_index("node_id")
        child = nodes[nodes.parent_id >= 0]
        parent = nodes.loc[child.parent_id]
        xyz = np.stack([child[["x", "y", "z"]].to_numpy(), parent[["x", "y", "z"]].to_numpy()], axis=1)
        arrays.append(xyz.astype("<f4"))
        skeletons.append(dict(id=str(body_id), label=entry["name"], index=model_index.get(str(body_id)),
            start=segment_offset, count=len(child), sha256=hashlib.sha256((DATA / f"{body_id}.swc").read_bytes()).hexdigest()))
        segment_offset += len(child)
    np.concatenate(arrays).tofile(segments)
    anatomy.write_text(json.dumps(dict(version=VERSION, skeletons=skeletons, segments=segment_offset,
        sha256=hashlib.sha256(segments.read_bytes()).hexdigest(), dtype="little-endian float32", unit="um",
        scope="The exact 28 local atlas skeletons; only model members receive live activation. Skeleton-wide color is a neuron response, not measured propagation."), separators=(",", ":")))
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(graph_record, separators=(",", ":"), allow_nan=False))
    temporary.replace(target)
    return target

if __name__ == "__main__":
    print(prepare())
