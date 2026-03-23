"""
Tests for Kongnitive ROS2 EdgeMCP Phase 1

Basic tests for NodeManager and MCP tools.
"""

import pytest
import asyncio
from pathlib import Path


# Mock rclpy for testing without ROS2
class MockNode:
    def __init__(self, name):
        self._name = name
        self._namespace = '/'

    def get_name(self):
        return self._name

    def get_namespace(self):
        return self._namespace

    def destroy_node(self):
        pass


@pytest.fixture
def mock_rclpy(monkeypatch):
    """Mock rclpy for testing without ROS2."""
    import sys
    from unittest.mock import MagicMock

    # Create mock rclpy module
    mock_rclpy = MagicMock()
    mock_rclpy.ok.return_value = False
    mock_rclpy.init = MagicMock()
    mock_rclpy.shutdown = MagicMock()
    mock_rclpy.node.Node = MockNode

    # Mock MultiThreadedExecutor
    mock_executor = MagicMock()
    mock_rclpy.executors.MultiThreadedExecutor.return_value = mock_executor

    sys.modules['rclpy'] = mock_rclpy
    sys.modules['rclpy.node'] = mock_rclpy.node
    sys.modules['rclpy.executors'] = mock_rclpy.executors

    return mock_rclpy


@pytest.mark.asyncio
async def test_system_tools_get_status():
    """Test get_status returns valid system info."""
    from kongnitive_ros2_edgemcp.tools import system_tools

    result = await system_tools.get_status()

    assert result["status"] == "success"
    assert "system" in result
    assert "cpu" in result
    assert "memory" in result
    assert "disk" in result


@pytest.mark.asyncio
async def test_system_tools_get_logs():
    """Test log retrieval and filtering."""
    from kongnitive_ros2_edgemcp.tools import system_tools

    # Add some test logs
    log_buffer = system_tools.get_log_buffer()
    log_buffer.add("INFO", "Test message 1", "test")
    log_buffer.add("ERROR", "Test error", "test")
    log_buffer.add("INFO", "Test message 2", "other")

    # Get all logs
    result = await system_tools.sys_get_logs()
    assert result["status"] == "success"
    assert result["count"] >= 3

    # Filter by level
    result = await system_tools.sys_get_logs(level="ERROR")
    assert result["status"] == "success"
    assert all(log["level"] == "ERROR" for log in result["logs"])

    # Filter by source
    result = await system_tools.sys_get_logs(source="test")
    assert result["status"] == "success"
    assert all(log["source"] == "test" for log in result["logs"])

    # Filter by text
    result = await system_tools.sys_get_logs(filter_text="error")
    assert result["status"] == "success"
    assert all("error" in log["message"].lower() for log in result["logs"])


@pytest.mark.asyncio
async def test_system_tools_configure_default_limit():
    """Test configurable default log limit is applied."""
    from kongnitive_ros2_edgemcp.tools import system_tools

    system_tools.configure(buffer_size=50, default_limit=2)
    log_buffer = system_tools.get_log_buffer()
    log_buffer.add("INFO", "A", "test")
    log_buffer.add("INFO", "B", "test")
    log_buffer.add("INFO", "C", "test")

    result = await system_tools.sys_get_logs()
    assert result["status"] == "success"
    assert result["count"] == 2


@pytest.mark.asyncio
async def test_log_buffer_limit():
    """Test log buffer respects size limit."""
    from kongnitive_ros2_edgemcp.tools.system_tools import LogBuffer

    buffer = LogBuffer(max_size=10)

    # Add more than max_size logs
    for i in range(20):
        buffer.add("INFO", f"Message {i}", "test")

    # Should only keep last 10
    logs = buffer.get_logs()
    assert len(logs) == 10
    assert logs[-1]["message"] == "Message 19"


def test_example_detector_node():
    """Test example detector node structure."""
    from pathlib import Path

    detector_path = Path(__file__).parent.parent / "examples" / "detector_node.py"
    assert detector_path.exists()

    # Read and check for required components
    content = detector_path.read_text()
    assert "def create_node()" in content
    assert "class DetectorNode" in content
    assert "import rclpy" in content


def test_example_planner_node():
    """Test example planner node structure."""
    from pathlib import Path

    planner_path = Path(__file__).parent.parent / "examples" / "planner_node.py"
    assert planner_path.exists()

    # Read and check for required components
    content = planner_path.read_text()
    assert "def create_node()" in content
    assert "class PlannerNode" in content
    assert "import rclpy" in content


def test_config_files_exist():
    """Test configuration files exist."""
    from pathlib import Path

    config_dir = Path(__file__).parent.parent / "config"
    assert (config_dir / "server_config.yaml").exists()
    assert (config_dir / "system_prompt.txt").exists()


def test_package_config_files_exist():
    """Test packaged configuration files exist."""
    from pathlib import Path

    config_dir = Path(__file__).parent.parent / "kongnitive_ros2_edgemcp" / "config"
    assert (config_dir / "server_config.yaml").exists()
    assert (config_dir / "system_prompt.txt").exists()


def test_load_server_config():
    """Test server config loader returns expected keys."""
    from kongnitive_ros2_edgemcp.utils.config_loader import (
        get_config_dir,
        load_server_config,
    )

    config = load_server_config()
    assert "server" in config
    assert "nodes" in config
    assert "logging" in config
    assert get_config_dir().name == "config"


def test_load_server_config_env_override(tmp_path, monkeypatch):
    """Test env var config directory override works."""
    from kongnitive_ros2_edgemcp.utils.config_loader import load_server_config

    config_text = """
server:
  log_level: DEBUG
nodes:
  script_dir: /tmp/nodes
logging:
  default_limit: 7
"""
    config_path = tmp_path / "server_config.yaml"
    config_path.write_text(config_text.strip(), encoding="utf-8")
    monkeypatch.setenv("KONGNITIVE_CONFIG_DIR", str(tmp_path))

    config = load_server_config()
    assert config["server"]["log_level"] == "DEBUG"
    assert config["logging"]["default_limit"] == 7


@pytest.mark.asyncio
async def test_node_manager_initialization(mock_rclpy, tmp_path):
    """Test NodeManager initializes correctly."""
    from kongnitive_ros2_edgemcp.core.node_manager import NodeManager

    # Use temporary directory for scripts
    nm = NodeManager(script_dir=str(tmp_path))

    assert nm.script_dir == tmp_path
    assert len(nm.nodes) == 0


@pytest.mark.asyncio
async def test_node_manager_max_nodes_limit(mock_rclpy, tmp_path):
    """Test NodeManager enforces max node count."""
    from kongnitive_ros2_edgemcp.core.node_manager import NodeManager

    nm = NodeManager(script_dir=str(tmp_path), max_nodes=1)

    script_a = """
import rclpy
from rclpy.node import Node

class ANode(Node):
    def __init__(self):
        super().__init__('a_node')

def create_node():
    return ANode()
"""
    script_b = script_a.replace("ANode", "BNode").replace("a_node", "b_node")

    result_a = await nm.push_node("a", script_a)
    result_b = await nm.push_node("b", script_b)

    assert result_a["status"] == "success"
    assert result_b["status"] == "error"
    assert "Max node limit" in result_b["message"]


@pytest.mark.asyncio
async def test_node_manager_list_empty(mock_rclpy, tmp_path):
    """Test listing nodes when none are running."""
    from kongnitive_ros2_edgemcp.core.node_manager import NodeManager

    nm = NodeManager(script_dir=str(tmp_path))
    result = await nm.list_nodes()

    assert result["status"] == "success"
    assert result["count"] == 0
    assert result["nodes"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
