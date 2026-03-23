"""
Kongnitive ROS2 EdgeMCP Setup

Installation script for Kongnitive ROS2 EdgeMCP package.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text(encoding='utf-8') if readme_path.exists() else ""

setup(
    name="kongnitive-ros2-edgemcp",
    version="0.1.0",
    description="Jetson-based MCP server for AI-driven hot-swapping of ROS2 nodes",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Kongnitive",
    author_email="",
    url="https://github.com/kongnitive/kongnitive-ros2-edgemcp",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "fastmcp>=3.0.0",
        "rclpy>=3.0.0",
        "psutil>=5.9.0",
        "pyyaml>=6.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "kongnitive-ros2-edgemcp=kongnitive_ros2_edgemcp.server:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    include_package_data=True,
    package_data={
        "kongnitive_ros2_edgemcp": [
            "config/*.yaml",
            "config/*.txt",
        ],
    },
)
