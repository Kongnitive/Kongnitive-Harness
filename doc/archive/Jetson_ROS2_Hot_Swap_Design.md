# Jetson ROS2 热插拔基座设计

**目标**: 实现能够热插拔ROS节点的基座，包括动态创建/修改 topic/service/action

---

## 核心架构

```
MCP Server (Jetson)
    ↓
Node Manager (常驻进程)
    ↓
Dynamic Node Loader
    ↓
运行时创建的 Python ROS2 节点
    ├─ 动态创建 Topic
    ├─ 动态创建 Service
    └─ 动态创建 Action
```

---

## 技术实现

### 1. 节点热插拔

```python
# node_manager.py
import rclpy
import importlib
import sys
from threading import Thread

class NodeManager:
    def __init__(self):
        self.nodes = {}  # {node_name: {instance, thread, module}}

    def load_node(self, node_name, script_content):
        """动态加载节点"""
        # 1. 保存脚本到文件
        script_path = f"/tmp/ros_nodes/{node_name}.py"
        with open(script_path, 'w') as f:
            f.write(script_content)

        # 2. 动态导入
        spec = importlib.util.spec_from_file_location(node_name, script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 3. 实例化节点
        node = module.create_node()  # 脚本需要提供这个函数

        # 4. 在新线程中spin
        thread = Thread(target=rclpy.spin, args=(node,), daemon=True)
        thread.start()

        # 5. 保存引用
        self.nodes[node_name] = {
            'instance': node,
            'thread': thread,
            'module': module
        }

    def unload_node(self, node_name):
        """卸载节点"""
        if node_name in self.nodes:
            self.nodes[node_name]['instance'].destroy_node()
            del self.nodes[node_name]

    def reload_node(self, node_name, script_content):
        """热重载节点"""
        self.unload_node(node_name)
        self.load_node(node_name, script_content)
```

### 2. Topic 热插拔

```python
# 动态创建 Publisher
def create_dynamic_publisher(node, topic_name, msg_type_str, qos=10):
    """
    node: ROS2节点实例
    topic_name: "/camera/image"
    msg_type_str: "sensor_msgs/Image"
    """
    # 动态导入消息类型
    pkg, msg = msg_type_str.split('/')
    msg_module = importlib.import_module(f'{pkg}.msg')
    msg_class = getattr(msg_module, msg)

    # 创建publisher
    pub = node.create_publisher(msg_class, topic_name, qos)
    return pub

# 动态创建 Subscriber
def create_dynamic_subscriber(node, topic_name, msg_type_str, callback, qos=10):
    msg_module = importlib.import_module(f'{msg_type_str.split("/")[0]}.msg')
    msg_class = getattr(msg_module, msg_type_str.split("/")[1])

    sub = node.create_subscription(msg_class, topic_name, callback, qos)
    return sub
```

### 3. Service 热插拔

```python
def create_dynamic_service(node, service_name, srv_type_str, callback):
    """
    service_name: "/get_position"
    srv_type_str: "nav_msgs/GetPosition"
    """
    pkg, srv = srv_type_str.split('/')
    srv_module = importlib.import_module(f'{pkg}.srv')
    srv_class = getattr(srv_module, srv)

    service = node.create_service(srv_class, service_name, callback)
    return service

def create_dynamic_client(node, service_name, srv_type_str):
    pkg, srv = srv_type_str.split('/')
    srv_module = importlib.import_module(f'{pkg}.srv')
    srv_class = getattr(srv_module, srv)

    client = node.create_client(srv_class, service_name)
    return client
```

### 4. Action 热插拔

```python
from rclpy.action import ActionServer, ActionClient

def create_dynamic_action_server(node, action_name, action_type_str, execute_callback):
    """
    action_name: "/navigate_to_pose"
    action_type_str: "nav2_msgs/NavigateToPose"
    """
    pkg, action = action_type_str.split('/')
    action_module = importlib.import_module(f'{pkg}.action')
    action_class = getattr(action_module, action)

    server = ActionServer(node, action_class, action_name, execute_callback)
    return server

def create_dynamic_action_client(node, action_name, action_type_str):
    pkg, action = action_type_str.split('/')
    action_module = importlib.import_module(f'{pkg}.action')
    action_class = getattr(action_module, action)

    client = ActionClient(node, action_class, action_name)
    return client
```

---

## MCP 工具接口

### 节点管理
```python
# 1. 推送节点脚本
mcp.call("ros_push_node", {
    "node_name": "detector",
    "script": """
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2DArray

class DetectorNode(Node):
    def __init__(self):
        super().__init__('detector')
        # 动态创建 subscriber
        self.sub = self.create_subscription(
            Image, '/camera/image', self.callback, 10)
        # 动态创建 publisher
        self.pub = self.create_publisher(
            Detection2DArray, '/detections', 10)

    def callback(self, msg):
        # 检测逻辑
        detections = self.detect(msg)
        self.pub.publish(detections)

def create_node():
    return DetectorNode()
"""
})

# 2. 启动节点
mcp.call("ros_start_node", {"node_name": "detector"})

# 3. 停止节点
mcp.call("ros_stop_node", {"node_name": "detector"})

# 4. 重启节点
mcp.call("ros_restart_node", {"node_name": "detector"})
```

