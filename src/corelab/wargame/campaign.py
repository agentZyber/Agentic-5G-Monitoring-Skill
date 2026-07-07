"""Theater-scale campaign — a large multi-wave red/blue simulation on a battlespace map.

The built-in :mod:`~corelab.wargame.scenario` games are deliberately tiny (a handful of turns, a few
threats — unit-test fixtures). This module is the opposite: a dispersed force laydown of ~28 nodes
across three sectors, hit by sustained *waves* of jamming / flooding / intrusion / spoofing over ~80
turns, with a doctrine-driven blue defender that senses continuously and neutralises threats by node
criticality. It exists to be *watched*: :func:`iter_campaign` yields one map-ready frame per turn, so a
front-end can animate the whole engagement over ~30 s and show mission availability rise and fall under
pressure. Deterministic and seeded — a synthetic exercise, non-kinetic, decision-support only.
"""
from __future__ import annotations

import random
from typing import Any, Dict, Iterator, List, Tuple

# node kinds grouped by domain — the battlespace is a 5G/IoT tactical network:
#   5G  : gnb (5G base station), core (5G core / UPF+AMF), relay (5G backhaul)
#   IoT : iot (IoT sensor field), gw (IoT gateway)
#   TAC : c2 (command & control), sat (SATCOM uplink), uav (ISR UAV), log (logistics)
NODE_LABEL = {"gnb": "gNB", "core": "5GC", "relay": "RELAY", "iot": "IoT", "gw": "IoT-GW",
              "c2": "C2", "sat": "SATCOM", "uav": "UAV", "log": "LOG"}
DOMAIN = {"gnb": "5G", "core": "5G", "relay": "5G", "iot": "IoT", "gw": "IoT",
          "c2": "TAC", "sat": "TAC", "uav": "TAC", "log": "TAC"}
KIND_LABEL = {"jam_link": "JAM", "signaling_flood": "FLOOD", "intrude_node": "INTRUDE", "spoof_feed": "SPOOF"}
CRIT = {"c2": 6, "core": 6, "sat": 5, "gnb": 4, "relay": 3, "gw": 3, "uav": 2, "iot": 2, "log": 1}

# force laydown: sector -> (x-band, [(node kind, count), …]); y spans the full height
_LAYDOWN: List[Tuple[str, Tuple[int, int], List[Tuple[str, int]]]] = [
    ("Rear",    (70, 300),  [("core", 1), ("sat", 2), ("c2", 1), ("log", 2)]),
    ("Main",    (390, 650), [("gnb", 2), ("relay", 5), ("core", 1), ("c2", 1), ("gw", 1)]),
    ("Forward", (710, 940), [("gnb", 4), ("iot", 5), ("uav", 2), ("gw", 1)]),
]

# adversary waves: mid-weighted intensity, each targeting sector(s) with a threat menu
_WAVES = [
    {"s": 4, "e": 26, "kinds": ["jam_link"], "sec": {"Forward"}, "rate": 2.3, "name": "Wave A · forward jamming"},
    {"s": 18, "e": 44, "kinds": ["signaling_flood"], "sec": {"Main"}, "rate": 2.2, "name": "Wave B · relay flood"},
    {"s": 32, "e": 58, "kinds": ["intrude_node", "spoof_feed"], "sec": {"Main", "Rear", "Forward"},
     "rate": 2.4, "name": "Wave C · intrusion & spoof"},
    {"s": 50, "e": 72, "kinds": ["jam_link", "signaling_flood", "intrude_node", "spoof_feed"], "sec": None,
     "rate": 5.2, "name": "Wave D · multi-vector surge"},
]
# blue neutralises a doctrine-approved base rate + surges reserves as the active load climbs — so the
# picture dips under a fast onset and recovers between waves rather than collapsing.
_BLUE_BASE = 1
_BLUE_SURGE_CAP = 6


def build_theater(seed: int = 7) -> Tuple[List[Dict[str, Any]], List[List[int]]]:
    """Deterministic node laydown + a comms mesh (each node linked to its 2 nearest)."""
    rng = random.Random(seed)
    nodes: List[Dict[str, Any]] = []
    i = 0
    for sector, (x0, x1), spec in _LAYDOWN:
        for kind, count in spec:
            for _ in range(count):
                nodes.append({
                    "id": f"N{i}", "kind": kind, "domain": DOMAIN[kind],
                    "x": round(rng.uniform(x0, x1), 1), "y": round(rng.uniform(70, 570), 1),
                    "label": f"{NODE_LABEL[kind]}-{i}", "sector": sector, "crit": CRIT[kind]})
                i += 1
    edges: set = set()
    for a, na in enumerate(nodes):
        nearest = sorted(range(len(nodes)),
                         key=lambda b: (na["x"] - nodes[b]["x"]) ** 2 + (na["y"] - nodes[b]["y"]) ** 2)
        for b in nearest[1:3]:
            edges.add(tuple(sorted((a, b))))
    return nodes, [list(e) for e in edges]


def _wave_names(t: int) -> List[str]:
    return [w["name"] for w in _WAVES if w["s"] <= t <= w["e"]]


