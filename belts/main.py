#!/usr/bin/env python3
"""
Belts Flow Feasibility and Max-Throughput Solver
------------------------------------------------
Reads a flow network in JSON format, enforces lower and upper bounds,
and computes a feasible max-flow configuration under node and edge capacity limits.

Implements:
  - Lower-bound and node-splitting transformations
  - Feasibility check via auxiliary graph construction
  - Max-flow computation and infeasibility certificate generation
  - Deterministic JSON outputs for evaluation systems
"""

import sys
import json
import networkx as nx
from typing import Dict, Any, List, Tuple, Set
from collections import defaultdict

EPS = 1e-9


class FlowGraph:
    """Encapsulates a directed flow network with bounds, node capacities, and supply/sink structure."""

    def __init__(self):
        self.graph = nx.DiGraph()
        self.sources: Dict[str, float] = {}
        self.sink: str | None = None
        self.node_caps: Dict[str, float] = {}
        self.edge_meta: Dict[Tuple[str, str], Dict[str, float]] = {}
        self.orig_edges: Dict[Tuple[str, str], Dict[str, float]] = {}

    def add_edge(self, u: str, v: str, lo: float, hi: float):
        """Insert edge with lower and upper flow bounds."""
        self.graph.add_edge(u, v, capacity=hi, lower=lo)
        self.edge_meta[(u, v)] = {"lo": lo, "hi": hi}
        self.orig_edges[(u, v)] = {"lo": lo, "hi": hi}

    def add_node_capacity(self, node: str, cap: float):
        """Add node capacity constraint."""
        self.node_caps[node] = cap

    def add_source(self, node: str, supply: float):
        """Add a fixed supply source node."""
        self.sources[node] = supply

    def set_sink(self, node: str):
        """Designate a node as the global sink."""
        self.sink = node

    def nodes(self) -> Set[str]:
        return set(self.graph.nodes())

    def edges(self) -> List[Tuple[str, str]]:
        return list(self.graph.edges())


def split_nodes_for_capacity(base: FlowGraph) -> FlowGraph:
    """Perform node-splitting transformation for node capacity constraints."""
    new = FlowGraph()
    new.sources = base.sources.copy()
    new.sink = base.sink

    split = {n for n in base.node_caps if n not in base.sources and n != base.sink}

    for u, v in base.edges():
        e = base.edge_meta[(u, v)]
        lo, hi = e["lo"], e["hi"]
        u_out = f"{u}_out" if u in split else u
        v_in = f"{v}_in" if v in split else v
        new.add_edge(u_out, v_in, lo, hi)

    for node in split:
        cap = base.node_caps[node]
        new.add_edge(f"{node}_in", f"{node}_out", 0, cap)

    return new


def transform_lower_bounds(base: FlowGraph) -> Tuple[FlowGraph, Dict[str, float]]:
    """Shift lower bounds out of the system and record node imbalances."""
    transformed = FlowGraph()
    transformed.sources = base.sources.copy()
    transformed.sink = base.sink
    transformed.node_caps = base.node_caps.copy()

    imbalance = defaultdict(float)
    for (u, v), meta in base.edge_meta.items():
        lo, hi = meta["lo"], meta["hi"]
        transformed.add_edge(u, v, 0, hi - lo)
        if lo > EPS:
            imbalance[u] -= lo
            imbalance[v] += lo

    return transformed, dict(imbalance)


def build_auxiliary_graph(flow: FlowGraph, imbalance: Dict[str, float]) -> Tuple[nx.DiGraph, str, str, float]:
    """Construct auxiliary graph for feasibility test."""
    aux = nx.DiGraph()
    for u, v in flow.graph.edges():
        aux.add_edge(u, v, capacity=flow.graph[u][v].get("capacity", float("inf")))

    S, T = "__super_source__", "__super_sink__"
    total = 0.0

    for n, b in imbalance.items():
        if b > EPS:
            aux.add_edge(S, n, capacity=b)
            total += b
        elif b < -EPS:
            aux.add_edge(n, T, capacity=-b)

    return aux, S, T, total


def parse_input(data: Dict[str, Any]) -> FlowGraph:
    """Parse JSON input into a FlowGraph."""
    g = FlowGraph()

    for e in data.get("edges", []):
        u, v = e["from"], e["to"]
        lo = e.get("lower_bound", e.get("lo", 0))
        hi = e.get("capacity", e.get("hi", float("inf")))
        g.add_edge(u, v, lo, hi)

    node_caps = data.get("node_caps", {})
    for n, c in node_caps.items():
        g.add_node_capacity(n, c)

    sources = data.get("sources", {})
    if isinstance(sources, list):
        for s in sources:
            g.add_source(s["node"], s["supply"])
    elif isinstance(sources, dict):
        for n, s in sources.items():
            g.add_source(n, s)

    if sink := data.get("sink"):
        g.set_sink(sink)

    return g


