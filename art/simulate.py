"""Exact decimal arithmetic over SYNTHETIC STAND-IN workloads."""
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

from art import BANNER
from art.router import RoutingError, route, validate_task


class WorkloadError(ValueError):
    pass


def load_workload(path):
    try:
        tasks = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WorkloadError(f"WorkloadError: {exc}") from exc
    if not isinstance(tasks, list):
        raise WorkloadError("WorkloadError: root must be a JSON list")
    return tasks


def simulate(tasks, profiles):
    totals = {key: Decimal(0) for key in ("routed", "premium", "cheapest")}
    violations = {key: 0 for key in totals}
    counts = Counter()
    decisions = []
    premium = next((p for p in profiles if p.name == "hosted-premium"), None)
    if premium is None:
        raise WorkloadError("WorkloadError: always-premium baseline requires hosted-premium")
    cheapest = min(profiles, key=lambda p: (p.cost, p.latency_ms, p.name))
    for index, task in enumerate(tasks):
        try:
            if not isinstance(task, dict):
                raise ValueError("entry must be an object")
            for key in ("task_type", "quality_floor"):
                if key not in task:
                    raise ValueError(f"missing field {key}")
            floor = validate_task(task["task_type"], task["quality_floor"], profiles)
            decision = route(task["task_type"], floor, profiles)
        except (ValueError, RoutingError) as exc:
            raise WorkloadError(f"WorkloadError: entry index {index}: {exc}") from exc
        decisions.append(decision)
        counts[decision["chosen_profile"]] += 1
        totals["routed"] += Decimal(decision["estimated_cost_usd"])
        for key, p in (("premium", premium), ("cheapest", cheapest)):
            totals[key] += p.cost
            violations[key] += int(task["task_type"] not in p.supports or p.quality < floor)
    savings = totals["premium"] - totals["routed"]
    percent = savings / totals["premium"] * 100 if totals["premium"] else Decimal(0)
    leader = min(counts, key=lambda name: (-counts[name], name)) if counts else None
    return {"totals": totals, "violations": violations, "savings_usd": savings,
            "savings_percent": percent, "counts": dict(sorted(counts.items())), "decisions": decisions,
            "leader": leader, "leader_share": Decimal(counts[leader]) / len(tasks) * 100 if leader else Decimal(0)}


def render_simulation(result):
    lines = [BANNER, "Policy             Total USD  Quality-floor/support violations"]
    for key, label in (("routed", "Routed"), ("premium", "Always-premium"), ("cheapest", "Always-cheapest")):
        lines.append(f"{label:18} {result['totals'][key]:.4f}     {result['violations'][key]}")
    lines.append(f"Savings: USD {result['savings_usd']:.4f} ({result['savings_percent']:.2f}%)")
    lines.append(f"Zero routed quality-floor violations: {result['violations']['routed'] == 0}")
    lines.append(f"Highest selection share: {result['leader'] or 'none'} ({result['leader_share']:.2f}%)")
    return "\n".join(lines)
