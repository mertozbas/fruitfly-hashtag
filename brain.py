"""Local MaleCNS v1.0 queries and geometry, with no neuPrint account required."""

from functools import lru_cache
from pathlib import Path
import base64
import hashlib
import json
import time

import google_crc32c
import numpy as np
import pandas as pd
import pyarrow.feather as feather
import requests
from scipy import sparse

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "male-cns-v1.0"
CACHE = DATA / "derived"
ARTIFACTS = ROOT / "artifacts"
SWC_BASE = "https://storage.googleapis.com/flyem-male-cns/v1.0/segmentation/skeletons-malecns/skeletons-swc"
FILTER_RULE = "annotation.superclass.notna(); both edge endpoints in this set"


@lru_cache(maxsize=1)
def annotations():
    """All 211,577 annotated bodies; not all bodies are identified neurons."""
    return feather.read_feather(DATA / "body-annotations-male-cns-v1.0-minconf-0.5.feather").set_index("bodyId", drop=False)


@lru_cache(maxsize=1)
def neurons():
    """Exploratory 166,700-body subset, NOT a reproduction of the paper census."""
    a = annotations()
    n = a[a.superclass.notna()].sort_index().copy()
    nt = feather.read_feather(DATA / "body-neurotransmitters-male-cns-v1.0.feather").set_index("body")
    return n.join(nt[["consensus_nt", "predicted_nt_confidence"]])


def find_neurons(query, limit=30):
    """Literal substring search by ID, type or instance. No regex interpretation."""
    n = neurons()
    cols = ["bodyId", "type", "instance", "superclass", "class", "consensus_nt"]
    mask = pd.Series(False, index=n.index)
    for col in ("bodyId", "type", "instance"):
        mask |= n[col].astype("string").str.contains(str(query), case=False, regex=False, na=False)
    return n.loc[mask, cols].head(limit)


def build_graph():
    """Build an integer synapse-count CSR: row=presynaptic, column=postsynaptic."""
    CACHE.mkdir(parents=True, exist_ok=True)
    if all((CACHE / f).exists() for f in ("adjacency.npz", "body_ids.npy", "graph.json")):
        return json.loads((CACHE / "graph.json").read_text())
    ids = neurons().index.to_numpy(dtype=np.int64)
    index = pd.Index(ids)
    rows, cols, weights = [], [], []
    table = feather.read_table(DATA / "connectome-weights-male-cns-v1.0-minconf-0.5.feather", memory_map=True)
    raw_rows = table.num_rows
    for batch in table.to_batches(max_chunksize=1_000_000):
        pre = index.get_indexer(batch.column(0).to_numpy())
        post = index.get_indexer(batch.column(1).to_numpy())
        keep = (pre >= 0) & (post >= 0)
        rows.append(pre[keep].astype(np.int32))
        cols.append(post[keep].astype(np.int32))
        weights.append(batch.column(2).to_numpy()[keep].astype(np.int64))
    del table
    row, col, weight = map(np.concatenate, (rows, cols, weights))
    matrix = sparse.csr_matrix((weight, (row, col)), shape=(len(ids), len(ids)), dtype=np.int64)
    matrix.sort_indices()
    stats = dict(dataset="male-cns:v1.0", filter=FILTER_RULE, nodes=len(ids),
                 raw_rows=raw_rows, retained_rows=len(weight), edges=matrix.nnz,
                 synaptic_contacts=int(matrix.sum()), orientation="row=pre, column=post",
                 weights="unsigned anatomical contact counts; no physiological sign or learned parameters")
    # Expected counts for the version-pinned public sources; a fresh installation
    # must not depend on a private validation artifact from the author's machine.
    expected = dict(nodes=166700, edges=25582938, synaptic_contacts=124177617)
    for key in ("nodes", "edges", "synaptic_contacts"):
        if stats[key] != expected[key]:
            raise ValueError(f"Graph validation mismatch: {key}")
    sparse.save_npz(CACHE / "adjacency.npz", matrix)
    np.save(CACHE / "body_ids.npy", ids, allow_pickle=False)
    (CACHE / "graph.json").write_text(json.dumps(stats, indent=2) + "\n")
    return stats


@lru_cache(maxsize=1)
def graph():
    if not (CACHE / "graph.json").exists():
        build_graph()
    return np.load(CACHE / "body_ids.npy", allow_pickle=False), sparse.load_npz(CACHE / "adjacency.npz")


@lru_cache(maxsize=1)
def incoming_graph():
    return graph()[1].tocsc()


def partners(body_id, direction="out", limit=20):
    """Rank partners within the exploratory subset by anatomical contact count."""
    if direction not in ("in", "out"):
        raise ValueError("direction must be 'in' or 'out'")
    ids, matrix = graph()
    pos = np.searchsorted(ids, int(body_id))
    if pos >= len(ids) or ids[pos] != int(body_id):
        raise KeyError(f"Body {body_id} is outside the exploratory subset")
    m = matrix if direction == "out" else incoming_graph()
    start, end = m.indptr[pos:pos + 2]
    result = neurons().loc[ids[m.indices[start:end]], ["bodyId", "type", "instance", "superclass", "consensus_nt"]].copy()
    result["synaptic_contacts"] = m.data[start:end]
    return result.sort_values("synaptic_contacts", ascending=False, kind="stable").head(limit)


