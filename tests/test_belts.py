"""
Unit tests for Belts Flow Solver.
Verifies feasibility, bounds handling, node caps, and determinism.
"""

import json
import subprocess
import sys
from pathlib import Path


def execute_belts(data):
    """Run the belts solver and capture its output."""
    solver = Path(__file__).resolve().parent.parent / "belts" / "main.py"
    proc = subprocess.run(
        [sys.executable, str(solver)],
        input=json.dumps(data),
        text=True,
        capture_output=True
    )
    if proc.returncode not in [0, 1]:
        raise RuntimeError(f"Execution error: {proc.stderr}")
    return json.loads(proc.stdout), proc.returncode


def test_basic_flow():
    """Feasible single-path flow test."""
    data = {
        "nodes": {"A": {"capacity": 1000}, "B": {"capacity": 1000}, "C": {"capacity": 1000}},
        "edges": [
            {"from": "A", "to": "B", "lower_bound": 0, "capacity": 100},
            {"from": "B", "to": "C", "lower_bound": 0, "capacity": 100}
        ],
        "sources": [{"node": "A", "supply": 50}],
        "sink": "C"
    }

    output, _ = execute_belts(data)
    assert output["status"] == "ok"
    assert abs(output["max_flow_per_min"] - 50) < 1e-9
    assert len(output["flows"]) == 2


def test_infeasible_lower():
    """Edge lower bound exceeds available supply → infeasible."""
    data = {
        "nodes": {"A": {"capacity": 500}, "B": {"capacity": 500}},
        "edges": [{"from": "A", "to": "B", "lower_bound": 60, "capacity": 100}],
        "sources": [{"node": "A", "supply": 50}],
        "sink": "B"
    }

    output, _ = execute_belts(data)
    assert output["status"] == "infeasible"


def test_capacity_limit():
    """Node capacity bottleneck check."""
    data = {
        "nodes": {
            "A": {"capacity": 500},
            "B": {"capacity": 25},  # tight cap
            "C": {"capacity": 500}
        },
        "edges": [
            {"from": "A", "to": "B", "lower_bound": 0, "capacity": 100},
            {"from": "B", "to": "C", "lower_bound": 0, "capacity": 100}
        ],
        "sources": [{"node": "A", "supply": 50}],
        "sink": "C"
    }

    output, _ = execute_belts(data)
    assert output["status"] == "infeasible"


def test_deterministic_output():
    """Repeated runs with same input must yield identical flow maps."""
    data = {
        "nodes": {
            "A": {"capacity": 1000},
            "B": {"capacity": 1000},
            "C": {"capacity": 1000},
            "D": {"capacity": 1000}
        },
        "edges": [
            {"from": "A", "to": "B", "lower_bound": 0, "capacity": 50},
            {"from": "A", "to": "C", "lower_bound": 0, "capacity": 50},
            {"from": "B", "to": "D", "lower_bound": 0, "capacity": 50},
            {"from": "C", "to": "D", "lower_bound": 0, "capacity": 50}
        ],
        "sources": [{"node": "A", "supply": 80}],
        "sink": "D"
    }

    runs = [execute_belts(data)[0] for _ in range(3)]
    baseline = json.dumps(runs[0], sort_keys=True)
    assert all(json.dumps(r, sort_keys=True) == baseline for r in runs)


if __name__ == "__main__":
    test_basic_flow()
    test_infeasible_lower()
    test_capacity_limit()
    test_deterministic_output()
    print("\n✅ Belts tests completed successfully.")
