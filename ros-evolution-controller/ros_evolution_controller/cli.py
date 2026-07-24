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
    candidate = subcommands.add_parser("create-candidate")
    candidate.set_defaults(action="candidate")
    args = parser.parse_args()

    controller = EvolutionController(args.runtime_workspace, args.state_dir)
    if args.command == "inspect":
        output = controller.inspect_runtime()
    else:
        output = controller.create_candidate()
    print(json.dumps(output, indent=2, sort_keys=True))
