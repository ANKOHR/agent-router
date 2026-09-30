"""SYNTHETIC workload generator, fixed seed 31."""
import json
import random
from pathlib import Path

SEED = 31
TASK_TYPES = ("classify", "summarize", "qa", "search", "code")
FLOORS = ("0.60", "0.75", "0.85", "0.90", "0.95")


def generate_workload():
    rng = random.Random(SEED)
    return [{"label": "SYNTHETIC STAND-IN workload; fixed seed 31", "task_type": rng.choice(TASK_TYPES), "quality_floor": rng.choice(FLOORS)} for _ in range(50)]


def write_fixtures(out):
    directory = Path(out)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "workload.json"
    path.write_text(json.dumps(generate_workload(), indent=2) + "\n", encoding="utf-8", newline="\n")
    return path
