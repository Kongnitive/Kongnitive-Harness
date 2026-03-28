"""
Template launch file for one shared Gazebo world with two robots.

Adapt package names and file paths to your simulation packages.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    world = LaunchConfiguration("world")
    robot_a_ns = LaunchConfiguration("robot_a_ns")
    robot_b_ns = LaunchConfiguration("robot_b_ns")

    return LaunchDescription(
        [
            DeclareLaunchArgument("world", default_value="tabletop.world"),
            DeclareLaunchArgument("robot_a_ns", default_value="/robot_a"),
            DeclareLaunchArgument("robot_b_ns", default_value="/robot_b"),

            # Gazebo server/client (replace package/executable to match your setup)
            Node(
                package="ros_gz_sim",
                executable="gz_sim",
                arguments=["-r", world],
                output="screen",
            ),

            # Robot A state publisher (replace robot_description source)
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                namespace=robot_a_ns,
                output="screen",
                parameters=[{"use_sim_time": True}],
            ),

            # Robot B state publisher
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                namespace=robot_b_ns,
                output="screen",
                parameters=[{"use_sim_time": True}],
            ),

            # Add your per-robot:
            # - ros2_control controller_manager
            # - MoveIt2 move_group
            # - sensor bridge nodes
            # keeping all topics/services/actions namespaced.
        ]
    )

