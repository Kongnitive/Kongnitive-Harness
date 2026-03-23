"""
Example Planner Node

This demonstrates a more complex ROS2 node with subscriptions and publications.
Shows how AI can hot-swap navigation/planning logic.
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Int32


class PlannerNode(Node):
    """
    Planner node that receives goals and publishes plans.

    Demonstrates:
    - Topic subscription
    - Topic publication
    - Stateful processing
    - Hot-swappable planning logic
    """

    def __init__(self):
        super().__init__('planner')

        # Subscribe to goal topic
        self.goal_sub = self.create_subscription(
            String,
            '/goal',
            self.goal_callback,
            10
        )

        # Publish to plan topic
        self.plan_pub = self.create_publisher(
            String,
            '/plan',
            10
        )

        # Publish status
        self.status_pub = self.create_publisher(
            Int32,
            '/planner_status',
            10
        )

        # State
        self.current_goal = None
        self.plan_count = 0

        # Status timer (1 Hz)
        self.status_timer = self.create_timer(1.0, self.publish_status)

        self.get_logger().info('PlannerNode started')

    def goal_callback(self, msg):
        """
        Handle incoming goal messages.

        Args:
            msg: String message with goal description
        """
        self.current_goal = msg.data
        self.get_logger().info(f'Received goal: {self.current_goal}')

        # Generate plan
        plan = self.plan(self.current_goal)

        # Publish plan
        plan_msg = String()
        plan_msg.data = plan
        self.plan_pub.publish(plan_msg)

        self.plan_count += 1
        self.get_logger().info(f'Published plan: {plan}')

    def plan(self, goal: str) -> str:
        """
        Planning logic - AI modifies this method.

        Args:
            goal: Goal description

        Returns:
            Plan as string
        """
        # Simple example: reverse the goal string
        plan = f"PLAN[{self.plan_count}]: {goal[::-1]}"
        return plan

    def publish_status(self):
        """Publish periodic status updates."""
        status_msg = Int32()
        status_msg.data = self.plan_count
        self.status_pub.publish(status_msg)


def create_node():
    """
    Factory function required for hot-swap.

    Returns:
        PlannerNode instance
    """
    return PlannerNode()


# For standalone testing
if __name__ == '__main__':
    rclpy.init()
    node = create_node()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
