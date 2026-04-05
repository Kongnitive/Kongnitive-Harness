"""
Tests for Kongnitive ROS2 EdgeMCP Phase 1

Basic tests for NodeManager and MCP tools.
"""

import pytest
import asyncio
import sys
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


def test_example_observer_node():
    """Test observer example exposes the world-state subscription pattern."""
    from pathlib import Path

    observer_path = Path(__file__).parent.parent / "examples" / "observer_node.py"
    assert observer_path.exists()

    content = observer_path.read_text(encoding="utf-8")
    assert "def create_node()" in content
    assert "class ObserverNode" in content
    assert '"/world_model/state"' in content
    assert '"/zone_events"' in content
    assert "node_log" in content


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


def test_success_example_store_roundtrip(tmp_path):
    """Test successful example persistence helpers."""
    from kongnitive_ros2_edgemcp.core.success_examples import (
        build_example,
        filter_examples,
        get_store_path,
        load_examples,
        upsert_example,
    )

    store_path = get_store_path(tmp_path / "nodes")
    example = build_example(
        node_name="demo",
        script="def create_node():\n    pass\n",
        script_path=str(tmp_path / "nodes" / "demo.py"),
        recent_logs=[{"skill": "pick", "success": True}],
        source="manual",
        goal="pick place red lego",
        summary="demo summary",
        tags=["lego"],
    )
    upsert_example(store_path, example)

    persisted = load_examples(store_path)
    assert len(persisted) == 1
    assert persisted[0]["node_name"] == "demo"
    assert persisted[0]["has_goal_success"] is False

    filtered = filter_examples(persisted, goal_filter="lego", limit=3)
    assert len(filtered) == 1
    assert filtered[0]["goal"] == "pick place red lego"


@pytest.mark.asyncio
async def test_ros_get_successful_node_examples_accepts_non_goal_success(tmp_path, monkeypatch):
    """Test retrieval works for success logs even without a goal entry."""
    from kongnitive_ros2_edgemcp import server
    from kongnitive_ros2_edgemcp.core.node_log import clear_logs, node_log

    script_dir = tmp_path / "nodes"
    script_dir.mkdir()
    (script_dir / "demo.py").write_text(
        "import rclpy\n"
        "from rclpy.node import Node\n\n"
        "class Demo(Node):\n"
        "    def __init__(self):\n"
        "        super().__init__('demo')\n\n"
        "def create_node():\n"
        "    return Demo()\n",
        encoding="utf-8",
    )
    node_log("demo", {"skill": "pick", "success": True, "failure_reason": None})

    class FakeNodeManager:
        def __init__(self, script_dir):
            self.script_dir = script_dir

    monkeypatch.setattr(server, "get_node_manager", lambda: FakeNodeManager(script_dir))
    result = await server.ros_get_successful_node_examples(goal_filter="pick", limit=5)

    assert result["status"] == "success"
    assert result["count"] >= 1
    assert any(item["node_name"] == "demo" for item in result["examples"])
    assert any(item["source"] == "session" for item in result["examples"])
    clear_logs("demo")


@pytest.mark.asyncio
async def test_ros_write_successful_node_examples_persists_current_node(tmp_path, monkeypatch):
    """Test explicit persistence tool writes the current successful node example."""
    from kongnitive_ros2_edgemcp import server
    from kongnitive_ros2_edgemcp.core.node_log import clear_logs, node_log
    from kongnitive_ros2_edgemcp.core.success_examples import get_store_path, load_examples

    script_dir = tmp_path / "nodes"
    script_dir.mkdir()
    script_path = script_dir / "demo.py"
    script_path.write_text(
        "import rclpy\n"
        "from rclpy.node import Node\n\n"
        "class Demo(Node):\n"
        "    def __init__(self):\n"
        "        super().__init__('demo')\n\n"
        "def create_node():\n"
        "    return Demo()\n",
        encoding="utf-8",
    )
    node_log("demo", {"skill": "goal", "success": True})

    class FakeNodeManager:
        def __init__(self, script_dir):
            self.script_dir = script_dir

    async def fake_ros_get_node(_nm, node_name):
        return {
            "status": "success",
            "node_name": node_name,
            "script": script_path.read_text(encoding="utf-8"),
            "script_path": str(script_path),
        }

    monkeypatch.setattr(server, "get_node_manager", lambda: FakeNodeManager(script_dir))
    monkeypatch.setattr(server.node_tools, "ros_get_node", fake_ros_get_node)

    result = await server.ros_write_successful_node_examples(
        node_name="demo",
        goal="pick place red lego left table",
        summary="stable success",
        tags=["lego", "left"],
    )

    assert result["status"] == "success"
    store_path = get_store_path(script_dir)
    persisted = load_examples(store_path)
    assert len(persisted) == 1
    assert persisted[0]["goal"] == "pick place red lego left table"
    assert persisted[0]["has_goal_success"] is True
    clear_logs("demo")


@pytest.mark.asyncio
async def test_ros_list_capabilities_returns_runtime_view(monkeypatch):
    """Test runtime capability view combines managed nodes and local skills."""
    from types import SimpleNamespace

    class FakeFastMCP:
        def __init__(self, _name):
            pass

        def tool(self):
            def decorator(func):
                return func
            return decorator

        def run(self, **_kwargs):
            return None

    monkeypatch.setitem(sys.modules, "fastmcp", SimpleNamespace(FastMCP=FakeFastMCP))
    from kongnitive_ros2_edgemcp import server

    class FakeNodeManager:
        async def list_nodes(self):
            return {
                "status": "success",
                "count": 1,
                "nodes": [
                    {
                        "name": "observer",
                        "ros_node_name": "observer",
                        "namespace": "/",
                        "script_path": "/tmp/observer.py",
                    }
                ],
            }

    class FakeAgent:
        skills = ["detect", "pick", "place"]

    monkeypatch.setattr(server, "get_node_manager", lambda: FakeNodeManager())
    monkeypatch.setattr(
        "kongnitive_ros2_edgemcp.core.vector_bridge.get_agent",
        lambda: FakeAgent(),
    )

    result = await server.ros_list_capabilities()

    assert result["status"] == "success"
    assert result["view"] == "runtime control-plane"
    assert result["managed_nodes"][0]["name"] == "observer"
    assert result["agent_skills"] == ["detect", "pick", "place"]
    assert any(topic["name"] == "/world_model/state" for topic in result["topics"])
    assert any(topic["name"] == "/zone_events" for topic in result["topics"])


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
