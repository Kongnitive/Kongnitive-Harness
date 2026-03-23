# AI 自迭代的关键问题

## 问题1: 代码报错后如何获取日志让AI迭代？

### 1.1 日志捕获机制

#### ROS2 节点日志系统

```python
# detector.py (节点脚本)
import rclpy
from rclpy.node import Node

class DetectorNode(Node):
    def __init__(self):
        super().__init__('detector')

        # ROS2 日志 API
        self.get_logger().info('Node started')
        self.get_logger().warn('Low confidence detection')
        self.get_logger().error('Failed to load model')

    def callback(self, msg):
        try:
            result = self.detect(msg)
        except Exception as e:
            # 捕获异常并记录
            self.get_logger().error(f'Detection failed: {str(e)}')
            import traceback
            self.get_logger().error(traceback.format_exc())
```

#### NodeManager 日志捕获

```python
# node_manager.py
import logging
import sys
from io import StringIO

class NodeManager:
    def __init__(self):
        # 设置日志文件
        self.log_file = '/var/log/ros_nodes/manager.log'

        # 配置日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            handlers=[
                logging.FileHandler(self.log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger('NodeManager')

    def push_node(self, node_name, script_content):
        """推送节点并捕获错误"""
        try:
            # 保存脚本
            script_path = f'/opt/ros_nodes/{node_name}.py'
            with open(script_path, 'w') as f:
                f.write(script_content)

            self.logger.info(f'Script saved: {script_path}')

            # 动态加载
            self.load_node(node_name, script_path)

            self.logger.info(f'Node {node_name} loaded successfully')
            return {'status': 'success'}

        except SyntaxError as e:
            # Python 语法错误
            error_msg = f'Syntax error in {node_name}: {str(e)}'
            self.logger.error(error_msg)
            return {'status': 'error', 'error': error_msg, 'type': 'syntax'}

        except ImportError as e:
            # 导入错误
            error_msg = f'Import error in {node_name}: {str(e)}'
            self.logger.error(error_msg)
            return {'status': 'error', 'error': error_msg, 'type': 'import'}

        except Exception as e:
            # 其他错误
            error_msg = f'Failed to load {node_name}: {str(e)}'
            self.logger.error(error_msg)
            import traceback
            self.logger.error(traceback.format_exc())
            return {'status': 'error', 'error': error_msg, 'type': 'runtime'}
```

### 1.2 MCP 日志工具

```python
# mcp_tools.py
def handle_sys_get_logs(args):
    """获取系统日志"""
    lines = args.get('lines', 100)
    node_name = args.get('node_name', None)  # 可选：只看特定节点
    level = args.get('level', 'all')  # info/warn/error/all

    logs = []

    # 1. 读取 NodeManager 日志
    manager_log = '/var/log/ros_nodes/manager.log'
    if os.path.exists(manager_log):
        with open(manager_log, 'r') as f:
            logs.extend(f.readlines()[-lines:])

    # 2. 读取 ROS2 日志
    # ROS2 日志默认在 ~/.ros/log/
    ros_log_dir = os.path.expanduser('~/.ros/log/latest/')
    if os.path.exists(ros_log_dir):
        for log_file in os.listdir(ros_log_dir):
            if node_name and node_name not in log_file:
                continue
            with open(os.path.join(ros_log_dir, log_file), 'r') as f:
                logs.extend(f.readlines()[-lines:])

    # 3. 过滤日志级别
    if level != 'all':
        logs = [l for l in logs if f'[{level.upper()}]' in l]

    return {'logs': ''.join(logs[-lines:])}
```

### 1.3 AI 自迭代流程

```python
# AI 的完整迭代流程

# 1. AI 推送代码
response = mcp.call("ros_push_node", {
    "node_name": "detector",
    "script": """
import rclpy
from rclpy.node import Node

class DetectorNode(Node):
    def __init__(self):
        super().__init__('detector')
        # 故意写错：缺少导入
        self.model = YOLOv8()  # NameError!
"""
})

# 2. 检查推送结果
if response['status'] == 'error':
    # 立即发现错误
    print(f"Error: {response['error']}")
    print(f"Type: {response['type']}")

    # AI 分析错误并修复
    if response['type'] == 'import':
        # 修复：添加导入
        fixed_script = """
from ultralytics import YOLOv8  # 修复

class DetectorNode(Node):
    def __init__(self):
        super().__init__('detector')
        self.model = YOLOv8()
"""
        # 重新推送
        mcp.call("ros_push_node", {"node_name": "detector", "script": fixed_script})

# 3. 如果推送成功，但运行时报错
# AI 定期检查日志
logs = mcp.call("sys_get_logs", {"node_name": "detector", "lines": 50})

# 4. AI 分析日志
if "ERROR" in logs['logs']:
    # 发现错误
    # 例如: "Failed to load model: FileNotFoundError: yolov8n.pt not found"

    # AI 修复：下载模型
    mcp.call("bash", {"command": "wget https://github.com/.../yolov8n.pt -O /opt/models/yolov8n.pt"})

    # 重启节点
    mcp.call("ros_restart_node", {"node_name": "detector"})

    # 再次验证
    logs = mcp.call("sys_get_logs", {"node_name": "detector", "lines": 20})
    if "Node started" in logs['logs']:
        print("✅ 修复成功!")
```

