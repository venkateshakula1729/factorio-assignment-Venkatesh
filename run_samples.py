"""
Unified test runner for both Factory and Belts solvers.
Executes internal tests and sample demonstration runs.
"""

import subprocess
import sys
from pathlib import Path


def run_tests():
    base = Path(__file__).resolve().parent
    tests = [
        base / "test_factory.py",
        base / "test_belts.py",
    ]
    for t in tests:
        print(f"\n Running {t.name}...")
        res = subprocess.run([sys.executable, str(t)], capture_output=True, text=True)
        if res.returncode == 0:
            print(res.stdout)
        else:
            print("Test failed:\n", res.stderr)


def run_sample_solvers():
    """Optional quick demonstration of both solvers with minimal sample inputs."""
    import json

    factory_input = {
        "machines": {"asm": {"crafts_per_min": 60}},
        "recipes": {
            "r1": {"machine": "asm", "time_s": 1.0, "in": {"iron_ore": 1}, "out": {"plate": 1}}
        },
        "modules": {},
        "limits": {
            "raw_supply_per_min": {"iron_ore": 200},
            "max_machines": {"asm": 5},
        },
        "target": {"item": "plate", "rate_per_min": 100},
    }

    belts_input = {
        "nodes": {"A": {"capacity": 500}, "B": {"capacity": 500}},
        "edges": [{"from": "A", "to": "B", "lower_bound": 0, "capacity": 100}],
        "sources": [{"node": "A", "supply": 80}],
        "sink": "B",
    }

    print("\n Running Factory Solver...")
    proc1 = subprocess.run(
        [sys.executable, str(Path(__file__).parent.parent / "factory" / "main.py")],
        input=json.dumps(factory_input),
        text=True,
        capture_output=True,
    )
    print(proc1.stdout)

    print("\n Running Belts Solver...")
    proc2 = subprocess.run(
        [sys.executable, str(Path(__file__).parent.parent / "belts" / "main.py")],
        input=json.dumps(belts_input),
        text=True,
        capture_output=True,
    )
    print(proc2.stdout)


if __name__ == "__main__":
    print(" Running all solvers and tests...")
    run_tests()
    run_sample_solvers()
    print("\n All sample runs completed successfully.")
