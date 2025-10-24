# Code is self-Explanatory with detailed comments written at appropriate places 
"""
Factory Steady-State Production Solver
--------------------------------------
Reads a structured JSON input describing machines, recipes, modules, limits, 
and target outputs, and computes a feasible steady-state production plan.

Implements:
  - Linear programming formulation for balance equations
  - Module-driven machine speed and productivity adjustments
  - Capacity and supply constraints for raw materials and machines
  - Binary search for determining maximum feasible production rate
"""

import sys
import json
import pulp
from typing import Dict, Any, Set, Tuple

EPS = 1e-9  # numerical precision tolerance


def classify_materials(recipes: Dict[str, Any], target: str) -> Tuple[Set[str], Set[str]]:
    """
    Identify which items are raw, intermediate, or final.

    Raw materials are consumed but never produced.
    Intermediate materials are produced and consumed internally.
    The target item is the final output of interest.
    """
    produced, consumed = set(), set()
    for rec in recipes.values():
        produced |= set(rec.get("out", {}).keys())
        consumed |= set(rec.get("in", {}).keys())

    raw_items = consumed - produced
    intermediates = (produced | consumed) - raw_items - {target}
    return raw_items, intermediates


def compute_recipe_speeds(recipes: Dict[str, Any],
                          machines: Dict[str, Any],
                          modules: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    """
    Compute the effective processing rates and productivity multipliers
    for all recipes given machine parameters and module bonuses.

    eff_rate = base_rate * (1 + speed_bonus) * 60 / time_s
    prod_mult = 1 + prod_bonus
    """
    effective = {}
    for rname, rec in recipes.items():
        mtype = rec["machine"]
        base_rate = machines[mtype]["crafts_per_min"]
        time_s = rec["time_s"]

        mod = modules.get(mtype, {})
        speed_bonus = mod.get("speed", 0.0)
        prod_bonus = mod.get("prod", 0.0)

        eff_rate = base_rate * (1 + speed_bonus) * 60 / time_s
        effective[rname] = {
            "machine": mtype,
            "eff_rate": eff_rate,
            "prod_mult": 1 + prod_bonus
        }

    return effective


def solve_production_lp(recipes: Dict[str, Any],
                        eff: Dict[str, Any],
                        raw: Set[str],
                        inter: Set[str],
                        target_item: str,
                        target_rate: float,
                        limits: Dict[str, Any]) -> Dict[str, Any]:
    """
    Formulate and solve the linear program representing the steady-state factory.

    The LP minimizes total machine load while ensuring:
      - Material conservation across all items
      - Machine count and raw supply constraints
      - Target item is produced at required rate
    """
    model = pulp.LpProblem("FactorySteadyState", pulp.LpMinimize)

    # Decision variables: production rate per recipe (crafts per minute)
    x = {r: pulp.LpVariable(f"x_{r}", lowBound=0) for r in recipes}

    # Objective: minimize total machine usage
    model += pulp.lpSum(x[r] / eff[r]["eff_rate"] for r in recipes)

    # Collect all items appearing in recipes
    all_items = {i for rec in recipes.values() for i in rec.get("in", {}).keys() | rec.get("out", {}).keys()}

    # Flow balance equations
    for item in all_items:
        produced = pulp.lpSum(x[r] * rec.get("out", {}).get(item, 0) * eff[r]["prod_mult"]
                              for r, rec in recipes.items())
        consumed = pulp.lpSum(x[r] * rec.get("in", {}).get(item, 0)
                              for r, rec in recipes.items())
        net = produced - consumed

        if item == target_item:
            model += net == target_rate
        elif item in inter:
            model += net == 0
        elif item in raw:
            model += net <= 0
            cap = limits.get("raw_supply_per_min", {}).get(item, float("inf"))
            if cap < float("inf"):
                model += -net <= cap

    # Machine capacity constraints
    for mtype, cap in limits.get("max_machines", {}).items():
        load = pulp.lpSum(x[r] / eff[r]["eff_rate"] for r in recipes if eff[r]["machine"] == mtype)
        model += load <= cap

    solver = pulp.PULP_CBC_CMD(msg=0, timeLimit=2)
    status = model.solve(solver)

    if status == pulp.LpStatusOptimal:
        return extract_solution(x, recipes, eff, raw)
    return {"status": "infeasible"}


def extract_solution(xvars: Dict[str, pulp.LpVariable],
                     recipes: Dict[str, Any],
                     eff: Dict[str, Any],
                     raw: Set[str]) -> Dict[str, Any]:
    """
    Extracts optimal solution from the solved LP, computing:
      - per-recipe crafts/min
      - per-machine type count
      - raw consumption rates
    """
    per_recipe = {r: round(max(0.0, v.varValue or 0.0), 6) for r, v in xvars.items()}

    per_machine = {}
    for r, rate in per_recipe.items():
        mtype = eff[r]["machine"]
        used = rate / eff[r]["eff_rate"]
        per_machine[mtype] = per_machine.get(mtype, 0.0) + used

    per_machine = {m: round(v, 6) for m, v in per_machine.items()}

    raw_use = {}
    for item in raw:
        total = sum(per_recipe[r] * recipes[r].get("in", {}).get(item, 0) for r in recipes)
        if total > EPS:
            raw_use[item] = round(total, 6)

    return {
        "status": "ok",
        "per_recipe_crafts_per_min": per_recipe,
        "per_machine_counts": per_machine,
        "raw_consumption_per_min": raw_use
    }


def search_max_rate(recipes, eff, raw, inter, tgt, goal_rate, limits):
    """
    If the requested target rate is infeasible, use binary search to 
    determine the maximum feasible production rate within tolerance.
    """
    low, high = 0.0, goal_rate
    best = None

    while high - low > EPS:
        mid = (low + high) / 2
        res = solve_production_lp(recipes, eff, raw, inter, tgt, mid, limits)
        if res["status"] == "ok":
            best = res
            low = mid
        else:
            high = mid

    hints = []
    if best:
        used = best["per_machine_counts"]
        caps = limits.get("max_machines", {})
        for m, val in used.items():
            if abs(val - caps.get(m, float("inf"))) < 1e-6:
                hints.append(f"{m} cap")

        cons = best["raw_consumption_per_min"]
        raw_caps = limits.get("raw_supply_per_min", {})
        for i, val in cons.items():
            if abs(val - raw_caps.get(i, float("inf"))) < 1e-6:
                hints.append(f"{i} supply")

    return {
        "status": "infeasible",
        "max_feasible_target_per_min": round(low, 4),
        "bottleneck_hint": sorted(hints)
    }


def solve_factory(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main orchestration function:
      - Parses input
      - Precomputes rates and bonuses
      - Solves LP or finds maximum feasible rate
    """
    machines = data["machines"]
    recipes = data["recipes"]
    modules = data.get("modules", {})
    limits = data["limits"]
    target = data["target"]

    tgt_item = target["item"]
    tgt_rate = target["rate_per_min"]

    raw, inter = classify_materials(recipes, tgt_item)
    eff = compute_recipe_speeds(recipes, machines, modules)

    result = solve_production_lp(recipes, eff, raw, inter, tgt_item, tgt_rate, limits)
    if result["status"] == "ok":
        return result
    return search_max_rate(recipes, eff, raw, inter, tgt_item, tgt_rate, limits)


def main():
    """Entry point: read from stdin, solve, and output formatted JSON."""
    try:
        data = json.load(sys.stdin)
        result = solve_factory(data)
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    except Exception as e:
        json.dump({"status": "error", "message": str(e)}, sys.stdout, indent=2)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
