"""Tests for WorldModelServiceNode state topic publishing."""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path


class _FakeLogger:
    def info(self, _msg: str) -> None:
        pass

    def warn(self, _msg: str) -> None:
        pass

    def error(self, _msg: str) -> None:
        pass


class _FakePublisher:
    def __init__(self) -> None:
        self.messages: list[object] = []

    def publish(self, msg: object) -> None:
        self.messages.append(msg)


class _FakeNode:
    def __init__(self, _name: str) -> None:
        self.publishers: dict[str, _FakePublisher] = {}
        self.subscriptions: list[tuple[object, str, object, int]] = []
        self.services: list[tuple[object, str, object]] = []
        self.parameters: dict[str, str] = {}
        self.logger = _FakeLogger()

    def declare_parameter(self, name: str, value: str) -> None:
        self.parameters[name] = value

    def create_publisher(self, _msg_type: object, topic: str, _qos: int) -> _FakePublisher:
        pub = _FakePublisher()
        self.publishers[topic] = pub
        return pub

    def create_subscription(self, msg_type: object, topic: str, callback: object, qos: int) -> object:
        self.subscriptions.append((msg_type, topic, callback, qos))
        return object()

    def create_service(self, srv_type: object, topic: str, callback: object) -> object:
        self.services.append((srv_type, topic, callback))
        return object()

    def get_logger(self) -> _FakeLogger:
        return self.logger

    def get_parameter(self, name: str):
        value = self.parameters[name]

        class _ParameterValue:
            def __init__(self, raw: str) -> None:
                self.string_value = raw

        class _Parameter:
            def __init__(self, raw: str) -> None:
                self.raw = raw

            def get_parameter_value(self) -> _ParameterValue:
                return _ParameterValue(self.raw)

        return _Parameter(value)


class _FakeJointState:
    def __init__(self, name: list[str] | None = None, position: list[float] | None = None) -> None:
        self.name = name or []
        self.position = position or []


class _FakeString:
    def __init__(self) -> None:
        self.data = ""


class _FakeTrigger:
    class Request:
        pass

    class Response:
        def __init__(self) -> None:
            self.success = False
            self.message = ""


def _install_ros2_stubs(monkeypatch) -> None:
    """Provide enough ROS2 surface area to import the node module."""
    fake_rclpy = types.ModuleType("rclpy")
    fake_rclpy.init = lambda *args, **kwargs: None
    fake_rclpy.shutdown = lambda *args, **kwargs: None

    fake_node_mod = types.ModuleType("rclpy.node")
    fake_node_mod.Node = _FakeNode

    fake_exec_mod = types.ModuleType("rclpy.executors")

    class _FakeExecutor:
        def add_node(self, _node: object) -> None:
            pass

        def spin(self) -> None:
            pass

    fake_exec_mod.MultiThreadedExecutor = _FakeExecutor

    fake_sensor_msgs = types.ModuleType("sensor_msgs.msg")
    fake_sensor_msgs.JointState = _FakeJointState

    fake_std_msgs = types.ModuleType("std_msgs.msg")
    fake_std_msgs.String = _FakeString

    fake_std_srvs = types.ModuleType("std_srvs.srv")
    fake_std_srvs.Trigger = _FakeTrigger

    monkeypatch.setitem(sys.modules, "rclpy", fake_rclpy)
    monkeypatch.setitem(sys.modules, "rclpy.node", fake_node_mod)
    monkeypatch.setitem(sys.modules, "rclpy.executors", fake_exec_mod)
    monkeypatch.setitem(sys.modules, "sensor_msgs.msg", fake_sensor_msgs)
    monkeypatch.setitem(sys.modules, "std_msgs.msg", fake_std_msgs)
    monkeypatch.setitem(sys.modules, "std_srvs.srv", fake_std_srvs)


def _load_node_module(monkeypatch):
    _install_ros2_stubs(monkeypatch)
    module_name = "test_world_model_node_module"
    sys.modules.pop(module_name, None)
    module_path = (
        Path(__file__).resolve().parents[2]
        / "vector_os_nano"
        / "ros2"
        / "nodes"
        / "world_model_node.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_world_model_node_publishes_initial_state(monkeypatch) -> None:
    mod = _load_node_module(monkeypatch)

    node = mod.WorldModelServiceNode()
    messages = node.publishers["/world_model/state"].messages

    assert len(messages) == 1
    payload = json.loads(messages[0].data)
    assert payload["objects"] == []
    assert "robot" in payload


def test_world_model_node_republishes_after_detection_update(monkeypatch) -> None:
    mod = _load_node_module(monkeypatch)

    node = mod.WorldModelServiceNode()
    msg = _FakeString()
    msg.data = json.dumps(
        [{"object_id": "cube-1", "label": "red cube", "x": -0.2, "y": 0.05, "z": 0.01}]
    )

    node._on_detections(msg)
    messages = node.publishers["/world_model/state"].messages

    assert len(messages) == 2
    payload = json.loads(messages[-1].data)
    assert payload["objects"][0]["object_id"] == "cube-1"
    assert payload["objects"][0]["x"] == -0.2


def test_world_model_node_republishes_after_joint_state_update(monkeypatch) -> None:
    mod = _load_node_module(monkeypatch)

    node = mod.WorldModelServiceNode()
    msg = _FakeJointState(name=["joint_1", "joint_2"], position=[0.1, -0.2])

    node._on_joint_states(msg)
    messages = node.publishers["/world_model/state"].messages

    assert len(messages) == 2
    payload = json.loads(messages[-1].data)
    assert payload["robot"]["joint_positions"] == [0.1, -0.2]
