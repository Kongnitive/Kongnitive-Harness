"""
Example Turtle Controller Node

Demonstrates hot-swapping a turtlesim controller.
AI can modify movement logic without restarting turtlesim.

Prerequisites:
    sudo apt install ros-humble-turtlesim
    ros2 run turtlesim turtlesim_node
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from turtlesim.msg import Pose
import math


class TurtleControllerNode(Node):
    """
    Controls turtlesim turtle with hot-swappable logic.

    Subscribes to: /turtle1/pose
    Publishes to: /turtle1/cmd_vel
    """

    def __init__(self):
        super().__init__('turtle_controller')

        # Subscribe to turtle pose
        self.pose_sub = self.create_subscription(
            Pose,
            '/turtle1/pose',
            self.pose_callback,
            10
        )

        # Publish velocity commands
        self.vel_pub = self.create_publisher(
            Twist,
            '/turtle1/cmd_vel',
            10
        )

        # State
        self.current_pose = None
        self.counter = 0

        # Control timer (10 Hz)
        self.timer = self.create_timer(0.1, self.control_loop)

        self.get_logger().info('TurtleController started')

    def pose_callback(self, msg):
        """Update current turtle pose."""
        self.current_pose = msg

    def control_loop(self):
        """
        Main control logic - AI modifies this method.

        Current behavior: Circle pattern
        """
        if self.current_pose is None:
            return

        self.counter += 1

        # Generate velocity command
        cmd = self.generate_command(self.counter)

        # Publish
        self.vel_pub.publish(cmd)

        if self.counter % 50 == 0:
            self.get_logger().info(
                f'Pose: x={self.current_pose.x:.2f}, '
                f'y={self.current_pose.y:.2f}, '
                f'theta={self.current_pose.theta:.2f}'
            )

    def generate_command(self, tick: int) -> Twist:
        """
        Generate velocity command - AI modifies this.

        Args:
            tick: Control loop counter

        Returns:
            Twist command
        """
        cmd = Twist()

        # Example 1: Circle pattern
        cmd.linear.x = 2.0
        cmd.angular.z = 1.0

        return cmd


def create_node():
    """Factory function required for hot-swap."""
    return TurtleControllerNode()


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
