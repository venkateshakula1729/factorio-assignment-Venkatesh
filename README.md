# factorio-assignment-Venkatesh


## Overview

This repository implements two independent solvers for production and logistics systems, inspired by **Factorio-style throughput and flow constraints**.
Both programs operate in **deterministic batch mode**: they read a single JSON problem description from `stdin`, compute a verified solution, and emit canonical JSON to `stdout`.

| Component         | Purpose                                                                        |
| ----------------- | ------------------------------------------------------------------------------ |
| `factory/main.py` | Steady-state factory optimization (production balance via Linear Programming). |
| `belts/main.py`   | Network flow solver with edge bounds and node capacity constraints.            |

All computations are **purely mathematical**, using no simulation or stochastic sampling, ensuring reproducibility under the same inputs.

---

## 1. Architecture Overview

Each solver is **self-contained**, with layered responsibility:

```
Input JSON → Parser → Transformation → Core Solver → Feasibility Check → Result Serializer
```

### a. belts/main.py

Implements **bounded-flow feasibility and maximum-throughput computation**.

* Supports:

  * Directed edges with lower and upper bounds
  * Node capacity constraints (via node-splitting)
  * Multiple sources and a single sink
* Outputs:

  * Total feasible throughput
  * Per-edge realized flow values
  * Feasibility certificate (if infeasible)

Core algorithms:

1. **Lower-Bound Transformation**

   * Shifts lower bounds into node imbalance terms
   * Converts constrained edges into equivalent residual-capacity edges

2. **Node-Splitting Transformation**

   * Enforces per-node flow caps by splitting nodes into `*_in` and `*_out`
   * Inserts artificial capacity edges between them

3. **Feasibility Test**

   * Builds an **auxiliary flow network** with a super-source/sink
   * Computes `max_flow(super_source → super_sink)`
   * If the achieved flow equals total imbalance, the system is feasible.

4. **Max-Flow Computation**

   * Augments with a unified source combining all supplies
   * Runs Edmonds–Karp/Preflow–Push via `networkx.maximum_flow`
   * Detects and reports minimal cuts when infeasible

5. **Deterministic Output Serialization**

   * JSON fields sorted for reproducibility
   * Rounded numeric precision (`round(x, 4)`) for stable grading

---

### b. factory/main.py

Implements a **steady-state material balance solver** for multi-stage production graphs.

* Solves:

  * Material balance constraints (`Σ in = Σ out`)
  * Machine capacity limits
  * Raw material supply caps
* Uses **Linear Programming (LP)** to minimize total machine usage.

Core stages:

1. **Material Classification**
   Distinguishes *raw*, *intermediate*, and *target* items via recipe I/O closure.

2. **Module-Adjusted Machine Rates**
   Applies speed and productivity modifiers:

   ```
   eff_rate = base_rate * (1 + speed_bonus) * 60 / time_s
   prod_mult = 1 + prod_bonus
   ```

3. **Linear Program Formulation**

   ```
   minimize Σ (craft_rate[r] / eff_rate[r])
   subject to:
     - ∑ production(i) - ∑ consumption(i) = 0 (for intermediates)
     - ∑ production(target) = target_rate
     - ∑ consumption(raw) ≤ raw_supply_cap
     - Σ(machine_type usage) ≤ capacity
   ```

4. **Solver Engine**

   * Uses `pulp` with the CBC backend (`PULP_CBC_CMD`)
   * Enforces strict numerical tolerance `EPS = 1e-9`

5. **Binary Search Fallback**

   * If infeasible at target rate, performs bounded binary search on rate
   * Returns maximum feasible throughput and bottleneck hints

6. **Result Composition**

   * Returns:

     * Per-recipe production rates
     * Machine counts
     * Raw consumption rates
     * Optional bottleneck hints (machine caps or raw supply limits)

---

## 2. Mathematical Foundations

| Concept           | belts/main.py                        | factory/main.py                           |
| ----------------- | ------------------------------------ | ----------------------------------------- |
| Optimization Type | Network flow feasibility & max flow  | Linear Programming                        |
| Primary Variables | Edge flows                           | Recipe craft rates                        |
| Constraints       | Flow conservation, bounds, node caps | Material balance, machine & resource caps |
| Objective         | Maximize feasible throughput         | Minimize machine load                     |
| Solver Backend    | `networkx.maximum_flow`              | `pulp` (CBC LP solver)                    |
| Verification      | Min-cut infeasibility certificate    | Binary-search bottleneck recovery         |