---

## 问题2: 相机接入后，AI 自动发现并创建节点

### 2.1 设备发现机制

#### USB 设备发现

```python
# device_discovery.py
import pyudev
import subprocess

class DeviceDiscovery:
    def __init__(self):
        self.context = pyudev.Context()

    def discover_cameras(self):
        """发现所有摄像头设备"""
        cameras = []

        # 方法1: 通过 /dev/video* 发现
        import glob
        video_devices = glob.glob('/dev/video*')

        for device in video_devices:
            info = self.get_camera_info(device)
            cameras.append(info)

        # 方法2: 通过 v4l2 获取详细信息
        for device in video_devices:
            try:
                result = subprocess.run(
                    ['v4l2-ctl', '--device', device, '--all'],
                    capture_output=True, text=True
                )
                # 解析输出获取摄像头信息
                cameras.append(self.parse_v4l2_info(result.stdout))
            except:
                pass

        return cameras

    def get_camera_info(self, device_path):
        """获取摄像头详细信息"""
        return {
            'device': device_path,
            'type': 'camera',
            'driver': self.get_driver(device_path),
            'resolution': self.get_resolution(device_path),
            'formats': self.get_formats(device_path)
        }

    def discover_all_devices(self):
        """发现所有设备"""
        devices = {
            'cameras': self.discover_cameras(),
            'lidars': self.discover_lidars(),
            'imu': self.discover_imu(),
            'gps': self.discover_gps()
        }
        return devices
```

#### 网络设备发现

```python
def discover_network_cameras(self):
    """发现网络摄像头 (RTSP/HTTP)"""
    # 使用 nmap 扫描网络
    result = subprocess.run(
        ['nmap', '-p', '554,8080', '192.168.1.0/24'],
        capture_output=True, text=True
    )

    # 解析结果，找到摄像头
    cameras = []
    # ... 解析逻辑
    return cameras
```

### 2.2 MCP 设备发现工具

```python
# mcp_tools.py
def handle_device_discover(args):
    """发现设备"""
    device_type = args.get('type', 'all')  # camera/lidar/imu/all

    discovery = DeviceDiscovery()

    if device_type == 'camera':
        devices = discovery.discover_cameras()
    elif device_type == 'all':
        devices = discovery.discover_all_devices()
    else:
        devices = getattr(discovery, f'discover_{device_type}')()

    return {'devices': devices}

def handle_device_create_node(args):
    """为设备自动创建节点"""
    device_info = args['device_info']
    node_name = args.get('node_name', f"{device_info['type']}_{device_info['device'].replace('/', '_')}")

    # 根据设备类型生成节点代码
    if device_info['type'] == 'camera':
        script = generate_camera_node(device_info)
    elif device_info['type'] == 'lidar':
        script = generate_lidar_node(device_info)
    # ... 其他设备类型

    # 推送节点
    return handle_ros_push_node({
        'node_name': node_name,
        'script': script
    })
```

### 2.3 自动生成节点代码

```python
def generate_camera_node(device_info):
    """根据设备信息生成摄像头节点代码"""
    device = device_info['device']
    resolution = device_info.get('resolution', '640x480')
    fps = device_info.get('fps', 30)

    script = f"""
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2

class CameraNode(Node):
    def __init__(self):
        super().__init__('camera_{device.replace("/", "_")}')

        # 创建 publisher
        self.pub = self.create_publisher(Image, '/camera/image', 10)

        # 打开摄像头
        self.cap = cv2.VideoCapture('{device}')
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, {resolution.split('x')[0]})
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, {resolution.split('x')[1]})
        self.cap.set(cv2.CAP_PROP_FPS, {fps})

        # CV Bridge
        self.bridge = CvBridge()

        # 定时器
        self.timer = self.create_timer(1.0/{fps}, self.timer_callback)

        self.get_logger().info(f'Camera node started: {device}')

    def timer_callback(self):
        ret, frame = self.cap.read()
        if ret:
            msg = self.bridge.cv2_to_imgmsg(frame, 'bgr8')
            self.pub.publish(msg)
        else:
            self.get_logger().warn('Failed to read frame')

    def __del__(self):
        self.cap.release()

def create_node():
    return CameraNode()
"""
    return script
```

### 2.4 AI 完整流程

