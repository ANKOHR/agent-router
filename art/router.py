"""Cheapest capable policy for SYNTHETIC STAND-IN profiles."""
from decimal import Decimal, InvalidOperation


class RoutingError(ValueError):
    pass


def validate_task(task_type, quality_floor, profiles):
    types = sorted({t for p in profiles for t in p.supports})
    if not isinstance(task_type, str) or task_type not in types:
        raise RoutingError(f"UnknownTaskType: {task_type!r}; supported types: {', '.join(types)}")
    try:
        floor = Decimal(str(quality_floor))
        if not floor.is_finite() or not 0 <= floor <= 1:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        raise RoutingError("InvalidQualityFloor: quality_floor must be a finite number between 0 and 1") from None
    return floor


def route(task_type, quality_floor, profiles):
    floor = validate_task(task_type, quality_floor, profiles)
    supported = [p for p in profiles if task_type in p.supports]
    qualified = [p for p in supported if p.quality >= floor]
    if not qualified:
        closest = min(supported, key=lambda p: (-p.quality, p.cost, p.latency_ms, p.name))
        raise RoutingError(f"NoQualifyingProfile: {task_type} floor {floor}; max available quality {closest.quality}, closest profile {closest.name}")
    chosen = min(qualified, key=lambda p: (p.cost, p.latency_ms, p.name))
    rejected = []
    for p in sorted(profiles, key=lambda p: p.name):
        if p == chosen:
            continue
        if task_type not in p.supports:
            reason = "unsupported task type"
        elif p.quality < floor:
            reason = f"below floor ({p.quality} < {floor})"
        elif p.cost > chosen.cost:
            reason = f"more expensive ({p.cost:.4f} > {chosen.cost:.4f} USD/task)"
        elif p.latency_ms > chosen.latency_ms:
            reason = "equal cost; higher latency"
        else:
            reason = "equal cost and latency; later name"
        rejected.append({"profile": p.name, "reason": reason})
    return {"label": "SYNTHETIC STAND-IN", "task_type": task_type, "quality_floor": str(floor),
            "chosen_profile": chosen.name, "estimated_cost_usd": str(chosen.cost),
            "quality": str(chosen.quality), "latency_ms": chosen.latency_ms,
            "justification": "Cheapest supporting profile meeting the floor; ties use lower latency then name.",
            "rejected": rejected}


def render_decision(decision):
    d = decision
    lines = [f"Chosen: {d['chosen_profile']} | USD/task {d['estimated_cost_usd']} | quality {d['quality']} | latency {d['latency_ms']} ms", d["justification"]]
    lines.extend(f"Rejected {r['profile']}: {r['reason']}" for r in d["rejected"])
    return "\n".join(lines)