Both solvers assume **steady-state**, **deterministic**, and **linear** dynamics — no temporal evolution or probabilistic behavior.

---

## 3. Input Schema

### A. belts/main.py

```json
{
  "edges": [
    {"from": "A", "to": "B", "lower_bound": 5, "capacity": 10},
    {"from": "B", "to": "C", "capacity": 8}
  ],
  "node_caps": {"B": 12},
  "sources": {"A": 8},
  "sink": "C"
}
```

### B. factory/main.py

```json
{
  "machines": {
    "assembler": {"crafts_per_min": 1.2},
    "furnace": {"crafts_per_min": 0.5}
  },
  "recipes": {
    "iron_plate": {
      "machine": "furnace",
      "time_s": 3.2,
      "in": {"iron_ore": 1},
      "out": {"iron_plate": 1}
    },
    "green_circuit": {
      "machine": "assembler",
      "time_s": 0.5,
      "in": {"iron_plate": 1, "copper_wire": 3},
      "out": {"green_circuit": 1}
    }
  },
  "modules": {"assembler": {"speed": 0.2, "prod": 0.1}},
  "limits": {
    "max_machines": {"assembler": 10},
    "raw_supply_per_min": {"iron_ore": 500, "copper_wire": 800}
  },
  "target": {"item": "green_circuit", "rate_per_min": 120}
}
```

---

## 4. Output Schema

### belts/main.py

```json
{
  "status": "ok",
  "max_flow_per_min": 8.0,
  "flows": [
    {"from": "A", "to": "B", "flow": 8.0},
    {"from": "B", "to": "C", "flow": 8.0}
  ]
}
```

### factory/main.py

```json
{
  "status": "ok",
  "per_recipe_crafts_per_min": {
    "iron_plate": 60.0,
    "green_circuit": 120.0
  },
  "per_machine_counts": {
    "furnace": 12.5,
    "assembler": 10.0
  },
  "raw_consumption_per_min": {
    "iron_ore": 60.0,
    "copper_wire": 360.0
  }
}
```

If infeasible, both solvers return structured diagnostics:

* **`status: infeasible`**
* **Cut certificate** or **bottleneck hints**

---

## 5. Error Handling

* Invalid JSON input → returns structured error JSON (`status: error`)
* Missing keys (e.g., no sources/sink) → explicit validation message
* All exceptions are **caught and reported** deterministically
* No stack traces or non-JSON stderr output

---

## 6. Determinism & Precision

* All outputs are **sorted (`sort_keys=True`)** for reproducibility.
* Floating-point outputs are rounded to **4–6 significant decimals**.
* No use of random seeds or heuristic solvers.

---

## 7. Dependencies

| Library                 | Purpose                                                  |
| ----------------------- | -------------------------------------------------------- |
| `networkx`              | Flow graph construction and max-flow/min-cut computation |
| `pulp`                  | Linear Programming engine                                |
| `json`, `sys`           | I/O serialization                                        |
| `typing`, `collections` | Type safety and default structures                       |

Python ≥ 3.9 recommended.

---

## 8. Complexity Analysis

| Solver            | Algorithm                        | Time Complexity               | Space Complexity |
| ----------------- | -------------------------------- | ----------------------------- | ---------------- |
| `belts/main.py`   | Edmonds–Karp / Preflow-Push      | O(V·E²)                       | O(E)             |
| `factory/main.py` | Linear Programming (Simplex/CBC) | Polynomial / practical linear | O(V + E)         |

Both programs are designed for **moderate-scale graphs (≤ 10³ nodes)** and **≤ 10⁴ edges/recipes** typical of mid-size simulation test cases.

---

## 9. Verification Strategy

* **Unit-level consistency:** balanced net flow per node after solving
* **Cross-consistency check:** ensure total inflow = total outflow ± tolerance
* **Regression validation:** identical JSON output under repeated runs
* **Performance test:** ensure solve time < 2 s for standard demos

---
