"""Export a minimal, privacy-filtered snapshot from the original research workspace.

This optional maintainer utility needs unpublished source records. Readers can
verify the committed snapshot with verify_evidence.py without these records.
It never connects to hardware or loads a model. The output directory must be new.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def export(source: Path, destination: Path, validation_record: Path | None = None) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    inputs: list[dict] = []

    def read(relative: str, public_path: str | None = None) -> dict:
        data = (source / relative).read_bytes()
        inputs.append({"source_path": public_path or relative,
                       "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                       "distributed": False})
        return json.loads(data)

    def write_json(name: str, data: dict) -> None:
        (destination / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def write_csv(name: str, rows: list[dict]) -> None:
        with (destination / name).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    ttt = "models/lab_runs/local-tictactoe-robot-seed53/"
    strategy = read(ttt + "evaluation.json")
    training = read(ttt + "training.json")
    circuit = read(ttt + "circuit.json")
    motor = read(ttt + "motor-evaluation.json")
    state = read("models/lab_runs/local-so101-validated-seed42/evaluation.json")
    wrist = read("models/lab_runs/local-so101-uvc-recovery-seed49/evaluation.json")
    physical = read("reports/so101-connectome-2026-09-16/metrics.json")
    original_manifest = read("reports/so101-connectome-2026-09-16/evidence-manifest.json")
    for relative, metadata in original_manifest.items():
        assert hashlib.sha256((source / relative).read_bytes()).hexdigest() == metadata["sha256"], relative

    episodes = []
    conditions = [("state_trained", state)]
    conditions += [("state_" + key, value) for key, value in state["controls"].items()]
    conditions += [("wrist_trained", wrist), ("wrist_release_after_lift", wrist["recovery_evaluation"])]
    conditions += [("wrist_" + ("previous_trained" if key == "untrained" else key), value)
                   for key, value in wrist["controls"].items()]
    conditions += [("wrist_" + key, value) for key, value in wrist["extended_evaluations"].items()]
    aggregate = []
    for condition, evaluation in conditions:
        rows = evaluation["results"]
        assert len(rows) == evaluation["episodes"]
        assert sum(row["success"] for row in rows) == evaluation["success_count"]
        aggregate.append({"condition": condition, "episodes": len(rows),
                          "successes": evaluation["success_count"],
                          "unsafe_count": evaluation["unsafe_count"],
                          "checkpoint_sha256": evaluation["checkpoint_sha256"]})
        for row in rows:
            episodes.append({"condition": condition, **{key: row[key] for key in
                ["seed", "success", "outcome", "unsafe", "steps", "physics_warnings"]}})
    write_csv("so101-episodes.csv", episodes)

    motor_rows = []
    for condition, rows in [("single_destination", motor["rows"]),
                            ("sequential_game", motor["games"][0]["moves"]),
                            ("silenced", [motor["silenced"]])]:
        for index, row in enumerate(rows):
            motor_rows.append({"condition": condition, "trial": index + 1,
                               **{key: row[key] for key in ["cell", "success", "outcome", "seconds", "attempts"]}})
    write_csv("tictactoe-motor.csv", motor_rows)

    run_rows, motion_rows = [], []
    records_by_session = {}
    source_by_session = {}
    for index, summary in enumerate(physical["neural_runs"], 1):
        session = summary["session"]
        if session not in records_by_session:
            relative = f".runtime/hardware/neural/{session}/decisions.jsonl"
            data = (source / relative).read_bytes()
            source_id = f"physical-session-{len(records_by_session) + 1}"
            inputs.append({"source_id": source_id,
                           "source_path": ".runtime/hardware/neural/<private-session>/decisions.jsonl",
                           "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                           "distributed": False})
            records_by_session[session] = [json.loads(line) for line in data.splitlines() if line.strip()]
            source_by_session[session] = source_id
        records = records_by_session[session]
        cuts = [0] + [i for i in range(1, len(records)) if records[i]["time"] - records[i-1]["time"] > 1] + [len(records)]
        start, stop = cuts[summary["segment"] - 1:summary["segment"] + 1]
        segment = records[start:stop]
        assert len(segment) == summary["samples"]
        run_id = f"R{index}"
        run_rows.append({"run_id": run_id, "source_id": source_by_session[session],
                         "source_segment": summary["segment"],
                         **{key: summary[key] for key in ["samples", "logged_span_seconds", "command_rows",
                           "measured_delta_counts", "measured_delta_degrees", "unique_camera_frames"]},
                         "drive_min": summary["drive_range"][0], "drive_max": summary["drive_range"][1]})
        for row in segment:
            motion_rows.append({"run_id": run_id, "elapsed_seconds": row["time"] - segment[0]["time"],
                "base_displacement_counts": row["q"][0] - segment[0]["q"][0],
                "goal_displacement_counts": row["goal"] - segment[0]["q"][0],
                "neural_command": row["neural_command"], "drive": row["decision"]["drive"]})
    write_csv("physical-runs.csv", run_rows)
    write_csv("physical-motion.csv", motion_rows)

    results = {
        "schema_version": 1, "publication_date": "2026-09-26",
        "scope": "Retrospective recorded results; no new training, simulation rollouts or hardware trials during export.",
        "tictactoe": {
            "circuit": {"dataset": circuit["dataset"], "groups": circuit["groups"],
                        "neurons": sum(circuit["groups"].values()),
                        "edges": sum(layer["edges"] for layer in circuit["layers"]),
                        "graph_sha256": circuit["graph_sha256"]},
            "strategy": {key: strategy[key] for key in ["reachable_decision_boards", "optimal_decisions",
                "optimal_fraction", "random_opponent", "minimax_opponent", "controls",
                "worst_case_by_role", "generalization", "scope", "checkpoint_sha256"]},
            "training": {key: training[key] for key in ["method", "seed", "steps", "history", "loss_name",
                "changed_existing_synaptic_gains", "complete_canonical_boards", "teacher_in_rollout",
                "torch_numpy_max_error", "motor_training", "strategy_checkpoint_sha256"]},
            "motor": {"single_destination_successes": motor["success_count"], "single_destination_trials": motor["episodes"],
                      "sequential_game_moves": len(motor["games"][0]["moves"]),
                      "sequential_game_complete": motor["games"][0]["complete"],
                      "silenced_success": motor["silenced"]["success"],
                      "geometry": motor["geometry"], "sensor": motor["sensor"], "scope": motor["scope"]}},
        "so101_simulation": {"conditions": aggregate, "criterion": state["criterion"],
            "state_evaluation_role": state["evaluation_role"],
            "wrist_acceptance_scope": wrist["acceptance_scope"],
            "wrist_extended_robustness_passed": wrist["extended_robustness_passed"],
            "wrist_baseline_kind": wrist["baseline_kind"]},
        "physical": {"experiment_date": "2026-09-16", "scope": physical["scope"],
            "circuit": physical["circuit"], "degrees_per_count": physical["degrees_per_count"],
            "synthetic_training": {key: physical["synthetic_training"][key] for key in
                ["training_examples", "heldout_examples", "steps", "after_mse", "heldout_direction_accuracy", "training_kind", "scope"]},
            "run_count": len(run_rows), "independent_session_count": len(records_by_session),
            "geometry": physical["geometry"],
            "temperature": {key: physical["temperature"][key] for key in
                ["samples", "seconds", "high_sample_groups", "min_c", "max_c", "goals_unchanged", "independent_thermometry"]},
            "limitations": ["All recorded neural drive values equal -1; no physical bidirectional target-tracking proof.",
                            "Only base motion was neural-driven; body/gripper trials used separate deterministic controls.",
                            "Autonomous grasping and physical tic-tac-toe were not demonstrated."]}}
    write_json("results.json", results)
    if validation_record is not None:
        payload = validation_record.read_bytes()
        validation = json.loads(payload)
        assert validation["schema"] == "fruitfly-publication-validation-v1"
        (destination / "validation-2026-09-26.json").write_bytes(payload)
    artifacts = {p.name: {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                 for p in sorted(destination.iterdir())}
    write_json("provenance.json", {"schema_version": 1, "export_date": "2026-09-26",
        "method": "Selective field export; original records unchanged; full source manifest verified before export.",
        "original_manifest_entries_verified": len(original_manifest),
        "redactions": ["Absolute paths", "Device identifiers", "Raw session identifiers", "Wall-clock timestamps",
                       "Calibration profiles", "Images", "Full neural activations", "Network/session metadata"],
        "source_availability": "Original local evidence and checkpoints are not bundled in this snapshot. Hashes record identity, not public availability or independent certification.",
        "inputs": inputs, "public_artifacts": artifacts})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New directory; existing paths are rejected")
    parser.add_argument("--validation-record", type=Path, help="Optional independently generated publication validation JSON")
    args = parser.parse_args()
    export(args.source.resolve(), args.output.resolve(), args.validation_record)
