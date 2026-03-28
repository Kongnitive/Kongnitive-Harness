"""
Kongnitive ROS2 EdgeMCP Server

FastMCP server that enables AI-driven hot-swapping of ROS2 nodes.
"""

import logging
import sys
from typing import Optional

from fastmcp import FastMCP

from kongnitive_ros2_edgemcp.core.episode_manager import EpisodeManager
from kongnitive_ros2_edgemcp.core.node_manager import NodeManager
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