def ensure_skeleton(body_id):
    """Download one official SWC, generation-pin it and verify its server CRC32C."""
    body_id = int(body_id)
    if body_id not in annotations().index:
        raise KeyError(f"Unknown annotated body: {body_id}")
    path = DATA / f"{body_id}.swc"
    record_path = DATA / "skeleton-manifests" / f"{body_id}.json"
    if path.exists():
        original = json.loads((DATA / "manifest.json").read_text())["files"]
        record = json.loads(record_path.read_text()) if record_path.exists() else next((r for r in original if r["file"] == path.name), None)
        if record and hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]:
            return path
        raise ValueError(f"Unverified cached SWC: {path.name}")
    record_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"{SWC_BASE}/{body_id}.swc"
    for attempt in range(3):
        try:
            head = requests.head(url, timeout=(10, 30))
            head.raise_for_status()
            generation = head.headers["x-goog-generation"]
            pinned = f"{url}?generation={generation}"
            response = requests.get(pinned, timeout=(10, 60))
            response.raise_for_status()
            content = response.content
            expected = next(v.split("=", 1)[1] for v in response.headers["x-goog-hash"].split(",") if v.strip().startswith("crc32c="))
            actual = base64.b64encode(google_crc32c.Checksum(content).digest()).decode()
            if actual != expected:
                raise ValueError(f"CRC32C mismatch for {body_id}")
            tmp = path.with_suffix(".swc.part")
            tmp.write_bytes(content)
            tmp.replace(path)
            record = dict(file=path.name, url=url, download_url=pinned, generation=generation,
                          bytes_downloaded=len(content), sha256=hashlib.sha256(content).hexdigest(),
                          crc32c_verified=True, coordinate_unit="8 nm")
            record_path.write_text(json.dumps(record, indent=2) + "\n")
            return path
        except (requests.RequestException, ValueError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def load_neuron(body_id):
    """Read a real skeleton and convert 8 nm coordinates to micrometers."""
    import navis
    n = navis.read_swc(str(ensure_skeleton(body_id)))
    n.nodes[["x", "y", "z", "radius"]] *= 0.008
    n.units = "um"
    n.id = int(body_id)
    row = annotations().loc[int(body_id)]
    n.name = str(row["instance"] if pd.notna(row["instance"]) else body_id)
    return n


def plot_neurons(body_ids, context=True):
    """Interactive Plotly skeletons; geometry only, not neural activity."""
    import plotly.graph_objects as go
    from plotly.colors import qualitative
    fig = go.Figure()
    if context:
        vertices, faces = context_mesh()
        fig.add_trace(go.Mesh3d(x=vertices[:, 0], y=vertices[:, 1], z=vertices[:, 2],
                               i=faces[:, 0], j=faces[:, 1], k=faces[:, 2], color="#b9c8da",
                               opacity=0.07, name="CNS yüzeyi", hoverinfo="skip", showlegend=True))
    for i, body_id in enumerate(body_ids):
        n = load_neuron(body_id)
        nodes = n.nodes.set_index("node_id")
        child = nodes[nodes.parent_id >= 0]
        parent = nodes.loc[child.parent_id]
        xyz = np.full((len(child), 3, 3), np.nan, dtype=np.float32)
        xyz[:, 0] = child[["x", "y", "z"]].to_numpy()
        xyz[:, 1] = parent[["x", "y", "z"]].to_numpy()
        xyz = xyz.reshape(-1, 3)
        fig.add_trace(go.Scatter3d(x=xyz[:, 0], y=xyz[:, 1], z=xyz[:, 2], mode="lines",
                                  line=dict(width=2, color=qualitative.Light24[i % 24]),
                                  name=f"{n.name[:32]} · {body_id}", hovertemplate=f"{n.name}<br>ID {body_id}<extra></extra>"))
    style_3d(fig)
    if not context:
        fig.update_layout(scene_camera_eye=dict(x=0.1, y=-3.1, z=0.15))
    return fig


def context_mesh():
    """flybrains JRCFIB2022M is in nanometers; return micrometers."""
    import flybrains
    mesh = flybrains.JRCFIB2022M.mesh
    return (np.asarray(mesh.vertices) * 0.001).astype(np.float32), np.asarray(mesh.faces)


def style_3d(fig):
    fig.update_layout(template="plotly_dark", paper_bgcolor="#101722", plot_bgcolor="#101722",
                      margin=dict(l=0, r=0, t=20, b=0), height=780,
                      legend=dict(font=dict(size=11), itemsizing="constant",
                                  x=0.99, xanchor="right", y=1, yanchor="top"),
                      scene=dict(aspectmode="data", bgcolor="#101722",
                                 xaxis=dict(title="x (µm)", visible=False),
                                 yaxis=dict(title="y (µm)", visible=False),
                                 zaxis=dict(title="z (µm)", visible=False, autorange="reversed"),
                                 camera=dict(eye=dict(x=0.1, y=-2.2, z=0.15), up=dict(x=0, y=0, z=1))))
    return fig
