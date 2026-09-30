"""SYNTHETIC STAND-IN policy and offline CLI verification."""
import json
import subprocess
import sys
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

import pytest

from art.audit import AuditError, append_decision, read_audit
from art.fixtures import generate_workload, write_fixtures
from art.registry import RegistryError, load_registry, render_registry
from art.router import RoutingError, render_decision, route
from art.simulate import WorkloadError, load_workload, render_simulation, simulate


@pytest.fixture
def profiles():
    return load_registry()


@pytest.mark.parametrize("task,floor,expected", [
    ("classify", "0.60", "local-tiny"),
    ("summarize", "0.75", "local-small"),
    ("qa", "0.85", "tool-codeexec"),
    ("search", "0.85", "tool-websearch"),
    ("code", "0.90", "hosted-standard"),
])
def test_route_picks_cheapest_qualifying(profiles, task, floor, expected):
    decision = route(task, floor, profiles)
    assert decision["chosen_profile"] == expected
    assert len(decision["rejected"]) == 5
    for rejection in decision["rejected"]:
        p = next(p for p in profiles if p.name == rejection["profile"])
        expected_reason = ("unsupported task type" if task not in p.supports else
                           "below floor" if p.quality < D(floor) else "more expensive")
        assert rejection["reason"].startswith(expected_reason)
    assert "Cheapest supporting profile" in decision["justification"]


def test_route_enforces_floor(profiles):
    d = route("qa", ".95", profiles)
    assert d["chosen_profile"] == "hosted-premium"
    explanation = render_decision(d)
    for p in profiles:
        if p.name != "hosted-premium":
            assert f"Rejected {p.name}:" in explanation


def test_route_task_type_support(profiles):
    assert route("search", 0, profiles)["chosen_profile"] == "tool-websearch"
    assert route("code", 0, profiles)["chosen_profile"] == "tool-codeexec"


def test_route_tiebreak(profiles):
    base = profiles[0]
    candidates = [replace(base, name="a", latency_ms=200), replace(base, name="z", latency_ms=100)]
    assert route("classify", .6, candidates)["chosen_profile"] == "z"
    assert "higher latency" in route("classify", .6, candidates)["rejected"][0]["reason"]
    candidates.append(replace(base, name="b", latency_ms=100))
    assert route("classify", .6, candidates)["chosen_profile"] == "b"
    assert "later name" in render_decision(route("classify", .6, candidates))


def test_route_no_qualifier(profiles):
    with pytest.raises(RoutingError, match="NoQualifyingProfile:.*max available quality 0.97, closest profile hosted-premium"):
        route("qa", .99, profiles)
    with pytest.raises(RoutingError, match="UnknownTaskType:.*supported types: classify, code, qa, search, summarize"):
        route("unsupported", .99, profiles)


def test_simulate_math(profiles):
    tasks = [{"task_type": t, "quality_floor": f} for t, f in
             [("classify", ".6"), ("summarize", ".75"), ("qa", ".85"), ("search", ".85"), ("code", ".9")]]
    r = simulate(tasks, profiles)
    # Hand sum: .0002 + .0010 + .0020 + .0040 + .0120 = .0192.
    assert r["totals"]["routed"] == D(".0192")
    assert r["totals"]["premium"] == D(".3000")
    assert r["savings_usd"] == D(".2808")
    assert r["savings_percent"] == D("93.6")


def test_simulate_violation_counts(profiles):
    r = simulate(generate_workload(), profiles)
    assert r["violations"] == {"routed": 0, "premium": 0, "cheapest": 43}


def test_shipped_workload_hand_computation(profiles):
    r = simulate(generate_workload(), profiles)
    expected = {"local-tiny": 7, "local-small": 13, "tool-codeexec": 9,
                "tool-websearch": 7, "hosted-standard": 10, "hosted-premium": 4}
    assert r["counts"] == expected
    # Independent count-times-price hand calculation.
    total = 7*D(".0002") + 13*D(".0010") + 9*D(".0020") + 7*D(".0040") + 10*D(".0120") + 4*D(".0600")
    assert total == r["totals"]["routed"] == D(".4204")
    assert r["totals"]["premium"] == 50*D(".0600")
    assert r["savings_percent"] == (D(3)-total)/D(3)*100
    assert r["leader"] == "local-small" and r["leader_share"] == 26


def test_audit_logged(profiles, tmp_path):
    d = route("qa", ".9", profiles)
    record = append_decision(d, tmp_path)
    assert read_audit(tmp_path) == [record]
    assert record["rejected"] == d["rejected"]
    assert record["timestamp"].endswith("+00:00")
    out = cli("audit", "--store", str(tmp_path))
    assert record["timestamp"] in out.stdout
    assert "Rejected local-tiny" in out.stdout
    data = json.loads(cli("audit", "--store", str(tmp_path), "--format", "json").stdout)
    assert data["decisions"] == [record]
    append_decision(d, tmp_path)
    assert len(read_audit(tmp_path)) == 2


