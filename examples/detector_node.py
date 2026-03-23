"""
Example Detector Node

This is a template for a simple ROS2 detector node that can be hot-swapped.
AI can modify the detect() method to change detection logic without restarting.
"""

import rclpy
from rclpy.node import Node


class DetectorNode(Node):
    """
    Simple detector node that processes data and publishes results.

    This node demonstrates the hot-swap pattern:
    - Subscribes to input topic
    - Processes data in callback
    - Publishes results to output topic
    """

    def __init__(self):
        super().__init__('detector')

        # Create timer for periodic processing (1 Hz)
        self.timer = self.create_timer(1.0, self.timer_callback)

        self.counter = 0

        self.get_logger().info('DetectorNode started')

    def timer_callback(self):
        """
        Timer callback - called periodically.

        AI can modify this method to change behavior.
        """
        self.counter += 1
        self.get_logger().info(f'DetectorNode tick {self.counter}')

        # Example: Simple detection logic
        result = self.detect(self.counter)
        self.get_logger().info(f'Detection result: {result}')

    def detect(self, value):
        """
        Detection logic - AI modifies this method.

        Args:
            value: Input value to process

        Returns:
            Detection result
        """
        # Simple example: detect even numbers
        if value % 2 == 0:
            return f"EVEN: {value}"
        else:
            return f"ODD: {value}"


def create_node():
    """
    Factory function required for hot-swap.

    Returns:
        DetectorNode instance
    """
    return DetectorNode()


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
