from __future__ import annotations

import argparse
import json
from pathlib import Path

from .controller import EvolutionController


def main() -> None:
    parser = argparse.ArgumentParser(description="ROS Evolution Controller operator CLI")
    parser.add_argument("--runtime-workspace", required=True, type=Path)
    parser.add_argument("--state-dir", required=True, type=Path)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("inspect")
    subcommands.add_parser("create-candidate")
    approve = subcommands.add_parser("approve")
    approve.add_argument("candidate_id")
    approve.add_argument("--note", required=True)
    approve.add_argument("--approve-interfaces", action="store_true")
    promote = subcommands.add_parser("promote")
    promote.add_argument("candidate_id")
    rollback = subcommands.add_parser("rollback")
    rollback.add_argument("candidate_id")
    rollback.add_argument("--reason", required=True)
    monitor = subcommands.add_parser("monitor")
    monitor.add_argument("candidate_id")
    monitor.add_argument("--metrics", required=True, help="JSON object of live metrics")
    monitor.add_argument("--baseline", required=True, help="JSON object of approved baseline metrics")
    args = parser.parse_args()

    controller = EvolutionController(args.runtime_workspace, args.state_dir)
    if args.command == "inspect":
        output = controller.inspect_runtime()
    elif args.command == "create-candidate":
        output = controller.create_candidate()
    elif args.command == "approve":
        output = controller.approve_candidate(args.candidate_id, args.note, args.approve_interfaces)
    elif args.command == "promote":
        output = controller.promote(args.candidate_id)
    elif args.command == "rollback":
        output = controller.rollback(args.candidate_id, args.reason)
    else:
        output = controller.monitor(args.candidate_id, json.loads(args.metrics), json.loads(args.baseline))
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