```python
# AI 自动发现设备并创建节点

# 1. AI 发现设备
devices = mcp.call("device_discover", {"type": "camera"})

# 返回:
# {
#   "devices": [
#     {
#       "device": "/dev/video0",
#       "type": "camera",
#       "driver": "uvcvideo",
#       "resolution": "1920x1080",
#       "formats": ["MJPEG", "YUYV"]
#     }
#   ]
# }

# 2. AI 分析设备信息
camera = devices['devices'][0]
print(f"发现摄像头: {camera['device']}")
print(f"分辨率: {camera['resolution']}")

# 3. AI 自动创建节点
response = mcp.call("device_create_node", {
    "device_info": camera,
    "node_name": "camera_main"
})

# 4. 验证节点运行
logs = mcp.call("sys_get_logs", {"node_name": "camera_main", "lines": 10})
if "Camera node started" in logs['logs']:
    print("✅ 摄像头节点创建成功!")

    # 5. 验证 topic
    topics = mcp.call("ros_list_topics")
    if "/camera/image" in topics['topics']:
        print("✅ Topic 已创建!")

        # 6. 查看数据
        data = mcp.call("ros_echo_topic", {"topic": "/camera/image", "count": 1})
        print(f"✅ 接收到图像数据: {data}")
```

### 2.5 高级功能：设备热插拔监听

```python
# device_monitor.py
import pyudev
from threading import Thread

class DeviceMonitor:
    def __init__(self, node_manager):
        self.node_manager = node_manager
        self.context = pyudev.Context()
        self.monitor = pyudev.Monitor.from_netlink(self.context)
        self.monitor.filter_by('video4linux')  # 监听摄像头

    def start(self):
        """启动设备监听"""
        thread = Thread(target=self._monitor_loop, daemon=True)
        thread.start()

    def _monitor_loop(self):
        """监听设备插拔"""
        for device in iter(self.monitor.poll, None):
            if device.action == 'add':
                # 设备插入
                print(f"设备插入: {device.device_node}")
                self._on_device_added(device)
            elif device.action == 'remove':
                # 设备拔出
                print(f"设备拔出: {device.device_node}")
                self._on_device_removed(device)

    def _on_device_added(self, device):
        """设备插入时自动创建节点"""
        # 获取设备信息
        device_info = {
            'device': device.device_node,
            'type': 'camera',
            # ... 其他信息
        }

        # 自动生成节点
        script = generate_camera_node(device_info)
        node_name = f"camera_{device.device_node.replace('/', '_')}"

        # 推送并启动
        self.node_manager.push_node(node_name, script)
        print(f"✅ 自动创建节点: {node_name}")

    def _on_device_removed(self, device):
        """设备拔出时自动停止节点"""
        node_name = f"camera_{device.device_node.replace('/', '_')}"
        self.node_manager.unload_node(node_name)
        print(f"❌ 自动停止节点: {node_name}")
```

---

## 完整的 MCP 工具列表

```python
# 系统工具
- sys_get_logs          # 获取日志
- sys_reboot            # 重启系统

# 节点管理
- ros_push_node         # 推送节点
- ros_start_node        # 启动节点
- ros_stop_node         # 停止节点
- ros_restart_node      # 重启节点
- ros_list_nodes        # 列出节点
- ros_get_node          # 获取节点代码

# Topic 管理
- ros_list_topics       # 列出 topic
- ros_echo_topic        # 监听 topic
- ros_pub_topic         # 发布测试数据

# 设备管理
- device_discover       # 发现设备
- device_create_node    # 为设备创建节点
- device_list           # 列出已连接设备

# GPU 管理
- gpu_list_models       # 列出模型
- gpu_push_model        # 推送模型
- gpu_profile           # 性能分析
```

---

## 总结

### 问题1: 日志获取和错误迭代

```
流程:
  AI push 代码
    ↓
  立即返回结果 (成功/语法错误/导入错误)
    ↓
  如果成功，AI 定期检查日志
    ↓
  发现运行时错误
    ↓
  AI 分析日志
    ↓
  AI 修复代码
    ↓
  AI 重新 push
    ↓
  验证修复

关键:
  ✅ 多层日志捕获 (NodeManager + ROS2)
  ✅ 结构化错误返回
  ✅ sys_get_logs 工具
  ✅ AI 自动分析和修复
```

### 问题2: 设备自动发现和节点创建

```
流程:
  设备插入
    ↓
  AI 调用 device_discover
    ↓
  获取设备信息
    ↓
  AI 调用 device_create_node
    ↓
  自动生成节点代码
    ↓
  推送并启动节点
    ↓
  验证运行

高级:
  ✅ 设备热插拔监听
  ✅ 自动创建节点
  ✅ 自动停止节点

关键:
  ✅ pyudev 设备发现
  ✅ 代码生成模板
  ✅ device_create_node 工具
  ✅ 热插拔监听 (可选)
```
