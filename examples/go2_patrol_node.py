"""Go2 patrol node — walks between waypoints and publishes position.

Hot-push with:
    ros_push_node("go2_patrol", script)

Publishes JSON on /go2/position after each move.
"""
import json
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from kongnitive_ros2_edgemcp.core.vector_bridge import get_agent
from kongnitive_ros2_edgemcp.core.node_log import node_log

NODE_NAME = "go2_patrol"

# Kitchen island area waypoints (IK-safe for arm reach)
WAYPOINTS = [
    {"x": 16.0, "y": 1.8},   # in front of island
    {"x": 17.5, "y": 1.8},   # right side of island
    {"x": 16.0, "y": 3.5},   # behind island
]


class Go2PatrolNode(Node):
    def __init__(self):
        super().__init__("go2_patrol")
        self.agent = get_agent()
        self.pub = self.create_publisher(String, "/go2/position", 10)
        self._wp_idx = 0
        self._done = False
        self.timer = self.create_timer(1.0, self._first_run)
        self.get_logger().info("[INIT] Go2 patrol node ready")

    def _first_run(self):
        self.timer.cancel()
        self._patrol_loop()

    def _patrol_loop(self):
        if self._done:
            return

        for i, wp in enumerate(WAYPOINTS):
            self.get_logger().info(f"[NAV] Moving to waypoint {i}: ({wp['x']}, {wp['y']})")
            result = self.agent.execute_skill("navigate", wp)
            node_log(NODE_NAME, {
                "skill": "navigate",
                "success": result.success,
                "failure_reason": result.failure_reason,
                "waypoint": wp,
            })

            # Publish position
            pos = self.agent.get_position()
            heading = self.agent.get_heading()
            msg = String()
            msg.data = json.dumps({"x": pos[0], "y": pos[1], "z": pos[2], "heading": heading})
            self.pub.publish(msg)
            self.get_logger().info(f"[POS] x={pos[0]:.2f} y={pos[1]:.2f} heading={heading:.2f}")

        self._done = True
        node_log(NODE_NAME, {"skill": "goal", "success": True, "status": "patrol complete"})
        self.get_logger().info("[SUCCESS] Patrol complete")


def create_node():
    return Go2PatrolNode()
