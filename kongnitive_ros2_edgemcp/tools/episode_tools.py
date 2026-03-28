"""
Episode tools for reproducible simulation and AI repair loop.
"""

from pathlib import Path
from typing import Any, Dict, Optional


async def run_episode(
    episode_manager,
    seed: int,
    profile: Optional[Dict[str, Any]] = None,
    strategy: str = "hardcoded_v1",
) -> Dict[str, Any]:
    return await episode_manager.run_episode(seed=seed, profile=profile, strategy=strategy)


async def get_metrics(episode_manager, run_id: str) -> Dict[str, Any]:
    return await episode_manager.get_metrics(run_id=run_id)


async def get_failure_trace(episode_manager, run_id: str) -> Dict[str, Any]:
    return await episode_manager.get_failure_trace(run_id=run_id)


async def patch_and_restart(node_manager, node_name: str, code: str) -> Dict[str, Any]:
    """
    Patch node source and restart with rollback on failure.

    If the patch fails to load, the previous script is restored.
    """
    previous_script = None
    script_path = Path(node_manager.script_dir) / f"{node_name}.py"
    if script_path.exists():
        previous_script = script_path.read_text(encoding="utf-8")
    elif node_name in node_manager.nodes:
        node_result = await node_manager.get_node_script(node_name)
        if node_result.get("status") == "success":
            previous_script = node_result.get("script")

    patch_result = await node_manager.push_node(node_name, code)
    if patch_result.get("status") == "success":
        return {
            "status": "success",
            "node_name": node_name,
            "rolled_back": False,
            "message": "Patch applied and node restarted",
        }

    if previous_script is None:
        return {
            "status": "error",
            "node_name": node_name,
            "rolled_back": False,
            "message": patch_result.get("message", "Patch failed and no rollback script available"),
        }

    rollback_result = await node_manager.push_node(node_name, previous_script)
    return {
        "status": "error",
        "node_name": node_name,
        "rolled_back": rollback_result.get("status") == "success",
        "message": patch_result.get("message", "Patch failed"),
        "rollback_message": rollback_result.get("message"),
    }
