"""Append and read local decision records."""
import json
from datetime import datetime, timezone
from pathlib import Path


class AuditError(ValueError):
    pass


def audit_path(store=None):
    return (Path(store) if store else Path.home() / ".art") / "audit.jsonl"


def append_decision(decision, store=None):
    path = audit_path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"timestamp": datetime.now(timezone.utc).isoformat(), **decision}
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def read_audit(store=None):
    path = audit_path(store)
    if not path.exists():
        return []
    records = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        try:
            record = json.loads(line)
            if not isinstance(record, dict) or any(k not in record for k in ("timestamp", "task_type", "quality_floor", "chosen_profile", "rejected", "estimated_cost_usd")):
                raise ValueError("incomplete decision record")
            records.append(record)
        except ValueError as exc:
            raise AuditError(f"AuditError: line {index + 1}: {exc}") from exc
    return records
