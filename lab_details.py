"""Read-only, source-backed neuron and connection inspection for Neural Lab."""
from functools import lru_cache
import json
import threading
import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.feather as feather
from brain import DATA, neurons, graph, incoming_graph
from odor_brain import Circuit, GROUPS, MODEL

_lock = threading.RLock()

def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k,v in value.items()}
    if isinstance(value, (np.ndarray, list, tuple)):
        return [clean(v) for v in value]
    if value is None or value is pd.NA:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value

@lru_cache(maxsize=16)
def circuit_index(directory=MODEL):
    result, offset = {}, 0
    with np.load(directory / "body_ids.npz", allow_pickle=False) as ids:
        for level, group in enumerate(circuit(directory).groups):
            for index, body in enumerate(ids[group]):
                result[int(body)] = dict(group=group, level=level, layer_index=index, activity_index=offset+index)
            offset += len(ids[group])
    return result

@lru_cache(maxsize=1)
def nt_table():
    return feather.read_table(DATA / "body-neurotransmitters-male-cns-v1.0.feather", memory_map=True)

@lru_cache(maxsize=16)
def circuit(directory=MODEL):
    return Circuit(directory)

def body_position(body_id):
    ids, matrix = graph()
    i = int(np.searchsorted(ids, body_id))
    if i >= len(ids) or int(ids[i]) != body_id:
        raise KeyError("Nöron yerel veri kümesinde bulunamadı")
    return i

def identity(body_id, directory=MODEL):
    n = neurons()
    if body_id not in n.index:
        raise KeyError("Nöron yerel veri kümesinde bulunamadı")
    row = n.loc[body_id]
    return clean(dict(id=str(body_id), type=row["type"], instance=row.instance,
                     cell_class=row["class"], neurotransmitter=row.consensus_nt,
                     circuit=circuit_index(directory).get(body_id)))

@lru_cache(maxsize=128)
def neuron(body_id, directory=MODEL):
    with _lock:
        i = body_position(body_id)
        ids, outgoing = graph()
        incoming = incoming_graph()
        a,b = outgoing.indptr[i:i+2]
        c,d = incoming.indptr[i:i+2]
        row = neurons().loc[body_id]
        soma = row.somaLocation
        nt = nt_table().filter(pc.equal(nt_table()["body"], body_id)).to_pylist()
        return clean(dict(**identity(body_id, directory), annotations=row.to_dict(), neurotransmitter_predictions=nt,
            soma_um=None if soma is None or isinstance(soma,float) else np.asarray(soma)*.008,
            connectivity=dict(incoming_partners=int(d-c),outgoing_partners=int(b-a),
                              incoming_contacts=int(incoming.data[c:d].sum()),outgoing_contacts=int(outgoing.data[a:b].sum())),
            dataset="MaleCNS v1.0", connectivity_scope="166,700-neuron local superclass-filtered graph; unsigned anatomical contact counts",
            source_files=["body-annotations-male-cns-v1.0-minconf-0.5.feather", "body-neurotransmitters-male-cns-v1.0.feather", "connectome-weights-male-cns-v1.0-minconf-0.5.feather"]))

def connections(body_id, direction, page=0, limit=12, directory=MODEL):
    with _lock:
        i = body_position(body_id)
        ids, out = graph()
        matrix = out if direction == "out" else incoming_graph()
        a,b = matrix.indptr[i:i+2]
        values = matrix.data[a:b]
        order = np.argsort(-values, kind="stable")[page*limit:(page+1)*limit]
        rows = []
        for j in order:
            other = int(ids[matrix.indices[a+j]])
            rows.append(dict(**identity(other, directory), contacts=int(values[j]),
                             source=str(body_id if direction=="out" else other),
                             target=str(other if direction=="out" else body_id)))
        return dict(total=int(b-a), page=page, limit=limit, direction=direction, rows=rows)

def connection(source, target, model_path):
    with _lock:
        directory = model_path.parent if model_path is not None else MODEL
        i,j = body_position(source),body_position(target)
        contacts = int(graph()[1][i,j])
        if contacts == 0:
            raise KeyError("Bu yönde anatomik bağlantı yok")
        a,b = circuit_index(directory).get(source),circuit_index(directory).get(target)
        model = None
        if model_path is not None and a and b and a["level"] + 1 == b["level"]:
            level, row, col = a["level"], a["layer_index"], b["layer_index"]
            base = float(circuit(directory).layers[level][row,col])
            if base:
                with np.load(model_path,allow_pickle=False) as saved:
                    key='weight' if level==2 else f'weight{level}'
                    trainable=key in saved
                    trained = float(saved[key][row,col]) if trainable else base
                    total=float(saved[key][:,col].sum()) if trainable else float(circuit(directory).layers[level][:,col].sum())
                response_gains=circuit(directory).metadata.get('response_gains')
                model = dict(layer=f"{a['group']} → {b['group']}", base_weight=base, current_weight=trained,
                             gain=trained/base, change_percent=(trained/base-1)*100, trainable=trainable,
                             response_gain=response_gains[level] if response_gains else 2,
                             input_weight_sum=total if response_gains else 1,
                             response='sigmoid' if response_gains else 'tanh')
        return dict(source=identity(source, directory),target=identity(target, directory),anatomical_contacts=contacts,
                    model=model, dataset="MaleCNS v1.0", sign="Unknown in this model; contact counts are unsigned",
                    geometry="The displayed line connects somata and is not reconstructed axon geometry")
