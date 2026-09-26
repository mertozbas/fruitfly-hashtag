"""Verify the public snapshot and recompute its tabulated outcomes (stdlib only)."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent
    provenance = json.loads((root / "provenance.json").read_text())
    results = json.loads((root / "results.json").read_text())
    for name, expected in provenance["public_artifacts"].items():
        payload = (root / name).read_bytes()
        assert len(payload) == expected["bytes"], f"Size mismatch: {name}"
        assert hashlib.sha256(payload).hexdigest() == expected["sha256"], f"Hash mismatch: {name}"

    def groups(filename: str, field: str) -> dict[str, list[dict]]:
        output = defaultdict(list)
        with (root / filename).open(newline="") as handle:
            for row in csv.DictReader(handle):
                output[row[field]].append(row)
        return output

    episodes = groups("so101-episodes.csv", "condition")
    for condition in results["so101_simulation"]["conditions"]:
        rows = episodes[condition["condition"]]
        assert len(rows) == condition["episodes"]
        assert len({row["seed"] for row in rows}) == len(rows)
        assert sum(row["success"] == "True" for row in rows) == condition["successes"]
        assert sum(row["unsafe"] == "True" for row in rows) == condition["unsafe_count"]
        print(f"{condition['condition']}: {condition['successes']}/{len(rows)}, unsafe={condition['unsafe_count']}")

    strategy = results["tictactoe"]["strategy"]
    assert strategy["optimal_decisions"] <= strategy["reachable_decision_boards"]
    assert math.isclose(strategy["optimal_fraction"], strategy["optimal_decisions"] / strategy["reachable_decision_boards"])
    for label in ["random_opponent", "minimax_opponent"]:
        row = strategy[label]
        assert row["wins"] + row["draws"] + row["losses"] == row["episodes"]
    for row in strategy["controls"].values():
        assert row["wins"] + row["draws"] + row["losses"] == row["episodes"]
    print(f"tictactoe strategy: {strategy['optimal_decisions']}/{strategy['reachable_decision_boards']} recorded optimal decisions")
    motor = groups("tictactoe-motor.csv", "condition")
    assert len(motor["single_destination"]) == results["tictactoe"]["motor"]["single_destination_trials"]
    assert sum(row["success"] == "True" for row in motor["single_destination"]) == results["tictactoe"]["motor"]["single_destination_successes"]
    assert {int(row["cell"]) for row in motor["single_destination"]} == set(range(9))
    assert len(motor["sequential_game"]) == 5 and all(row["success"] == "True" for row in motor["sequential_game"])
    assert len(motor["silenced"]) == 1 and motor["silenced"][0]["success"] == "False"
    print("tictactoe motor: 9/9 destinations; 5/5 sequential moves; silenced control failed")

    runs = groups("physical-runs.csv", "run_id")
    motion = groups("physical-motion.csv", "run_id")
    assert set(runs) == set(motion)
    assert len(runs) == results["physical"]["run_count"]
    for run_id, rows in motion.items():
        summary = runs[run_id][0]
        assert len(rows) == int(summary["samples"])
        elapsed = [float(row["elapsed_seconds"]) for row in rows]
        assert elapsed[0] == 0 and all(a < b for a, b in zip(elapsed, elapsed[1:]))
        assert math.isclose(elapsed[-1], float(summary["logged_span_seconds"]), abs_tol=1e-9)
        assert int(rows[-1]["base_displacement_counts"]) == int(summary["measured_delta_counts"])
        assert sum(row["neural_command"] == "True" for row in rows) == int(summary["command_rows"])
        degrees = int(rows[-1]["base_displacement_counts"]) * results["physical"]["degrees_per_count"]
        assert math.isclose(degrees, float(summary["measured_delta_degrees"]), abs_tol=1e-9)
        assert {float(row["drive"]) for row in rows} == {-1.0}
        print(f"{run_id}: {len(rows)} samples, {summary['command_rows']} updates, {degrees:.5f} deg")
    validation_path = root / "validation-2026-09-26.json"
    if validation_path.is_file():
        validation = json.loads(validation_path.read_text())
        assert "validation-2026-09-26.json" in provenance["public_artifacts"]
        fresh = validation["xox_strategy_evaluation"]
        assert fresh["model_sha256"] == strategy["checkpoint_sha256"]
        for key in ["reachable_decision_boards", "optimal_decisions", "random_opponent", "minimax_opponent", "worst_case_by_role"]:
            assert fresh["result"][key] == strategy[key], f"Fresh strategy mismatch: {key}"
        assert fresh["result"]["controls"]["silenced"] == strategy["controls"]["silenced"]
        assert validation["unique_tests"]["passed"] == 247
        assert validation["scope_and_limitations"]["new_physical_hardware_execution"] is False
        print("Fresh validation record: 247 distinct tests; matching strategy results; no new physical execution")
    print("PASS: public hashes and recorded outcome arithmetic verified; no experiments executed.")


if __name__ == "__main__":
    main()
