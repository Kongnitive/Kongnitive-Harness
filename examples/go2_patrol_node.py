"""Go2 patrol node — walks between waypoints and publishes position.

Hot-push with:
    ros_push_node("go2_patrol", script)

Publishes JSON on /go2/position after each move.
"""
import json
import math
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from kongnitive_ros2_edgemcp.core.vector_bridge import get_agent
from kongnitive_ros2_edgemcp.core.node_log import node_log

NODE_NAME = "go2_patrol"

# Waypoints around the flat arena (objects are scattered at x=0.8~1.5, y=-0.4~0.5)
WAYPOINTS = [
    {"x":  1.0, "y":  0.0},   # approach objects
    {"x":  1.5, "y":  0.5},   # right flank
    {"x":  1.0, "y": -0.5},   # left flank
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
            self.get_logger().info(f"[PATROL] Moving to waypoint {i}: ({wp['x']}, {wp['y']})")
            result = self._move_to_waypoint(wp)
            node_log(NODE_NAME, {
                "skill": "walk",
                "success": result.success,
                "failure_reason": result.failure_reason,
                "waypoint": wp,
            })
            if not result.success:
                node_log(NODE_NAME, {"skill": "goal", "success": False, "failure_reason": result.failure_reason})
                self.get_logger().error(f"[FAIL] Waypoint {i} failed: {result.failure_reason}")
                return

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

    def _move_to_waypoint(self, waypoint):
        pos = self.agent.get_position()
        heading = self.agent.get_heading()
        dx = float(waypoint["x"] - pos[0])
        dy = float(waypoint["y"] - pos[1])
        distance = math.hypot(dx, dy)
        if distance < 0.05:
            return self.agent.execute_skill("where_am_i", {})

        target_heading = math.atan2(dy, dx)
        delta = self._normalize_angle(target_heading - heading)
        if abs(delta) > math.radians(5.0):
            turn_result = self.agent.execute_skill(
                "turn",
                {
                    "direction": "left" if delta >= 0 else "right",
                    "angle": math.degrees(abs(delta)),
                },
            )
            node_log(NODE_NAME, {
                "skill": "turn",
                "success": turn_result.success,
                "failure_reason": turn_result.failure_reason,
                "waypoint": waypoint,
            })
            if not turn_result.success:
                return turn_result

        return self.agent.execute_skill(
            "walk",
            {"direction": "forward", "distance": distance, "speed": 0.3},
        )

    @staticmethod
    def _normalize_angle(angle):
        while angle > math.pi:
            angle -= 2.0 * math.pi
        while angle < -math.pi:
            angle += 2.0 * math.pi
        return angle


def create_node():
    return Go2PatrolNode()
