"""Export real soma locations and anatomical surface for the local instrument UI."""
import json
from pathlib import Path
import numpy as np
from brain import neurons, context_mesh
from odor_brain import Circuit, GROUPS, MODEL

ROOT = Path(__file__).resolve().parent

def prepare():
    target = ROOT / "artifacts/lab/graph.json"
    if target.exists():
        return target
    n = neurons().set_index("bodyId")
    circuit = Circuit()
    records, offset, by_id = [], 0, {}
    with np.load(MODEL / "body_ids.npz", allow_pickle=False) as ids:
        for group in GROUPS:
            for i, body_id in enumerate(ids[group]):
                row = n.loc[body_id]
                if row.somaLocation is not None and not isinstance(row.somaLocation, float):
                    pos = (np.asarray(row.somaLocation) * .008).round(3).tolist()
                    record = dict(id=str(body_id), group=group, index=offset + i, position=pos,
                                  label=str(row.get("type") or group))
                    by_id[(group, i)] = len(records)
                    records.append(record)
            offset += len(ids[group])
    edges = []
    for level, matrix in enumerate(circuit.layers):
        coo = matrix.tocoo()
        # Deterministic strongest anatomical links; displayed as soma-to-soma abstractions.
        for k in np.argsort(coo.data)[::-1]:
            a = by_id.get((GROUPS[level], int(coo.row[k])))
            b = by_id.get((GROUPS[level + 1], int(coo.col[k])))
            if a is not None and b is not None:
                edges.append(dict(a=a, b=b, layer=level, row=int(coo.row[k]), col=int(coo.col[k]), weight=float(coo.data[k])))
                if sum(e["layer"] == level for e in edges) >= 260:
                    break
    vertices, faces = context_mesh()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(nodes=records, edges=edges, vertices=vertices.round(3).ravel().tolist(),
        faces=faces.ravel().tolist(), groups=circuit.metadata["groups"], total=offset,
        scope="True MaleCNS soma locations, 8 nm voxel conversion; JRCFIB2022M surface in micrometers. Missing somata are not invented. Lines denote connectivity, not neurite geometry."), separators=(",", ":")))
    return target

if __name__ == "__main__":
    print(prepare())