def test_registry_carries_synthetic_banner(profiles):
    assert "SYNTHETIC STAND-IN" in render_registry(profiles)
    assert len(profiles) == 6


def test_fixtures_deterministic(tmp_path):
    a, b = write_fixtures(tmp_path / "a"), write_fixtures(tmp_path / "b")
    assert a.read_bytes() == b.read_bytes()
    assert len(load_workload(a)) == 50
    assert all("SYNTHETIC" in t["label"] for t in load_workload(a))


def cli(*args):
    return subprocess.run([sys.executable, "-m", "art.cli", *args], capture_output=True, text=True)


@pytest.mark.parametrize("command", ["route", "simulate", "audit", "registry", "fixtures"])
def test_cli_help(command):
    result = cli(command, "--help")
    assert result.returncode == 0 and "SYNTHETIC STAND-IN" in result.stdout


def test_cli_smoke_and_end_to_end(tmp_path):
    store = str(tmp_path / "store")
    assert cli("fixtures", "--out", str(tmp_path)).returncode == 0
    result = cli("simulate", "--workload", str(tmp_path / "workload.json"), "--store", store)
    assert result.returncode == 0
    assert "0.4204" in result.stdout and "85.99%" in result.stdout
    assert "Zero routed quality-floor violations: True" in result.stdout
    assert "local-small (26.00%)" in result.stdout
    assert len(read_audit(store)) == 50
    args = ("route", "--task-type", "qa", "--quality-floor", ".9", "--store", store)
    first, second = cli(*args), cli(*args)
    assert first.returncode == 0 and first.stdout == second.stdout
    assert "Chosen: hosted-standard" in first.stdout
    assert cli("registry").returncode == 0
    assert cli("audit", "--store", store).returncode == 0


@pytest.mark.parametrize("floor", ["1.5", "-0.1", "NaN", "Infinity", "bad"])
def test_invalid_floor(profiles, floor, tmp_path):
    with pytest.raises(RoutingError, match="InvalidQualityFloor"):
        route("qa", floor, profiles)
    result = cli("route", "--task-type", "qa", "--quality-floor", floor, "--store", str(tmp_path))
    assert result.returncode != 0 and "InvalidQualityFloor" in result.stderr
    assert not (tmp_path / "audit.jsonl").exists()


def test_unknown_task_cli(tmp_path):
    result = cli("route", "--task-type", "alien", "--quality-floor", ".5", "--store", str(tmp_path))
    assert result.returncode == 2
    assert "UnknownTaskType" in result.stderr and "supported types" in result.stderr


@pytest.mark.parametrize("entry,problem", [(None, "object"), ({"task_type": "qa"}, "quality_floor"),
    ({"task_type": "qa", "quality_floor": 1.5}, "InvalidQualityFloor"),
    ({"task_type": "alien", "quality_floor": .5}, "UnknownTaskType")])
def test_malformed_workload(profiles, tmp_path, entry, problem):
    tasks = [{"task_type": "qa", "quality_floor": .5}, entry]
    with pytest.raises(WorkloadError, match=f"entry index 1:.*{problem}"):
        simulate(tasks, profiles)
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(tasks))
    result = cli("simulate", "--workload", str(path), "--store", str(tmp_path))
    assert result.returncode == 2 and "entry index 1" in result.stderr
    assert not (tmp_path / "audit.jsonl").exists()


@pytest.mark.parametrize("field,value", [("quality", 1.1), ("cost", -1), ("latency_ms", -1), ("supports", []), ("quality", "NaN")])
def test_registry_validation(tmp_path, field, value):
    data = json.loads(Path("art/profiles.json").read_text())
    data["profiles"][0][field] = value
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(data))
    with pytest.raises(RegistryError, match=f"local-tiny:.*{field}"):
        load_registry(path)


def test_registry_missing_field(tmp_path):
    data = json.loads(Path("art/profiles.json").read_text())
    del data["profiles"][0]["cost"]
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(data))
    with pytest.raises(RegistryError, match="local-tiny: missing field cost"):
        load_registry(path)


def test_empty_workload(profiles, tmp_path):
    r = simulate([], profiles)
    assert all(t == 0 for t in r["totals"].values())
    assert r["savings_percent"] == 0
    assert "none (0.00%)" in render_simulation(r)
    path = tmp_path / "empty.json"
    path.write_text("[]")
    output = cli("simulate", "--workload", str(path), "--store", str(tmp_path))
    assert output.returncode == 0 and "USD 0.0000 (0.00%)" in output.stdout


def test_corrupt_files(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{")
    with pytest.raises(WorkloadError):
        load_workload(path)
    with pytest.raises(RegistryError):
        load_registry(path)
    (tmp_path / "audit.jsonl").write_text("{}\n")
    with pytest.raises(AuditError, match="line 1"):
        read_audit(tmp_path)


def test_exact_custom_cost(profiles):
    edited = [replace(p, cost=D(".00012345")) if p.name == "local-tiny" else p for p in profiles]
    assert simulate([{"task_type": "classify", "quality_floor": .6}], edited)["totals"]["routed"] == D(".00012345")
