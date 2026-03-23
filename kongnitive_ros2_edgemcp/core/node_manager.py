"""
NodeManager - Core hot-swap engine for ROS2 nodes

Manages dynamic loading, unloading, and hot-swapping of ROS2 nodes
using Python importlib and MultiThreadedExecutor.
"""

import importlib.util
import sys
from pathlib import Path
from threading import Thread, Lock
from typing import Dict, Any
import logging

try:
    import rclpy
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.node import Node
except ImportError:
    # Allow import without ROS2 for testing
    rclpy = None
    MultiThreadedExecutor = None
    Node = None

logger = logging.getLogger(__name__)


class NodeManager:
    """
    Manages ROS2 node lifecycle with hot-swap capability.

    Features:
    - Dynamic Python module loading via importlib
    - Zero-downtime node replacement (<100ms)
    - MultiThreadedExecutor for runtime node management
    - Persistent script storage
    """

    def __init__(
        self,
        script_dir: str = "~/.kongnitive_ros2_edgemcp/nodes",
        max_nodes: int = 10,
        executor_threads: int = 0,
    ):
        """
        Initialize NodeManager.

        Args:
            script_dir: Directory to store node scripts
            max_nodes: Maximum number of concurrently running nodes
            executor_threads: Number of executor threads (0 = use ROS2 default)
        """
        if rclpy is None:
            raise ImportError("rclpy not available. Install ROS2 Humble.")

        # Initialize ROS2
        if not rclpy.ok():
            rclpy.init()

        # Setup script storage
        self.script_dir = Path(script_dir).expanduser()
        self.script_dir.mkdir(parents=True, exist_ok=True)
        self.max_nodes = max(1, int(max_nodes))

        # Node registry: {node_name: {'instance': Node, 'module': Module, 'script_path': Path}}
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.lock = Lock()

        # Create and start executor
        if executor_threads and int(executor_threads) > 0:
            self.executor = MultiThreadedExecutor(num_threads=int(executor_threads))
        else:
            self.executor = MultiThreadedExecutor()
        self.executor_thread = Thread(target=self._spin_executor, daemon=True)
        self.executor_thread.start()

        logger.info(
            "NodeManager initialized. Script dir: %s, max_nodes: %s",
            self.script_dir,
            self.max_nodes,
        )

    def _spin_executor(self):
        """Background thread to spin the executor."""
        try:
            self.executor.spin()
        except Exception as e:
            logger.error(f"Executor spin error: {e}")

    async def push_node(self, node_name: str, script: str) -> Dict[str, Any]:
        """
        Push and hot-reload a ROS2 node.

        This is the core hot-swap operation:
        1. Save script to disk
        2. Unload existing node if present
        3. Dynamically import new module
        4. Create node instance
        5. Add to executor (hot-swap!)

        Args:
            node_name: Unique node identifier
            script: Python source code (must have create_node() function)

        Returns:
            Status dict with success/error info
        """
        with self.lock:
            try:
                # 1. Save script
                script_path = self.script_dir / f"{node_name}.py"
                script_path.write_text(script)
                logger.info(f"Saved script: {script_path}")

                # 2. Unload if exists
                if node_name in self.nodes:
                    await self._unload_node(node_name)
                elif len(self.nodes) >= self.max_nodes:
                    return {
                        "status": "error",
                        "node_name": node_name,
                        "message": f"Max node limit reached ({self.max_nodes})"
                    }

                # 3. Dynamic import
                spec = importlib.util.spec_from_file_location(node_name, script_path)
                if spec is None or spec.loader is None:
                    return {
                        "status": "error",
                        "message": f"Failed to load module spec for {node_name}"
                    }

                module = importlib.util.module_from_spec(spec)
                sys.modules[node_name] = module
                spec.loader.exec_module(module)

                # 4. Create node (script must have create_node() function)
                if not hasattr(module, 'create_node'):
                    return {
                        "status": "error",
                        "message": "Script must define create_node() function"
                    }

                node_instance = module.create_node()

                if not isinstance(node_instance, Node):
                    return {
                        "status": "error",
                        "message": "create_node() must return rclpy.node.Node instance"
                    }

                # 5. Add to executor (hot-swap!)
                self.executor.add_node(node_instance)

                # Register
                self.nodes[node_name] = {
                    'instance': node_instance,
                    'module': module,
                    'script_path': script_path
                }

                logger.info(f"Node '{node_name}' hot-swapped successfully")

                return {
                    "status": "success",
                    "node_name": node_name,
                    "script_path": str(script_path),
                    "message": f"Node '{node_name}' loaded and running"
                }

            except Exception as e:
                logger.error(f"Failed to push node '{node_name}': {e}")
                return {
                    "status": "error",
                    "node_name": node_name,
                    "message": str(e)
                }

    async def _unload_node(self, node_name: str):
        """
        Unload a running node.

        Args:
            node_name: Node to unload
        """
        if node_name not in self.nodes:
            return

        node_info = self.nodes[node_name]
        node_instance = node_info['instance']

        # Remove from executor
        self.executor.remove_node(node_instance)

        # Destroy node
        node_instance.destroy_node()

        # Remove from registry
        del self.nodes[node_name]

        # Clean up module
        if node_name in sys.modules:
            del sys.modules[node_name]

        logger.info(f"Node '{node_name}' unloaded")

    async def list_nodes(self) -> Dict[str, Any]:
        """
        List all running nodes.

        Returns:
            Dict with node list and metadata
        """
        with self.lock:
            nodes_list = []
            for node_name, node_info in self.nodes.items():
                node_instance = node_info['instance']
                nodes_list.append({
                    "name": node_name,
                    "ros_node_name": node_instance.get_name(),
                    "namespace": node_instance.get_namespace(),
                    "script_path": str(node_info['script_path'])
                })

            return {
                "status": "success",
                "count": len(nodes_list),
                "nodes": nodes_list
            }

    async def get_node_script(self, node_name: str) -> Dict[str, Any]:
        """
        Get the source code of a node.

        Args:
            node_name: Node identifier

        Returns:
            Dict with script content
        """
        with self.lock:
            if node_name not in self.nodes:
                return {
                    "status": "error",
                    "message": f"Node '{node_name}' not found"
                }

            script_path = self.nodes[node_name]['script_path']
            script_content = script_path.read_text()

            return {
                "status": "success",
                "node_name": node_name,
                "script": script_content,
                "script_path": str(script_path)
            }

    async def start_node(self, node_name: str) -> Dict[str, Any]:
        """
        Start a previously saved node.

        Args:
            node_name: Node identifier

        Returns:
            Status dict
        """
        script_path = self.script_dir / f"{node_name}.py"
        if not script_path.exists():
            return {
                "status": "error",
                "message": f"No saved script for node '{node_name}'"
            }

        script = script_path.read_text()
        return await self.push_node(node_name, script)

    async def stop_node(self, node_name: str) -> Dict[str, Any]:
        """
        Stop a running node.

        Args:
            node_name: Node identifier

        Returns:
            Status dict
        """
        with self.lock:
            if node_name not in self.nodes:
                return {
                    "status": "error",
                    "message": f"Node '{node_name}' not running"
                }

            await self._unload_node(node_name)

            return {
                "status": "success",
                "node_name": node_name,
                "message": f"Node '{node_name}' stopped"
            }

    async def restart_node(self, node_name: str) -> Dict[str, Any]:
        """
        Restart a running node.

        Args:
            node_name: Node identifier

        Returns:
            Status dict
        """
        # Stop then start
        stop_result = await self.stop_node(node_name)
        if stop_result["status"] == "error":
            return stop_result

        return await self.start_node(node_name)

    def shutdown(self):
        """Shutdown the NodeManager and all nodes."""
        with self.lock:
            # Stop all nodes
            for node_name in list(self.nodes.keys()):
                self.executor.remove_node(self.nodes[node_name]['instance'])
                self.nodes[node_name]['instance'].destroy_node()

            self.nodes.clear()

        # Shutdown executor
        self.executor.shutdown()

        # Shutdown ROS2
        if rclpy.ok():
            rclpy.shutdown()

        logger.info("NodeManager shutdown complete")
