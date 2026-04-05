"""
Demo: AI-driven ROS2 node hot-pushed into kongnitive that controls
MuJoCo simulation via vector-os-nano.

This template shows the complete pattern for an AI-iterable robot strategy node:
  1. get_agent()      — shared MuJoCo Agent singleton
  2. execute_skill()  — real physics execution
  3. node_log()       — report results so AI can read via ros_get_node_log

Push this node with:
    ros_push_node(node_name="vector_demo", script=<content of this file>)

Then read the log:
    ros_get_node_log("vector_demo")

Iterate with:
    patch_and_restart("vector_demo", <updated script>)
"""

import rclpy
from rclpy.node import Node
from kongnitive_ros2_edgemcp.core.vector_bridge import get_agent
from kongnitive_ros2_edgemcp.core.node_log import node_log


class VectorSimDemoNode(Node):
    """Picks the red lego, places it to the left, returns home. Repeats every 10s.

    Logs each skill result so the AI can observe success/failure and iterate.
    """

    def __init__(self):
        super().__init__("vector_sim_demo")
        self.agent = get_agent()
        self._iteration = 0
        self.timer = self.create_timer(10.0, self._run_episode)
        self.get_logger().info("VectorSimDemoNode ready — MuJoCo sim active")
        self.get_logger().info(f"Available skills: {self.agent.skills}")

    def _run_episode(self):
        self._iteration += 1
        self.get_logger().info(f"=== Episode {self._iteration} ===")

        # Step 1: Move to scan position
        self._exec("scan", {})

        # Step 2: Detect the target object
        if not self._exec("detect", {"query": "red lego"}):
            return

        # Step 3: Pick it up
        if not self._exec("pick", {"object_label": "red lego"}):
            return

        # Step 4: Place to the left (-x side)
        self._exec("place", {"x": -0.25, "y": 0.0, "z": 0.05})

    def _exec(self, skill: str, params: dict) -> bool:
        """Execute one skill, log the result, return success."""
        result = self.agent.execute_skill(skill, params)
        node_log(self.get_name(), {
            "iteration": self._iteration,
            "skill": skill,
            "params": params,
            "success": result.success,
            "status": result.status,
            "failure_reason": result.failure_reason,
            "steps_completed": result.steps_completed,
            "steps_total": result.steps_total,
        })
        flag = "OK" if result.success else f"FAIL — {result.failure_reason}"
        self.get_logger().info(f"  {skill}: {flag}")
        return result.success


def create_node():
    return VectorSimDemoNode()


# Standalone testing (outside kongnitive)
if __name__ == "__main__":
    rclpy.init()
    node = create_node()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
