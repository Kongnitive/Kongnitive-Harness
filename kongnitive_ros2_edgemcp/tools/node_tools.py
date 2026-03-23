"""
Node management tools for Kongnitive ROS2 EdgeMCP

Provides MCP tools for managing ROS2 nodes.
"""

from typing import Dict, Any


async def ros_push_node(node_manager, node_name: str, script: str) -> Dict[str, Any]:
    """
    Push and hot-reload a ROS2 node.

    This is the core hot-swap operation. The script must define a create_node()
    function that returns a rclpy.node.Node instance.

    Args:
        node_manager: NodeManager instance
        node_name: Unique node identifier
        script: Python source code

    Returns:
        Status dict with success/error info

    Example script:
        ```python
        import rclpy
        from rclpy.node import Node

        class MyNode(Node):
            def __init__(self):
                super().__init__('my_node')
                self.get_logger().info('Node started')

        def create_node():
            return MyNode()
        ```
    """
    return await node_manager.push_node(node_name, script)


async def ros_list_nodes(node_manager) -> Dict[str, Any]:
    """
    List all running ROS2 nodes.

    Args:
        node_manager: NodeManager instance

    Returns:
        Dict with node list and metadata
    """
    return await node_manager.list_nodes()


async def ros_get_node(node_manager, node_name: str) -> Dict[str, Any]:
    """
    Get the source code of a running node.

    Args:
        node_manager: NodeManager instance
        node_name: Node identifier

    Returns:
        Dict with script content
    """
    return await node_manager.get_node_script(node_name)


async def ros_start_node(node_manager, node_name: str) -> Dict[str, Any]:
    """
    Start a previously saved node.

    Args:
        node_manager: NodeManager instance
        node_name: Node identifier

    Returns:
        Status dict
    """
    return await node_manager.start_node(node_name)


async def ros_stop_node(node_manager, node_name: str) -> Dict[str, Any]:
    """
    Stop a running node.

    Args:
        node_manager: NodeManager instance
        node_name: Node identifier

    Returns:
        Status dict
    """
    return await node_manager.stop_node(node_name)


async def ros_restart_node(node_manager, node_name: str) -> Dict[str, Any]:
    """
    Restart a running node.

    Args:
        node_manager: NodeManager instance
        node_name: Node identifier

    Returns:
        Status dict
    """
    return await node_manager.restart_node(node_name)
