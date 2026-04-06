"""
Kongnitive ROS2 EdgeMCP Server

FastMCP server that enables AI-driven hot-swapping of ROS2 nodes.
"""

import logging
import sys
from pathlib import Path
from typing import Any, Optional

from fastmcp import FastMCP

from kongnitive_ros2_edgemcp.core.episode_manager import EpisodeManager
from kongnitive_ros2_edgemcp.core.node_manager import NodeManager
from kongnitive_ros2_edgemcp.core.success_examples import (
    build_example,
    filter_examples,
    find_success_entries,
    get_store_path,
    load_examples,
    merge_examples,
    upsert_example,
)
from kongnitive_ros2_edgemcp.tools import system_tools, node_tools, episode_tools
from kongnitive_ros2_edgemcp.utils.config_loader import (
    get_config_dir,
    load_server_config,
    load_system_prompt,
)

CONFIG = load_server_config()
SERVER_CONFIG = CONFIG.get("server", {})
NODES_CONFIG = CONFIG.get("nodes", {})
LOGGING_CONFIG = CONFIG.get("logging", {})
EPISODE_CONFIG = CONFIG.get("episode", {})
DEFAULT_LOG_LIMIT = int(LOGGING_CONFIG.get("default_limit", 100))
DEFAULT_EPISODE_STRATEGY = str(EPISODE_CONFIG.get("default_strategy", "hardcoded_v1"))

# Setup logging
log_level_name = str(SERVER_CONFIG.get("log_level", "INFO")).upper()
log_level = getattr(logging, log_level_name, logging.INFO)
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastMCP server
mcp = FastMCP("Kongnitive-ROS2-EdgeMCP")

# Initialize NodeManager
node_manager = None
episode_manager = None


def get_node_manager() -> NodeManager:
    """Get or create NodeManager instance."""
    global node_manager
    if node_manager is None:
        node_manager = NodeManager(
            script_dir=NODES_CONFIG.get("script_dir", "~/.kongnitive_ros2_edgemcp/nodes"),
            max_nodes=int(NODES_CONFIG.get("max_nodes", 10)),
            executor_threads=int(CONFIG.get("ros2", {}).get("executor_threads", 0)),
        )
    return node_manager


def get_episode_manager() -> EpisodeManager:
    """Get or create EpisodeManager instance."""
    global episode_manager
    if episode_manager is None:
        episode_manager = EpisodeManager()
    return episode_manager


def _get_builtin_example_paths() -> list[Path]:
    """Return packaged example node scripts that can seed template reuse."""
    repo_examples_dir = Path(__file__).resolve().parent.parent / "examples"
    if not repo_examples_dir.exists():
        return []
    return sorted(
        path for path in repo_examples_dir.glob("*.py")
        if "create_node()" in path.read_text(encoding="utf-8")
    )


def _collect_session_examples(
    script_dir: Path,
    goal_filter: str = "",
) -> list[dict[str, Any]]:
    """Collect successful examples from saved scripts plus current node logs."""
    from kongnitive_ros2_edgemcp.core.node_log import get_logs  # noqa: PLC0415

    filt = (goal_filter or "").strip().lower()
    examples: list[dict[str, Any]] = []
    for script_path in sorted(script_dir.glob("*.py")):
        node_name = script_path.stem
        logs = get_logs(node_name, limit=200)
        success_entries = find_success_entries(logs)
        if not success_entries:
            continue

        script = script_path.read_text(encoding="utf-8")
        example = build_example(
            node_name=node_name,
            script=script,
            script_path=str(script_path),
            recent_logs=logs,
            source="session",
        )
        if filt:
            filtered = filter_examples([example], goal_filter=filt, limit=1)
            if not filtered:
                continue
        examples.append(example)
    return examples


def _collect_builtin_examples(goal_filter: str = "") -> list[dict[str, Any]]:
    """Collect built-in example node scripts as a last-resort template source."""
    examples: list[dict[str, Any]] = []
    for script_path in _get_builtin_example_paths():
        script = script_path.read_text(encoding="utf-8")
        example = build_example(
            node_name=script_path.stem,
            script=script,
            script_path=str(script_path),
            recent_logs=[],
            source="builtin",
            summary="Packaged example node shipped with Kongnitive ROS2 EdgeMCP.",
        )
        example["has_goal_success"] = False
        if filter_examples([example], goal_filter=goal_filter, limit=1):
            examples.append(example)
    return examples


