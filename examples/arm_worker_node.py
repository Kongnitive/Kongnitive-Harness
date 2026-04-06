"""Arm worker node — subscribes to task requests, executes pick/place.

Hot-push with:
    ros_push_node("arm_worker", script)

Subscribes to /arm/task_request, publishes results on /arm/task_result.
"""
import json
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from kongnitive_ros2_edgemcp.core.vector_bridge import get_agent
from kongnitive_ros2_edgemcp.core.node_log import node_log

NODE_NAME = "arm_worker"

PICK_LABELS = ["lego", "mug", "banana", "bottle", "duck", "screwdriver"]


class ArmWorkerNode(Node):
    def __init__(self):
        super().__init__("arm_worker")
        self.agent = get_agent()
        self.sub = self.create_subscription(
            String, "/arm/task_request", self._on_task, 10,
        )
        self.pub = self.create_publisher(String, "/arm/task_result", 10)
        self.get_logger().info("[INIT] Arm worker ready, waiting for tasks on /arm/task_request")

    def _on_task(self, msg: String):
        try:
            task = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().error(f"[ERROR] Invalid JSON: {msg.data}")
            return

        action = task.get("action", "pick_and_place")
        obj_label = task.get("object", PICK_LABELS[0])
        place_at = task.get("place_at")

        self.get_logger().info(f"[TASK] {action} object='{obj_label}'")

        if place_at is None:
            reason = "Task request must include place_at in arm base-frame coordinates"
            node_log(NODE_NAME, {"skill": "goal", "success": False, "failure_reason": reason})
            self._publish_result(action, obj_label, False, reason)
            self.get_logger().error(f"[ERROR] {reason}")
            return

        # Home first
        self.agent.execute_skill("home", {})

        # Detect
        det = self.agent.execute_skill("detect", {"query": obj_label})
        node_log(NODE_NAME, {
            "skill": "detect",
            "success": det.success,
            "failure_reason": det.failure_reason,
        })

        # Pick
        pick = self.agent.execute_skill("pick", {"object_label": obj_label, "mode": "hold"})
        node_log(NODE_NAME, {"skill": "pick", "success": pick.success,
                             "failure_reason": pick.failure_reason})

        if not pick.success:
            self._publish_result(action, obj_label, False, pick.failure_reason)
            return

        # Place
        if isinstance(place_at, dict):
            place_params = place_at
        else:
            place_params = {"x": place_at[0], "y": place_at[1], "z": place_at[2]}

        place = self.agent.execute_skill("place", place_params)
        node_log(NODE_NAME, {"skill": "place", "success": place.success,
                             "failure_reason": place.failure_reason})

        self._publish_result(action, obj_label, place.success, place.failure_reason)

        # Home
        self.agent.execute_skill("home", {})

        node_log(NODE_NAME, {
            "skill": "goal",
            "success": place.success,
            "failure_reason": place.failure_reason,
        })
        self.get_logger().info(f"[{'SUCCESS' if place.success else 'FAIL'}] {action} {obj_label}")

    def _publish_result(self, action, obj, success, reason=None):
        msg = String()
        msg.data = json.dumps({
            "action": action, "object": obj,
            "success": success, "failure_reason": reason,
        })
        self.pub.publish(msg)


def create_node():
    return ArmWorkerNode()
