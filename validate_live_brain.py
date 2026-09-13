"""Read-only validation of live neural instrumentation against local model math."""
import hashlib
import json
from pathlib import Path
import urllib.request
import numpy as np
from brain import CACHE, DATA, load_neuron
from odor_brain import Circuit, Policy

ROOT = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8766/api/"

def get(path):
    with urllib.request.urlopen(URL + path, timeout=30) as response:
        return json.load(response)

def validate():
    checks = []
    def check(name, value):
        assert value, name
        checks.append(name)
    g = get("graph")
    s = get("state")["simulation"]
    m = get("model/" + s["model"])
    circuit = Circuit()
    path = ROOT / "models/odor_navigation" / f"{s['model']}.npz" if s["model"] in {"trained", "untrained"} else ROOT / "models/lab_runs" / s["model"] / "trained.npz"
    policy = Policy(path)
    check("Checkpoint and circuit identity match live frame", m["sha256"] == s["model_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest() and g["circuit_identity"] == m["circuit_identity"] == s["circuit_identity"] == circuit.identity)
    check("Geometry schema and weight vector agree", g["version"] == m["graph_version"] and len(m["gains"]) == len(g["edges"]))
    turn, layers = policy.activity(s["odor"])
    activity = np.concatenate(layers)
    # Frames round responses to 5 decimals; the two runtimes also use different
    # NumPy/BLAS versions for FP32 reductions. Keep an explicit small error bound.
    check("Every live node response equals forward calculation within frame precision", len(activity) == 7075 and np.allclose(s["activity"], activity, atol=6e-6, rtol=0))
    check("Steering and layer summaries match independent FP32 replay", abs(turn-s["steering"]) < 1e-5 and np.allclose(s["layer_means"], [x.mean() for x in layers],atol=1e-6))
    if s['neural'].get('brain_connected'):
        n=s['neural']
        check('Flight brain decision is sampled within the last 10 ms', -.000001 <= s['time_s']-n['sample_time_s'] <= n['brain_dt']+.000001)
        sensors=np.array(n['sensor_positions_mm']);target=np.r_[s['goal_mm'],10.]
        expected_odor=(1/(1+(np.linalg.norm(sensors-target,axis=1)/5)**2)).astype(np.float32)
        check('Synthetic odor comes from recorded physical antenna positions', np.allclose(expected_odor,s['odor'],atol=1e-7))
        neutral=policy.activity([.1,.1])[0]
        applied=np.clip(turn-neutral,-1,1)
        check('Brain readout is the bounded command used by flight adapter', n['applied_to_physics'] and abs(applied-n['applied_steering'])<1e-5 and abs(n['yaw_rate_rad_s']-np.clip(n['yaw_gain']*applied,-8,8))<1e-3)
        check('Published motor command exactly matches the applied in-process readout', abs(n['applied_steering']-np.clip(n['raw_steering']-n['neutral_steering'],-1,1))<1e-12 and abs(n['yaw_rate_rad_s']-np.clip(n['yaw_gain']*n['applied_steering'],-8,8))<1e-12)
        check('Wing motor policy action is finite and separately identified', len(n['motor_action'])>0 and np.isfinite(n['motor_action']).all() and n['motor_model_sha256']!=s['model_sha256'])
    else:
        check("Body and neural sample timestamps agree", s["time_s"] == s["neural"]["sample_time_s"])
    check("Full HD body renderer preserved", s["render"]["width"] == 1920 and s["render"]["height"] == 1080 and s["render"]["mesh_faces"] >= 447417)
    nodes = g["nodes"]
    edges = g["edges"]
    groups = g["group_ranges"]
    present = {n["index"] for n in nodes}
    counts = []
    for level, matrix in enumerate(circuit.layers):
        coo = matrix.tocoo()
        counts.append(sum(int(r)+groups[level]["start"] in present and int(c)+groups[level+1]["start"] in present for r,c in zip(coo.row,coo.col)))
    check("All model edges with two known coordinates exported", counts == [x["located"] for x in g["layer_counts"]] and sum(counts) == len(edges) == 82747)
    check("Absent somata not fabricated", len(nodes) == 4826 and len(present) == 4826 and groups[0]["located"] == 0)
    with np.load(ROOT / "models/odor_navigation/body_ids.npz", allow_pickle=False) as ids:
        check("Node indices map to original body ids", all(str(ids[n["group"]][n["index"]-next(x["start"] for x in groups if x["name"]==n["group"])]) == n["id"] for n in nodes))
    max_weight_error, max_contribution_error = 0., 0.
    for e, gain in zip(edges,m["gains"]):
        level,row,col = e["layer"],e["row"],e["col"]
        base = float(circuit.layers[level][row,col])
        weight = float(policy.weight[row,col]) if level == 2 else base
        max_weight_error = max(max_weight_error,abs(e["weight"]*gain-weight))
        contribution = 2*activity[nodes[e["a"]]["index"]]*e["weight"]*gain
        expected = 2*layers[level][row]*weight
        max_contribution_error = max(max_contribution_error,abs(contribution-expected))
    check("All displayed learned weights and edge contributions exact", max_weight_error < 1e-7 and max_contribution_error < 1e-7)
    check("No new anatomical edges in learned model", np.count_nonzero(policy.weight) == circuit.layers[2].nnz)
    base_model = get("model/untrained")
    check("Training-before comparison uses unit anatomical gains", np.allclose(base_model["gains"],1))
    changed = sum(e["layer"] == 2 and abs(gain-1)>.01 for e,gain in zip(edges,m["gains"]))
    a = get("anatomy")
    original = json.loads((CACHE / "selected-skeletons.json").read_text())
    check("Same 28 skeleton identities as reference atlas", [x["id"] for x in a["skeletons"]] == [str(x["bodyId"]) for x in original])
    with urllib.request.urlopen(URL+"anatomy/segments",timeout=30) as response:
        binary = response.read()
    check("Anatomical binary integrity", hashlib.sha256(binary).hexdigest() == a["sha256"] and len(binary) == a["segments"]*24)
    xyz = np.frombuffer(binary,dtype="<f4").reshape(-1,2,3)
    for skeleton in a["skeletons"]:
        neuron = load_neuron(int(skeleton["id"]))
        swc = neuron.nodes.set_index("node_id")
        child = swc[swc.parent_id >= 0]
        expected = np.stack([child[["x","y","z"]].to_numpy(),swc.loc[child.parent_id][["x","y","z"]].to_numpy()],axis=1)
        assert np.array_equal(xyz[skeleton["start"]:skeleton["start"]+skeleton["count"]],expected.astype(np.float32)), skeleton["id"]
        assert hashlib.sha256((DATA / f"{skeleton['id']}.swc").read_bytes()).hexdigest() == skeleton["sha256"]
    check("Every SWC segment equals reference geometry in micrometers", True)
    check("Only three atlas skeletons carry model activation", sum(x["index"] is not None for x in a["skeletons"]) == 3)
    drive = s["neural"]["cpg_drive"]
    if drive is not None:
        last_turn = s["neural"]["applied_steering"]
        check("CPG display reports last applied steering mapping", np.allclose(drive,[.9-.55*last_turn,.9+.55*last_turn]))
    result = dict(checks=checks,model=s["model"],sha256=m["sha256"],seq=s["seq"],neurons=len(activity),located=len(nodes),edges=len(edges),changed_located_gains_over_one_percent=changed,
                  max_weight_error=float(max_weight_error),max_contribution_error=float(max_contribution_error),browser_visual_test=False)
    name='flight/live-brain-validation.json' if s['neural'].get('brain_connected') else 'live-brain-validation.json'
    (ROOT / "artifacts/lab" / name).write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__ == "__main__":
    validate()