# ============================================================================
# System Tools
# ============================================================================

@mcp.tool()
async def get_status() -> dict:
    """
    Get comprehensive system status.

    Returns CPU, memory, disk, temperature, and ROS node information.
    Use this to monitor system health and resource usage.

    Returns:
        Dict with system metrics including:
        - CPU usage and frequency
        - Memory usage
        - Disk usage
        - Temperature (if available)
        - Running ROS nodes
    """
    nm = get_node_manager()
    return await system_tools.get_status(nm)


@mcp.tool()
async def get_system_prompt() -> dict:
    """
    Get the system prompt with AI instructions for this project.

    Returns project-level instructions that guide AI behavior when
    working with Kongnitive ROS2 EdgeMCP.

    Returns:
        Dict with system prompt content
    """
    try:
        default_prompt = """
# Kongnitive ROS2 EdgeMCP System Prompt

You are working with Kongnitive ROS2 EdgeMCP, a Jetson-based MCP server for AI-driven
hot-swapping of ROS2 nodes.

## Your Capabilities

1. **Hot-swap ROS2 nodes** - Push Python node scripts that reload instantly
2. **Monitor system** - Check CPU, memory, GPU, temperature
3. **Read logs** - Analyze ROS and system logs
4. **Iterate autonomously** - Read → Analyze → Fix → Verify

## Node Script Requirements

Every node script must:
- Import rclpy and Node
- Define a Node subclass
- Implement create_node() factory function

Example:
```python
import rclpy
from rclpy.node import Node

class MyNode(Node):
    def __init__(self):
        super().__init__('my_node')
        # Your logic here

def create_node():
    return MyNode()
```

## Workflow

1. Use get_status() to understand system state
2. Use sys_get_logs() to diagnose issues
3. Use ros_push_node() to deploy fixes
4. Verify with ros_list_nodes() and logs
5. Iterate until working

## Best Practices

- Keep nodes simple and focused
- Use descriptive node names
- Log important events
- Test incrementally
- Monitor resource usage
- Remember that scan is a robot motion primitive, not scene understanding
- Inspect execution traces, not just top-level success flags
- Reuse known-good node examples when available
"""

        content = load_system_prompt(default_prompt)
        return {
            "status": "success",
            "prompt": content,
            "config_dir": str(get_config_dir()),
        }

    except Exception as e:
        logger.error(f"Failed to get system prompt: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@mcp.tool()
async def sys_get_logs(
    filter: str = None,
    level: str = None,
    source: str = None,
    limit: Optional[int] = DEFAULT_LOG_LIMIT
) -> dict:
    """
    Get system and ROS logs with optional filtering.

    Use this to diagnose issues, monitor node behavior, and verify operations.

    Args:
        filter: Filter by message content (case-insensitive substring match)
        level: Filter by log level (DEBUG, INFO, WARNING, ERROR)
        source: Filter by source (system, node name)
        limit: Maximum number of logs to return (default: 100)

    Returns:
        Dict with log entries, each containing:
        - timestamp: ISO format timestamp
        - level: Log level
        - source: Log source
        - message: Log message
    """
    return await system_tools.sys_get_logs(
        filter_text=filter,
        level=level,
        source=source,
        limit=limit if limit is not None else DEFAULT_LOG_LIMIT
    )


# ============================================================================
# Node Management Tools
# ============================================================================

@mcp.tool()
async def ros_push_node(node_name: str, script: str) -> dict:
    """
    Push and hot-reload a ROS2 node.

    This is the core hot-swap operation. Upload a Python script that defines
    a ROS2 node, and it will be dynamically loaded and started without
    system restart.

    The script MUST define a create_node() function that returns a
    rclpy.node.Node instance.

    Args:
        node_name: Unique identifier for the node
        script: Python source code defining the node

    Returns:
        Status dict indicating success or error

    Example:
        ```python
        script = '''
import rclpy
from rclpy.node import Node

class DetectorNode(Node):
    def __init__(self):
        super().__init__('detector')
        self.get_logger().info('Detector started')

def create_node():
    return DetectorNode()
        '''
        result = await ros_push_node('detector', script)
        ```
    """
    nm = get_node_manager()
    result = await node_tools.ros_push_node(nm, node_name, script)

    # Log the operation
    log_buffer = system_tools.get_log_buffer()
    if result["status"] == "success":
        log_buffer.add("INFO", f"Node '{node_name}' pushed successfully", "system")
    else:
        log_buffer.add("ERROR", f"Failed to push node '{node_name}': {result.get('message')}", "system")

    return result


@mcp.tool()
async def ros_list_nodes() -> dict:
    """
    List all running ROS2 nodes managed by Kongnitive ROS2 EdgeMCP.

    Returns information about each node including name, namespace,
    and script path.

    Returns:
        Dict with node list containing:
        - count: Number of running nodes
        - nodes: List of node info dicts
    """
    nm = get_node_manager()
    return await node_tools.ros_list_nodes(nm)


@mcp.tool()
async def ros_list_capabilities() -> dict:
    """
    Get the runtime control-plane view exposed by this EdgeMCP process.

    This tool reports only what the current runtime can directly observe:
    managed hot-swapped nodes, local vector-os-nano skills, and the
    core ROS topics this project uses for cross-node coordination.

    Returns:
        Dict with runtime-visible managed nodes, agent skills, and topics
    """
    from kongnitive_ros2_edgemcp.core.vector_bridge import get_agent  # noqa: PLC0415

    nm = get_node_manager()
    managed_nodes = await node_tools.ros_list_nodes(nm)
    agent = get_agent()
    topics = [
        {
            "name": "/go2/position",
            "type": "std_msgs/String",
            "description": "Go2 position updates published by patrol-style nodes.",
        },
        {
            "name": "/arm/task_request",
            "type": "std_msgs/String",
            "description": "Task requests for arm-worker nodes (JSON payload in arm base frame).",
        },
        {
            "name": "/arm/task_result",
            "type": "std_msgs/String",
            "description": "Task execution results published by arm-worker nodes.",
        },
        {
            "name": "/world_model/state",
            "type": "std_msgs/String",
            "description": "World state snapshots published by world-model style nodes.",
        },
        {
            "name": "/zone_events",
            "type": "std_msgs/String",
            "description": "Zone change events published by observer-style nodes.",
        },
    ]
    return {
        "status": "success",
        "view": "runtime control-plane",
        "managed_nodes": managed_nodes.get("nodes", []),
        "agent_skills": list(agent.skills),
        "topics": topics,
    }


@mcp.tool()
async def ros_get_node(node_name: str) -> dict:
    """
    Get the source code of a running node.

    Use this to inspect the current implementation of a node before
    making modifications.

    Args:
        node_name: Node identifier

    Returns:
        Dict with script content and path
    """
    nm = get_node_manager()
    return await node_tools.ros_get_node(nm, node_name)


@mcp.tool()
async def ros_get_successful_node_examples(goal_filter: str = "", limit: int = 5) -> dict:
    """
    Get successful ROS2 node examples from persistent storage, current session,
    and packaged fallback templates.

    Success is recognized when a node has at least one `success == True` log entry.
    Examples with a final `skill == "goal"` success are ranked higher.

    Args:
        goal_filter: Optional case-insensitive substring filter applied to node
            name, script, goal/summary fields, and recent logs
        limit: Maximum number of examples to return

    Returns:
        Dict with matched example nodes including script, path, logs, and source
    """
    nm = get_node_manager()
    script_dir = Path(nm.script_dir)
    store_path = get_store_path(script_dir)
    persisted = load_examples(store_path)
    session_examples = _collect_session_examples(script_dir, goal_filter=goal_filter)
    for item in session_examples:
        upsert_example(store_path, item)
    merged = merge_examples(
        filter_examples(session_examples, goal_filter=goal_filter, limit=max(20, limit * 4)),
        filter_examples(persisted, goal_filter=goal_filter, limit=max(20, limit * 4)),
        filter_examples(_collect_builtin_examples(goal_filter), goal_filter=goal_filter, limit=max(20, limit * 4)),
    )
    examples = filter_examples(merged, goal_filter=goal_filter, limit=limit)

    return {
        "status": "success",
        "goal_filter": goal_filter,
        "store_path": str(store_path),
        "count": len(examples),
        "examples": examples,
    }


@mcp.tool()
async def ros_write_successful_node_examples(
    node_name: str,
    goal: str = "",
    summary: str = "",
    tags: Optional[list[str]] = None,
    script: Optional[str] = None,
    logs_limit: int = 200,
) -> dict:
    """
    Persist a successful node example so future sessions can reuse it.

    Args:
        node_name: Node identifier to persist
        goal: Optional user-level goal description for retrieval
        summary: Optional short summary of why this example is useful
        tags: Optional retrieval tags
        script: Optional script override; otherwise read from running/saved node
        logs_limit: Number of recent logs to capture alongside the example

    Returns:
        Dict with the persisted example metadata
    """
    from kongnitive_ros2_edgemcp.core.node_log import get_logs  # noqa: PLC0415

    nm = get_node_manager()
    result = await node_tools.ros_get_node(nm, node_name)
    if result.get("status") != "success":
        script_path = Path(nm.script_dir) / f"{node_name}.py"
        if not script_path.exists() and not script:
            return {
                "status": "error",
                "message": f"Node '{node_name}' not found and no script override provided",
            }
        script_text = script if script is not None else script_path.read_text(encoding="utf-8")
        script_location = str(script_path)
    else:
        script_text = script if script is not None else result["script"]
        script_location = result["script_path"]

    logs = get_logs(node_name, limit=max(1, int(logs_limit)))
    if not find_success_entries(logs):
        return {
            "status": "error",
            "message": (
                f"Node '{node_name}' has no successful log entries. "
                "Only successful nodes can be persisted."
            ),
        }

    example = build_example(
        node_name=node_name,
        script=script_text,
        script_path=script_location,
        recent_logs=logs,
        source="manual",
        goal=goal,
        summary=summary,
        tags=tags,
    )
    store_path = get_store_path(nm.script_dir)
    upsert_example(store_path, example)

    log_buffer = system_tools.get_log_buffer()
    log_buffer.add(
        "INFO",
        f"Persisted successful node example '{node_name}'",
        "system",
    )
    return {
        "status": "success",
        "store_path": str(store_path),
        "example": example,
    }


@mcp.tool()
async def ros_start_node(node_name: str) -> dict:
    """
    Start a previously saved node.

    Loads and starts a node from a previously saved script.

    Args:
        node_name: Node identifier

    Returns:
        Status dict
    """
    nm = get_node_manager()
    result = await node_tools.ros_start_node(nm, node_name)

    log_buffer = system_tools.get_log_buffer()
    if result["status"] == "success":
        log_buffer.add("INFO", f"Node '{node_name}' started", "system")
    else:
        log_buffer.add("ERROR", f"Failed to start node '{node_name}': {result.get('message')}", "system")

    return result


@mcp.tool()
async def ros_stop_node(node_name: str) -> dict:
    """
    Stop a running node.

    Gracefully stops a node and removes it from the executor.

    Args:
        node_name: Node identifier

    Returns:
        Status dict
    """
    nm = get_node_manager()
    result = await node_tools.ros_stop_node(nm, node_name)

    log_buffer = system_tools.get_log_buffer()
    if result["status"] == "success":
        log_buffer.add("INFO", f"Node '{node_name}' stopped", "system")
    else:
        log_buffer.add("ERROR", f"Failed to stop node '{node_name}': {result.get('message')}", "system")

    return result


@mcp.tool()
async def ros_restart_node(node_name: str) -> dict:
    """
    Restart a running node.

    Stops and then starts a node, reloading it from the saved script.

    Args:
        node_name: Node identifier

    Returns:
        Status dict
    """
    nm = get_node_manager()
    result = await node_tools.ros_restart_node(nm, node_name)

    log_buffer = system_tools.get_log_buffer()
    if result["status"] == "success":
        log_buffer.add("INFO", f"Node '{node_name}' restarted", "system")
    else:
        log_buffer.add("ERROR", f"Failed to restart node '{node_name}': {result.get('message')}", "system")

    return result


@mcp.tool()
async def ros_delete_node(node_name: str) -> dict:
    """
    Delete a node: stop it if running and remove its saved script file.

    Use this to permanently remove a node that is no longer needed.

    Args:
        node_name: Node identifier

    Returns:
        Status dict
    """
    nm = get_node_manager()
    result = await node_tools.ros_delete_node(nm, node_name)

    log_buffer = system_tools.get_log_buffer()
    if result["status"] == "success":
        log_buffer.add("INFO", f"Node '{node_name}' deleted", "system")
    else:
        log_buffer.add("ERROR", f"Failed to delete node '{node_name}': {result.get('message')}", "system")

    return result


# ============================================================================
# Episode / AI Iteration Tools
# ============================================================================

@mcp.tool()
async def run_episode(seed: int, profile: dict = None, strategy: str = DEFAULT_EPISODE_STRATEGY) -> dict:
    """
    Run one reproducible pick-and-place episode.

    Args:
        seed: Random seed for deterministic replay
        profile: Optional randomization profile overrides
        strategy: Task strategy id (default: hardcoded_v1)

    Returns:
        Dict with EpisodeResult payload
    """
    em = get_episode_manager()
    result = await episode_tools.run_episode(em, seed=seed, profile=profile, strategy=strategy)
    log_buffer = system_tools.get_log_buffer()
    if result.get("status") == "success":
        summary = result.get("result", {})
        log_buffer.add(
            "INFO",
            f"Episode run_id={summary.get('run_id')} seed={seed} success={summary.get('success')}",
            "episode",
        )
    else:
        log_buffer.add("ERROR", f"run_episode failed for seed={seed}", "episode")
    return result


@mcp.tool()
async def get_metrics(run_id: str) -> dict:
    """
    Get metrics for a run_id plus aggregate summary over all runs.
    """
    em = get_episode_manager()
    return await episode_tools.get_metrics(em, run_id=run_id)


@mcp.tool()
async def get_failure_trace(run_id: str) -> dict:
    """
    Get diagnostic trace for an episode run_id.
    """
    em = get_episode_manager()
    return await episode_tools.get_failure_trace(em, run_id=run_id)


@mcp.tool()
async def ros_get_node_log(node_name: str, limit: int = 50) -> dict:
    """
    Get real-time execution log for a running node.

    Each entry is one skill execution result reported by the node via node_log().
    Entries include: skill name, success/failure, failure reason, timestamp.

    Call this after ros_push_node to observe what the node is doing and whether
    it is achieving the goal. Logs are cleared automatically when a node is
    hot-replaced, so you only see output from the current version.

    Args:
        node_name: Node identifier (same name used in ros_push_node)
        limit: Max number of recent log entries to return (default 50)

    Returns:
        Dict with:
        - status: "success"
        - node_name: the queried node
        - count: number of entries returned
        - entries: list of log dicts, ordered oldest-first
    """
    from kongnitive_ros2_edgemcp.core.node_log import get_logs  # noqa: PLC0415
    entries = get_logs(node_name, limit=limit)
    return {
        "status": "success",
        "node_name": node_name,
        "count": len(entries),
        "entries": entries,
    }


@mcp.tool()
async def patch_and_restart(node_name: str, code: str) -> dict:
    """
    Patch a node script and restart it with automatic rollback on failure.
    """
    nm = get_node_manager()
    result = await episode_tools.patch_and_restart(nm, node_name=node_name, code=code)
    log_buffer = system_tools.get_log_buffer()
    if result.get("status") == "success":
        log_buffer.add("INFO", f"patch_and_restart succeeded for '{node_name}'", "episode")
    else:
        log_buffer.add(
            "ERROR",
            f"patch_and_restart failed for '{node_name}', rolled_back={result.get('rolled_back')}",
            "episode",
        )
    return result


# ============================================================================
# Server Lifecycle
# ============================================================================

def main():
    """Main entry point for Kongnitive ROS2 EdgeMCP server."""
    try:
        system_tools.configure(
            buffer_size=int(LOGGING_CONFIG.get("buffer_size", 1000)),
            default_limit=DEFAULT_LOG_LIMIT,
        )
        logger.info("Starting Kongnitive ROS2 EdgeMCP server...")
        logger.info("Using config directory: %s", get_config_dir())

        # Log startup
        log_buffer = system_tools.get_log_buffer()
        log_buffer.add("INFO", "Kongnitive ROS2 EdgeMCP server starting", "system")

        # Pre-warm vector-os-nano MuJoCo agent (reduces first-call latency)
        try:
            from kongnitive_ros2_edgemcp.core.vector_bridge import get_agent  # noqa: PLC0415
            get_agent()
            logger.info("vector-os-nano merged Go2+Arm MuJoCo agent ready")
            log_buffer.add("INFO", "vector-os-nano merged Go2+Arm MuJoCo agent ready", "system")
        except ImportError:
            logger.warning("vector-os-nano not installed — sim tools unavailable")

        # Run FastMCP server
        mcp.run(transport="stdio")

    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)
    finally:
        # Cleanup
        if node_manager:
            node_manager.shutdown()
        logger.info("Kongnitive ROS2 EdgeMCP server stopped")


if __name__ == "__main__":
    main()