### Topic 管理
```python
# 5. 列出所有 topic
mcp.call("ros_list_topics")
# 返回: ["/camera/image", "/detections", ...]

# 6. 查看 topic 信息
mcp.call("ros_topic_info", {"topic": "/camera/image"})
# 返回: {type: "sensor_msgs/Image", publishers: 1, subscribers: 2}

# 7. 监听 topic 数据
mcp.call("ros_echo_topic", {"topic": "/detections", "count": 10})
# 返回最近10条消息

# 8. 发布测试数据
mcp.call("ros_pub_topic", {
    "topic": "/cmd_vel",
    "msg_type": "geometry_msgs/Twist",
    "data": {"linear": {"x": 0.5}, "angular": {"z": 0.0}}
})
```

### Service 管理
```python
# 9. 列出所有 service
mcp.call("ros_list_services")

# 10. 调用 service
mcp.call("ros_call_service", {
    "service": "/get_position",
    "srv_type": "nav_msgs/GetPosition",
    "request": {}
})
```

### Action 管理
```python
# 11. 列出所有 action
mcp.call("ros_list_actions")

# 12. 发送 action goal
mcp.call("ros_send_goal", {
    "action": "/navigate_to_pose",
    "action_type": "nav2_msgs/NavigateToPose",
    "goal": {"pose": {"position": {"x": 1.0, "y": 2.0}}}
})
```

---

## AI 自迭代示例

### 场景: 动态添加新的检测类别

```python
# 1. AI 读取当前节点
code = mcp.call("ros_get_node", {"node_name": "detector"})

# 2. AI 发现只检测"人"，需要增加"车"
# AI 修改代码，增加新的 topic

# 3. AI 推送新版本
mcp.call("ros_push_node", {
    "node_name": "detector",
    "script": """
class DetectorNode(Node):
    def __init__(self):
        super().__init__('detector')
        self.sub = self.create_subscription(
            Image, '/camera/image', self.callback, 10)

        # 原有: 人的检测结果
        self.pub_person = self.create_publisher(
            Detection2DArray, '/detections/person', 10)

        # 新增: 车的检测结果
        self.pub_vehicle = self.create_publisher(
            Detection2DArray, '/detections/vehicle', 10)

    def callback(self, msg):
        persons = self.detect_person(msg)
        vehicles = self.detect_vehicle(msg)  # 新增

        self.pub_person.publish(persons)
        self.pub_vehicle.publish(vehicles)  # 新增
"""
})

# 4. AI 重启节点
mcp.call("ros_restart_node", {"node_name": "detector"})

# 5. AI 验证新 topic
topics = mcp.call("ros_list_topics")
# 确认: ["/detections/person", "/detections/vehicle"]

# 6. AI 监听数据
data = mcp.call("ros_echo_topic", {"topic": "/detections/vehicle", "count": 5})
# 验证: 车辆检测正常工作
```

---

## 关键特性

### 1. 完全动态
- 节点可以在运行时创建/销毁
- Topic/Service/Action 可以在运行时创建/销毁
- 消息类型可以动态指定

### 2. 零停机
- 更新节点不影响其他节点
- 新 topic 自动被其他节点发现
- FastDDS 自动处理连接

### 3. AI 友好
- 所有操作通过 MCP 工具
- AI 可以读取/修改/验证
- 完整的自迭代闭环

---

## 实现路线

### Phase 1: 基础框架 (1周)
- [ ] NodeManager 实现
- [ ] 动态加载 Python 节点
- [ ] 基础 MCP 工具 (push/start/stop/restart)

### Phase 2: Topic 热插拔 (1周)
- [ ] 动态创建 Publisher/Subscriber
- [ ] ros_list_topics / ros_echo_topic
- [ ] ros_pub_topic (测试工具)

### Phase 3: Service/Action (1周)
- [ ] 动态创建 Service/Client
- [ ] 动态创建 Action Server/Client
- [ ] 相关 MCP 工具

### Phase 4: AI 集成 (1周)
- [ ] 完整的自迭代示例
- [ ] 日志分析 + 自动修复
- [ ] 性能测试

---

## 技术要点

### 1. Python 动态特性
```python
# 运行时导入模块
importlib.import_module()

# 运行时获取类
getattr(module, class_name)

# 运行时执行代码
exec(code_string)
```

### 2. ROS2 动态特性
```python
# 节点可以随时创建/销毁
node = Node('my_node')
node.destroy_node()

# Topic 可以随时创建
pub = node.create_publisher(MsgType, '/topic', 10)
pub.destroy()

# FastDDS 自动发现
# 新 topic 会自动被其他节点发现
```

### 3. 线程管理
```python
# 每个节点在独立线程中 spin
thread = Thread(target=rclpy.spin, args=(node,))
thread.start()

# 停止时销毁节点，线程自动退出
node.destroy_node()
```

---

## 总结

这个设计实现了**真正的热插拔**:
- ✅ 节点可以动态加载/卸载
- ✅ Topic 可以动态创建/销毁
- ✅ Service 可以动态创建/销毁
- ✅ Action 可以动态创建/销毁
- ✅ AI 可以完全控制整个过程

核心是利用 Python 的动态特性 + ROS2 的运行时 API。