def basic_validity_check(g: FlowGraph) -> Tuple[bool, str]:
    """Ensure graph structure validity before computation."""
    if not g.sources:
        return False, "No sources specified"
    if not g.sink:
        return False, "No sink specified"
    if not g.edges():
        return False, "No edges defined"
    if g.sink not in g.nodes():
        return False, f"Sink '{g.sink}' missing"
    for s in g.sources:
        if s not in g.nodes():
            return False, f"Source '{s}' missing"
    return True, ""


def check_feasibility(flow: FlowGraph, imbalance: Dict[str, float]) -> Tuple[bool, Dict[str, Any]]:
    """Check feasibility of the network after lower-bound adjustment."""
    if not imbalance or all(abs(b) < EPS for b in imbalance.values()):
        return True, {}

    aux, S, T, demand = build_auxiliary_graph(flow, imbalance)

    try:
        value, fdict = nx.maximum_flow(aux, S, T)
    except nx.NetworkXError as e:
        return False, {"error": str(e)}

    if abs(value - demand) < EPS:
        return True, {}

    cut_val, (reach, nonreach) = nx.minimum_cut(aux, S, T)
    reach = [n for n in reach if n not in {S, T}]

    tight = []
    for u in reach:
        for v in nonreach:
            if aux.has_edge(u, v):
                cap = aux[u][v]["capacity"]
                if abs(fdict.get(u, {}).get(v, 0) - cap) < EPS:
                    tight.append({"from": u, "to": v, "capacity": round(cap, 4)})

    return False, {
        "cut_reachable": sorted(reach),
        "deficit": {"demand_balance": round(demand - value, 4), "tight_edges": tight}
    }


def solve_belts(data: Dict[str, Any]) -> Dict[str, Any]:
    """Main solver for belt flow feasibility and throughput optimization."""
    try:
        g = parse_input(data)
    except Exception as e:
        return {"status": "error", "message": f"Failed to parse input: {e}"}

    ok, msg = basic_validity_check(g)
    if not ok:
        return {"status": "error", "message": msg}

    if g.node_caps:
        g = split_nodes_for_capacity(g)

    g2, imb = transform_lower_bounds(g)
    feasible, cert = check_feasibility(g2, imb)
    if not feasible:
        return {"status": "infeasible", **cert}

    flow = nx.DiGraph()
    for u, v in g2.graph.edges():
        flow.add_edge(u, v, capacity=g2.graph[u][v].get("capacity", float("inf")))

    unified_source = "__source__"
    total_supply = 0.0
    for s, val in g2.sources.items():
        flow.add_edge(unified_source, s, capacity=val)
        total_supply += val

    try:
        fval, fdict = nx.maximum_flow(flow, unified_source, g2.sink)
    except nx.NetworkXError as e:
        return {"status": "error", "message": f"Flow computation failed: {e}"}

    if abs(fval - total_supply) > EPS:
        try:
            cut_val, (reach, nonreach) = nx.minimum_cut(flow, unified_source, g2.sink)
            reach = [n for n in reach if n != unified_source]
            tight = []
            for u in reach:
                for v in nonreach:
                    if flow.has_edge(u, v):
                        cap = flow[u][v]["capacity"]
                        if abs(fdict.get(u, {}).get(v, 0) - cap) < EPS:
                            u_clean = u.replace("_out", "")
                            v_clean = v.replace("_in", "")
                            tight.append({"from": u_clean, "to": v_clean, "capacity": round(cap, 4)})
            return {
                "status": "infeasible",
                "cut_reachable": sorted(reach),
                "deficit": {"demand_balance": round(total_supply - fval, 4), "tight_edges": tight}
            }
        except Exception:
            return {"status": "infeasible", "message": "Could not achieve full source-sink flow"}

    results = []
    for u in fdict:
        if u == unified_source:
            continue
        for v, flow_val in fdict[u].items():
            if abs(flow_val) < EPS:
                continue
            u_base, v_base = u.replace("_out", ""), v.replace("_in", "")
            if (u_base, v_base) in g.orig_edges:
                lo = g.orig_edges[(u_base, v_base)]["lo"]
            else:
                lo = 0
            results.append({"from": u_base, "to": v_base, "flow": round(flow_val + lo, 4)})

    results.sort(key=lambda e: (e["from"], e["to"]))
    return {"status": "ok", "max_flow_per_min": round(fval, 4), "flows": results}


def main():
    """Command-line entrypoint: read JSON from stdin, solve, and print result."""
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("Input must be a JSON object")

        res = solve_belts(data)
        json.dump(res, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")

    except json.JSONDecodeError as e:
        json.dump({"status": "error", "message": f"Invalid JSON: {e}"}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        sys.exit(1)
    except Exception as e:
        json.dump({"status": "error", "message": str(e)}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