def wave_windows() -> List[Dict[str, Any]]:
    """The wave schedule (start/end/name) — for a timeline legend in the map view."""
    return [{"s": w["s"], "e": w["e"], "name": w["name"]} for w in _WAVES]


def iter_campaign(turns: int = 80, seed: int = 11) -> Iterator[Dict[str, Any]]:
    """Yield one map-ready frame per turn: new injects, mitigations, the live threat set, and KPIs."""
    nodes, _ = build_theater()
    n = len(nodes)
    by_sector: Dict[str, List[int]] = {}
    for idx, node in enumerate(nodes):
        by_sector.setdefault(node["sector"], []).append(idx)

    rng = random.Random(seed)
    active: Dict[str, Dict[str, Any]] = {}     # threat_id -> {node_i, kind, born}
    tid = total_inj = total_mit = 0

    for t in range(1, turns + 1):
        injects: List[Dict[str, Any]] = []
        for w in _WAVES:
            if not (w["s"] <= t <= w["e"]):
                continue
            frac = (t - w["s"]) / max(1, w["e"] - w["s"])              # 0..1 through the wave
            ramp = max(0.0, min(frac / 0.25, (1 - frac) / 0.25, 1.0))  # trapezoid: full rate across the middle
            intensity = w["rate"] * ramp
            k = int(intensity) + (1 if rng.random() < (intensity - int(intensity)) else 0)
            pool = ([i for i in range(n) if nodes[i]["sector"] in w["sec"]] if w["sec"]
                    else list(range(n)))
            for _ in range(k):
                ni = rng.choice(pool)
                tid += 1
                thid = f"T{tid}"
                active[thid] = {"node_i": ni, "kind": rng.choice(w["kinds"]), "born": t}
                total_inj += 1
                injects.append({"threat_id": thid, "node": nodes[ni]["id"], "node_i": ni,
                                "kind": active[thid]["kind"]})

        # blue: sense (implicit) then neutralise up to the rate, worst-first (node criticality, then age)
        rate = _BLUE_BASE + min(_BLUE_SURGE_CAP, len(active) // 4)
        order = sorted(active.items(), key=lambda kv: (-nodes[kv[1]["node_i"]]["crit"], kv[1]["born"]))
        mitig: List[Dict[str, Any]] = []
        for thid, info in order[:rate]:
            del active[thid]
            total_mit += 1
            mitig.append({"threat_id": thid, "node": nodes[info["node_i"]]["id"], "node_i": info["node_i"]})

        compromised: Dict[int, List[str]] = {}
        for info in active.values():
            compromised.setdefault(info["node_i"], []).append(info["kind"])
        healthy = n - len(compromised)

        yield {
            "turn": t, "turns": turns,
            "injects": injects, "mitigations": mitig,
            "active": [{"threat_id": k, "node": nodes[v["node_i"]]["id"], "node_i": v["node_i"],
                        "kind": v["kind"], "age": t - v["born"]} for k, v in active.items()],
            "compromised": [nodes[i]["id"] for i in compromised],
            "waves": _wave_names(t),
            "kpi": {"active": len(active), "availability": round(healthy / n, 3), "healthy": healthy,
                    "total": n, "injected": total_inj, "mitigated": total_mit,
                    "worst_node": (max(compromised, key=lambda i: nodes[i]["crit"]) and
                                   nodes[max(compromised, key=lambda i: nodes[i]["crit"])]["label"])
                    if compromised else None},
        }


def run_campaign(turns: int = 80, seed: int = 11) -> Dict[str, Any]:
    """Collect the whole engagement (for a static render, a headless run, or tests)."""
    nodes, edges = build_theater()
    frames = list(iter_campaign(turns, seed))
    avails = [f["kpi"]["availability"] for f in frames]
    peak = max(f["kpi"]["active"] for f in frames)
    return {
        "nodes": nodes, "edges": edges, "frames": frames,
        "summary": {
            "turns": turns, "nodes": len(nodes),
            "threats_injected": frames[-1]["kpi"]["injected"],
            "threats_neutralised": frames[-1]["kpi"]["mitigated"],
            "residual_active": frames[-1]["kpi"]["active"],
            "min_availability": round(min(avails), 3),
            "end_availability": round(avails[-1], 3),
            "peak_concurrent_threats": peak,
            "held": frames[-1]["kpi"]["active"] == 0,
        },
    }


if __name__ == "__main__":
    r = run_campaign()
    s = r["summary"]
    print(f"theater: {s['nodes']} nodes · {s['turns']} turns")
    print(f"threats: injected={s['threats_injected']}  neutralised={s['threats_neutralised']}  "
          f"residual={s['residual_active']}")
    print(f"availability: min={s['min_availability']:.0%}  end={s['end_availability']:.0%}  "
          f"peak concurrent threats={s['peak_concurrent_threats']}  held={s['held']}")
    print("\navailability by turn (every 5):")
    for f in r["frames"][::5]:
        bar = "█" * int(f["kpi"]["availability"] * 30)
        print(f"  t{f['turn']:>2} {f['kpi']['availability']:>4.0%} {bar}  active={f['kpi']['active']:>2}"
              f"  {' / '.join(f['waves']) or 'consolidation'}")
