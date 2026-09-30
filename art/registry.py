"""Validated data registry of SYNTHETIC STAND-IN profiles."""
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from art import BANNER


class RegistryError(ValueError):
    pass


@dataclass(frozen=True)
class Profile:
    name: str
    cost: Decimal
    quality: Decimal
    latency_ms: int
    supports: tuple[str, ...]


def load_registry(path=None):
    path = Path(path) if path else Path(__file__).with_name("profiles.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data["profiles"]
        if not isinstance(rows, list) or not rows:
            raise ValueError("profiles must be a nonempty list")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RegistryError(f"RegistryError: {exc}") from exc
    result = []
    names = set()
    for i, row in enumerate(rows):
        name = row.get("name", f"entry {i}") if isinstance(row, dict) else f"entry {i}"
        if not isinstance(row, dict):
            raise RegistryError(f"RegistryError: {name}: profile must be an object")
        for field in ("name", "cost", "quality", "latency_ms", "supports"):
            if field not in row:
                raise RegistryError(f"RegistryError: {name}: missing field {field}")
        try:
            if not isinstance(name, str) or not name or name in names:
                raise ValueError("name must be unique and nonempty")
            cost, quality = Decimal(str(row["cost"])), Decimal(str(row["quality"]))
            if not cost.is_finite() or cost < 0:
                raise ValueError("cost must be finite and nonnegative")
            if not quality.is_finite() or not 0 <= quality <= 1:
                raise ValueError("quality must be between 0 and 1")
            latency = row["latency_ms"]
            if type(latency) is not int or latency < 0:
                raise ValueError("latency_ms must be a nonnegative integer")
            supports = row["supports"]
            if not isinstance(supports, list) or not supports or any(not isinstance(t, str) or not t for t in supports):
                raise ValueError("supports must be a nonempty list of task names")
        except (ValueError, InvalidOperation) as exc:
            raise RegistryError(f"RegistryError: {name}: {exc}") from exc
        names.add(name)
        result.append(Profile(name, cost, quality, latency, tuple(supports)))
    return result


def render_registry(profiles):
    lines = [BANNER, "Profile             USD/task  Quality  Latency ms  Supports"]
    for p in profiles:
        lines.append(f"{p.name:19} {p.cost:.4f}    {p.quality:.2f}     {p.latency_ms:4}        {', '.join(p.supports)}")
    return "\n".join(lines)
