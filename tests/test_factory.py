"""
Unit tests for Factory Steady-State Solver.
Ensures correctness, infeasibility detection, and deterministic behavior.
"""

import json
import subprocess
import sys
from pathlib import Path


def execute_factory(data):
    """Helper to run the factory solver and return (parsed_output, returncode)."""
    solver = Path(__file__).resolve().parent.parent / "factory" / "main.py"
    proc = subprocess.run(
        [sys.executable, str(solver)],
        input=json.dumps(data),
        text=True,
        capture_output=True
    )
    return json.loads(proc.stdout), proc.returncode


def test_reference_case():
    """Validate solver output on standard sample input."""
    data = {
        "machines": {
            "assembler_1": {"crafts_per_min": 30},
            "chemical": {"crafts_per_min": 60}
        },
        "recipes": {
            "iron_plate": {
                "machine": "chemical",
                "time_s": 3.2,
                "in": {"iron_ore": 1},
                "out": {"iron_plate": 1}
            },
            "copper_plate": {
                "machine": "chemical",
                "time_s": 3.2,
                "in": {"copper_ore": 1},
                "out": {"copper_plate": 1}
            },
            "green_circuit": {
                "machine": "assembler_1",
                "time_s": 0.5,
                "in": {"iron_plate": 1, "copper_plate": 3},
                "out": {"green_circuit": 1}
            }
        },
        "modules": {
            "assembler_1": {"prod": 0.1, "speed": 0.15},
            "chemical": {"prod": 0.2, "speed": 0.1}
        },
        "limits": {
            "raw_supply_per_min": {"iron_ore": 5000, "copper_ore": 5000},
            "max_machines": {"assembler_1": 300, "chemical": 300}
        },
        "target": {"item": "green_circuit", "rate_per_min": 1800}
    }

    output, code = execute_factory(data)
    assert code == 0
    assert output["status"] == "ok"
    assert "per_recipe_crafts_per_min" in output
    assert "per_machine_counts" in output
    assert "raw_consumption_per_min" in output

    crafts = output["per_recipe_crafts_per_min"]["green_circuit"]
    assert abs(crafts * 1.1 - 1800) < 1.0, "Production rate must match target"


def test_constraint_infeasible():
    """Case with insufficient machines/supply → infeasible."""
    data = {
        "machines": {
            "assembler_1": {"crafts_per_min": 30},
            "chemical": {"crafts_per_min": 60}
        },
        "recipes": {
            "iron_plate": {
                "machine": "chemical",
                "time_s": 3.2,
                "in": {"iron_ore": 1},
                "out": {"iron_plate": 1}
            },
            "copper_plate": {
                "machine": "chemical",
                "time_s": 3.2,
                "in": {"copper_ore": 1},
                "out": {"copper_plate": 1}
            },
            "green_circuit": {
                "machine": "assembler_1",
                "time_s": 0.5,
                "in": {"iron_plate": 1, "copper_plate": 3},
                "out": {"green_circuit": 1}
            }
        },
        "modules": {
            "assembler_1": {"prod": 0.1, "speed": 0.15},
            "chemical": {"prod": 0.2, "speed": 0.1}
        },
        "limits": {
            "raw_supply_per_min": {"iron_ore": 1000, "copper_ore": 1000},
            "max_machines": {"assembler_1": 10, "chemical": 10}
        },
        "target": {"item": "green_circuit", "rate_per_min": 5000}
    }

    output, code = execute_factory(data)
    assert code == 0
    assert output["status"] == "infeasible"
    assert output["max_feasible_target_per_min"] > 0
    assert len(output["bottleneck_hint"]) >= 1


def test_empty_recipes():
    """Ensure missing recipes trigger graceful error."""
    data = {
        "machines": {},
        "recipes": {},
        "modules": {},
        "limits": {"raw_supply_per_min": {}, "max_machines": {}},
        "target": {"item": "ghost", "rate_per_min": 100}
    }

    output, _ = execute_factory(data)
    assert output["status"] == "error"
    assert "message" in output


def test_reproducibility():
    """Repeated identical runs must produce identical JSON output."""
    data = {
        "machines": {"asm": {"crafts_per_min": 60}},
        "recipes": {
            "r1": {
                "machine": "asm",
                "time_s": 1.0,
                "in": {"raw": 1},
                "out": {"item_a": 1}
            }
        },
        "modules": {},
        "limits": {
            "raw_supply_per_min": {"raw": 1000},
            "max_machines": {"asm": 100}
        },
        "target": {"item": "item_a", "rate_per_min": 100}
    }

    results = [execute_factory(data)[0] for _ in range(3)]
    ref = json.dumps(results[0], sort_keys=True)
    assert all(json.dumps(r, sort_keys=True) == ref for r in results)


if __name__ == "__main__":
    test_reference_case()
    test_constraint_infeasible()
    test_empty_recipes()
    test_reproducibility()
    print("\n✅ Factory tests completed successfully.")
