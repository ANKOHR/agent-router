"""Offline command line interface."""
import argparse
import json
import sys

from art import BANNER
from art.audit import append_decision, read_audit
from art.fixtures import write_fixtures
from art.registry import load_registry, render_registry
from art.router import render_decision, route
from art.simulate import load_workload, render_simulation, simulate


def main(argv=None):
    parser = argparse.ArgumentParser(description=BANNER)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("route", "simulate", "audit", "registry", "fixtures"):
        p = sub.add_parser(command, description=BANNER)
        if command in ("route", "simulate", "audit"):
            p.add_argument("--store", help="Audit directory (default: ~/.art)")
        if command in ("route", "simulate", "registry"):
            p.add_argument("--profiles", help="Replacement synthetic registry JSON")
        if command == "route":
            p.add_argument("--task-type", required=True)
            p.add_argument("--quality-floor", required=True)
        elif command == "simulate":
            p.add_argument("--workload", required=True)
        elif command == "audit":
            p.add_argument("--format", choices=("text", "json"), default="text")
        elif command == "fixtures":
            p.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "audit":
            records = read_audit(args.store)
            if args.format == "json":
                print(json.dumps({"label": BANNER, "decisions": records}, indent=2, sort_keys=True))
            else:
                print(BANNER)
                for d in records:
                    print(f"{d['timestamp']} | task {d['task_type']} | floor {d['quality_floor']}")
                    print(render_decision(d))
        elif args.command == "fixtures":
            print(BANNER)
            print(f"Fixed seed 31, 50 tasks: {write_fixtures(args.out)}")
        else:
            profiles = load_registry(args.profiles)
            if args.command == "registry":
                print(render_registry(profiles))
            elif args.command == "route":
                decision = route(args.task_type, args.quality_floor, profiles)
                append_decision(decision, args.store)
                print(BANNER)
                print(render_decision(decision))
            else:
                result = simulate(load_workload(args.workload), profiles)
                for decision in result["decisions"]:
                    append_decision(decision, args.store)
                print(render_simulation(result))
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
