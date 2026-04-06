"""
Observer node example for hot-swap deployment.

This node demonstrates protocol-level composition:
  1. Subscribe to `/world_model/state`
  2. Infer simple left/center/right zones from object positions
  3. Publish zone change events to `/zone_events`
  4. Report structured events with `node_log()` for AI inspection
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from kongnitive_ros2_edgemcp.core.node_log import node_log

LEFT_THRESHOLD = -0.1
RIGHT_THRESHOLD = 0.1


def _classify_zone(x: float) -> str:
    """Map X position to a coarse zone label."""
    if x < LEFT_THRESHOLD:
        return "left"
    if x > RIGHT_THRESHOLD:
        return "right"
    return "center"


class ObserverNode(Node):
    """Observe world-state updates and emit zone change events."""

    def __init__(self) -> None:
        super().__init__("observer")
        self._zones: dict[str, str] = {}
        self._state_sub = self.create_subscription(
            String, "/world_model/state", self._on_state, 10
        )
        self._event_pub = self.create_publisher(String, "/zone_events", 10)
        self.get_logger().info("ObserverNode ready")

    def _on_state(self, msg: String) -> None:
        """Parse world state snapshots and emit events on zone changes."""
        try:
            state = json.loads(msg.data)
        except json.JSONDecodeError as exc:
            self.get_logger().warn(f"Failed to parse world state JSON: {exc}")
            return

        objects = state.get("objects", [])
        if not isinstance(objects, list):
            return

        for obj in objects:
            if not isinstance(obj, dict):
                continue

            object_id = str(obj.get("object_id", "unknown"))
            label = str(obj.get("label", "unknown"))
            x = float(obj.get("x", 0.0))
            y = float(obj.get("y", 0.0))
            z = float(obj.get("z", 0.0))
            zone = _classify_zone(x)
            previous = self._zones.get(object_id)
            if previous == zone:
                continue

            self._zones[object_id] = zone
            event = {
                "event": "zone_change",
                "object_id": object_id,
                "label": label,
                "zone": zone,
                "position": [x, y, z],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            event_msg = String()
            event_msg.data = json.dumps(event)
            self._event_pub.publish(event_msg)
            node_log(self.get_name(), event)
            self.get_logger().info(
                f"Object '{object_id}' entered zone '{zone}'"
            )


def create_node() -> ObserverNode:
    return ObserverNode()


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
