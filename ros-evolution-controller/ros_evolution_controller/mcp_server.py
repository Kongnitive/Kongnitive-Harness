from __future__ import annotations

import argparse
import json
from pathlib import Path

from .controller import EvolutionController


def build_server(controller: EvolutionController):
    """Build the optional FastMCP adapter without coupling core logic to MCP."""
    try:
        from fastmcp import FastMCP
    except ImportError as error:  # pragma: no cover - environment-specific adapter
        raise RuntimeError("Install the MCP extra: pip install '.[mcp]'") from error

    mcp = FastMCP("ROS Evolution Controller")

    @mcp.tool
    def inspect_runtime() -> dict:
        return controller.inspect_runtime()

    @mcp.tool
    def create_candidate() -> dict:
        return controller.create_candidate()

    @mcp.tool
    def run_validation(candidate_id: str, metrics_json: str, baseline_json: str) -> dict:
        report = controller.run_validation(candidate_id, json.loads(metrics_json), json.loads(baseline_json))
        return report.as_dict()

    @mcp.tool
    def submit_for_approval(candidate_id: str) -> dict:
        return controller.submit_for_approval(candidate_id)

    @mcp.tool
    def approve_candidate(candidate_id: str, note: str, approve_interfaces: bool = False) -> dict:
        return controller.approve_candidate(candidate_id, note, approve_interfaces)

    @mcp.tool
    def promote(candidate_id: str) -> dict:
        return controller.promote(candidate_id)

    @mcp.tool
    def rollback(candidate_id: str, reason: str) -> dict:
        return controller.rollback(candidate_id, reason)

    @mcp.tool
    def monitor(candidate_id: str, metrics_json: str, baseline_json: str) -> dict:
        return controller.monitor(candidate_id, json.loads(metrics_json), json.loads(baseline_json))

    @mcp.tool
    def get_evidence(candidate_id: str) -> list[dict]:
        return controller.store.evidence(candidate_id)

    @mcp.tool
    def search_skills(query: str) -> list[dict]:
        return controller.search_skills(query)

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ROS Evolution Controller MCP server")
    parser.add_argument("--runtime-workspace", required=True, type=Path)
    parser.add_argument("--state-dir", required=True, type=Path)
    args = parser.parse_args()
    build_server(EvolutionController(args.runtime_workspace, args.state_dir)).run()


if __name__ == "__main__":
    main()
