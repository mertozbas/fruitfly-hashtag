"""Train an explicitly simplified MaleCNS olfactory graph surrogate.

Real topology: ORN -> ALPN -> Kenyon_Cell -> MBON. Positive normalized
anatomical weights are computational features, not physiological synapses.
Learning: bounded gains on existing KC->MBON edges plus an artificial motor
readout, supervised by an odor-gradient teacher. No whole-brain emulation.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

import numpy as np
from scipy import sparse

from brain import DATA, graph, neurons

from odor_policy import ROOT, MODEL, GROUPS, Circuit, Policy


def build_circuit():
    MODEL.mkdir(parents=True, exist_ok=True)
    manifest = MODEL / "circuit.json"
    if manifest.exists():
        return json.loads(manifest.read_text())
    n = neurons()
    body_ids, adjacency = graph()
    if not np.array_equal(body_ids, n.bodyId.to_numpy()):
        raise ValueError("Annotation and adjacency ID ordering differ")
    all_orn = n["class"].eq("olfactory") & n.superclass.eq("cb_sensory")
    masks = [all_orn & n.rootSide.isin(["L", "R"])]
    masks += [n["class"].eq(name) for name in GROUPS[1:]]
    side = n.loc[masks[0], "rootSide"].eq("R").to_numpy(dtype=np.int64)
    np.savez_compressed(MODEL / "body_ids.npz", **{name: body_ids[mask] for name, mask in zip(GROUPS, masks)}, orn_side=side)
    layers = []
    for i in range(3):
        raw = adjacency[masks[i].to_numpy()][:, masks[i + 1].to_numpy()].astype(np.float32)
        incoming = np.asarray(raw.sum(axis=0)).ravel()
        normalized = (raw @ sparse.diags(1 / np.maximum(incoming, 1))).tocsr()
        path = MODEL / f"layer{i}.npz"
        sparse.save_npz(path, normalized)
        layers.append(dict(source=GROUPS[i], target=GROUPS[i + 1], shape=list(raw.shape),
                           edges=raw.nnz, anatomical_contacts=int(raw.sum()),
                           file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    source = json.loads((DATA / "manifest.json").read_text())
    source_hash = next(f["sha256"] for f in source["files"] if f["file"].startswith("connectome-weights"))
    result = dict(dataset="MaleCNS v1.0", source_connectome_sha256=source_hash,
                  groups={k: int(m.sum()) for k, m in zip(GROUPS, masks)}, layers=layers,
                  omitted_orn_unknown_root_side=int((all_orn & ~n.rootSide.isin(["L", "R"])).sum()),
                  sensory_encoder="Bilateral synthetic concentration contrast broadcast to ORNs according to rootSide; no receptor/odor identity model",
                  dynamics="Three feed-forward positive normalized graph layers with tanh activation; no physiological sign, recurrence, spikes or delays",
                  plasticity="Supervised gradient descent on bounded gains of existing KC->MBON edges and an artificial steering readout",
                  motor_adapter="Artificial MBON readout -> two CPG amplitudes; FlyGym hybrid controller provides leg motion",
                  scope="Engineering prototype on a MaleCNS-derived subgraph. Not a validated biological learning model or the full MaleCNS brain.")
    manifest.write_text(json.dumps(result, indent=2) + "\n")
    return result



def load_policy(kind="trained"):
    if kind not in ("trained", "untrained"):
        raise ValueError("Unknown checkpoint kind")
    path = MODEL / f"{kind}.npz"
    if not path.exists():
        raise FileNotFoundError("Run: rtk proxy .venv/bin/python odor_brain.py train")
    return Policy(path)


def make_examples(count, seed):
    from fly_sim import teacher
    rng = np.random.default_rng(seed)
    common = np.exp(rng.uniform(np.log(.005), np.log(.85), count))
    contrast = rng.uniform(-.08, .08, count)
    odor = np.stack([common * (1 + contrast), common * (1 - contrast)], axis=1).astype(np.float32)
    return odor, teacher(odor).astype(np.float32)


def train(*, steps=3000, seed=42, device="auto"):
    import torch
    from torch import nn
    from torch.utils.tensorboard import SummaryWriter
    torch.set_num_threads(4)
    torch.manual_seed(seed)
    circuit = Circuit()
    if (MODEL / "trained.npz").exists():
        import shutil
        from datetime import datetime, timezone
        archive = MODEL / "history" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        archive.mkdir(parents=True)
        for filename in ("untrained.npz", "trained.npz", "training.json"):
            if (MODEL / filename).exists():
                shutil.copy2(MODEL / filename, archive / filename)
    if device == "auto":
        device = "mps" if torch.backends.mps.is_available() else "cpu"
    base = torch.tensor(circuit.layers[2].toarray(), device=device)
    class Network(nn.Module):
        def __init__(self):
            super().__init__()
            self.raw_gain = nn.Parameter(torch.zeros_like(base))
            self.readout = nn.Linear(base.shape[1], 1, device=device)
            nn.init.normal_(self.readout.weight, std=.005)
            nn.init.zeros_(self.readout.bias)
        def weight(self):
            return base * torch.exp(1.5 * torch.tanh(self.raw_gain))
        def forward(self, kc):
            return torch.tanh(self.readout(torch.tanh(2 * kc @ self.weight()))).squeeze(-1)
    network = Network().to(device)
    def save(kind):
        np.savez_compressed(MODEL / f"{kind}.npz", weight=network.weight().detach().cpu().numpy(),
                            decoder=network.readout.weight.detach().cpu().numpy().T,
                            bias=network.readout.bias.detach().cpu().numpy(),
                            circuit_identity=circuit.identity, seed=seed)
    save("untrained")
    train_x, train_y = make_examples(2048, seed)
    test_x, test_y = make_examples(512, seed + 1000)
    x = torch.tensor(circuit.kc_features(train_x), device=device)
    y = torch.tensor(train_y, device=device)
    tx = torch.tensor(circuit.kc_features(test_x), device=device)
    ty = torch.tensor(test_y, device=device)
    with torch.no_grad():
        before = float(torch.mean((network(tx) - ty)**2).cpu())
    optimizer = torch.optim.Adam(network.parameters(), lr=.008)
    writer = SummaryWriter(str(MODEL / "tensorboard" / f"seed-{seed}"))
    rng = np.random.default_rng(seed)
    started = time.monotonic()
    print(f"Training {int((base != 0).sum().cpu()):,} existing KC->MBON gains + motor readout on {device}; baseline MSE={before:.5f}", flush=True)
    history = []
    for step in range(steps):
        batch = torch.tensor(rng.integers(0, len(x), 256), device=device)
        pred = network(x[batch])
        loss = torch.mean((pred - y[batch])**2)
        optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(network.parameters(), 5)
        optimizer.step()
        if step % 200 == 0 or step == steps - 1:
            with torch.no_grad():
                mse = float(torch.mean((network(tx) - ty)**2).cpu())
            history.append(dict(step=step + 1, validation_mse=mse))
            writer.add_scalar("validation/mse", mse, step + 1)
            print(f"step {step + 1}/{steps}: validation MSE={mse:.6f}", flush=True)
    with torch.no_grad():
        prediction = network(tx).cpu().numpy()
        final_weight = network.weight().cpu().numpy()
    after = float(np.mean((prediction - test_y)**2))
    save("trained")
    writer.close()
    original_weight = circuit.layers[2].toarray()
    changed = int(np.count_nonzero((original_weight != 0) & (np.abs(final_weight - original_weight) > 1e-7)))
    result = dict(seed=seed, device=device, steps=steps, elapsed_wall_seconds=time.monotonic() - started,
                  training_examples=len(x), heldout_examples=len(tx), before_mse=before, after_mse=after,
                  heldout_direction_accuracy=float(np.mean(np.sign(prediction) == np.sign(test_y))),
                  changed_existing_synaptic_gains=changed, newly_created_anatomical_edges=int(np.count_nonzero(final_weight[original_weight == 0])),
                  training_kind="Supervised imitation of synthetic odor-gradient labels, not biological reward learning",
                  scope=circuit.metadata["scope"], history=history)
    (MODEL / "training.json").write_text(json.dumps(result, indent=2) + "\n")
    if after >= before or changed == 0:
        raise RuntimeError("Training did not improve held-out error or change any anatomical edge gains")
    # Round-trip check uses the actual checkpoint replay path.
    replay = load_policy("trained")
    for i in range(3):
        if not np.isclose(replay(test_x[i]), prediction[i], atol=1e-4):
            raise ValueError("Checkpoint replay mismatch")
    print(json.dumps({k: v for k, v in result.items() if k != "history"}, indent=2), flush=True)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["prepare", "train"])
    p.add_argument("--steps", type=int, default=3000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--device", choices=["auto", "cpu", "mps"], default="auto")
    args = p.parse_args()
    if not 1 <= args.steps <= 10000:
        p.error("steps must be between 1 and 10000")
    if args.command == "prepare":
        print(json.dumps(build_circuit(), indent=2))
    else:
        train(steps=args.steps, seed=args.seed, device=args.device)


if __name__ == "__main__":
    main()
