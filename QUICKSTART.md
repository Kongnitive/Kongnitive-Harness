# Kongnitive ROS2 EdgeMCP — Quick Start

## 目标

给 AI 一个目标，AI 自主生成 ROS2 节点代码、热推执行、读取 MuJoCo 仿真反馈、迭代改进。
**无需 Gazebo，无需 build，无需重启。**

## 前置条件

- Python 3.10+
- ROS2 Humble
- vector-os-nano（含 MuJoCo 仿真）

## 1) 安装

```bash
# 安装 kongnitive
cd kongnitive-ros2-edgemcp
pip install -e .

# 安装 vector-os-nano（提供 MuJoCo 仿真）
pip install -e /path/to/vector-os-nano[sim]

# 验证 MuJoCo 可用
python -c "
from vector_os_nano.mcp.server import create_sim_agent
a = create_sim_agent(headless=True)
print('Skills:', a.skills)
a.disconnect()
"
```

## 2) 启动服务

```bash
python -m kongnitive_ros2_edgemcp.server
```

启动成功输出：
```
INFO - vector-os-nano MuJoCo agent ready
INFO - Starting Kongnitive ROS2 EdgeMCP server...
```

## 3) 配置 Claude Code

在项目根目录创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "kongnitive": {
      "command": "python",
      "args": ["-m", "kongnitive_ros2_edgemcp.server"]
    }
  }
}
```

## 4) 第一个 AI 迭代 Demo

在 Claude Code 中给出目标：

```
目标：把 MuJoCo 场景中的红色方块移到桌子左边
边界条件：不能碰撞其他物体

请自主生成 ROS2 节点，热推执行，读取日志，迭代直到成功。
```

Claude 会自动执行以下循环：

```
ros_push_node("pick_strategy", <生成的节点脚本>)
  → 等待 3-5 秒
ros_get_node_log("pick_strategy")
  → 分析失败原因
patch_and_restart("pick_strategy", <改进的脚本>)
  → 重复直到 success: true
```

## 5) 手动测试热推

```bash
# 推送示例节点
# （在 Claude Code 或任何 MCP 客户端中）

ros_push_node("vector_demo", open("examples/vector_sim_demo_node.py").read())

# 等待 10 秒（节点 timer 周期）

ros_get_node_log("vector_demo")
# 返回：
# [{"t": "...", "skill": "scan",   "success": true},
#  {"t": "...", "skill": "detect", "success": true,  "failure_reason": null},
#  {"t": "...", "skill": "pick",   "success": false, "failure_reason": "Cannot locate red cube"}]

# 修改节点逻辑后热推新版本
patch_and_restart("vector_demo", <new_script>)
```

## 节点脚本最小模板

```python
import rclpy
from rclpy.node import Node
from kongnitive_ros2_edgemcp.core.vector_bridge import get_agent
from kongnitive_ros2_edgemcp.core.node_log import node_log

class MyNode(Node):
    def __init__(self):
        super().__init__('my_node')
        self.agent = get_agent()
        self.timer = self.create_timer(3.0, self.tick)

    def tick(self):
        result = self.agent.execute_skill("home", {})
        node_log(self.get_name(), {
            "skill": "home",
            "success": result.success,
            "failure_reason": result.failure_reason,
        })

def create_node():
    return MyNode()
```

## 关键约束

- 节点脚本**必须**定义 `create_node()` 并返回 `rclpy.node.Node` 实例
- 节点脚本**必须**调用 `node_log()` 上报结果，否则 `ros_get_node_log` 返回空
- `get_agent()` 返回进程级单例，所有节点共享同一个 MuJoCo 仿真实例
- 热推新版本时，旧节点日志自动清空

## 可用技能

| 技能 | 主要参数 | 说明 |
|------|---------|------|
| `pick` | `object_label: str` | 检测并抓取物体 |
| `place` | `x, y, z: float` | 放置到世界坐标 |
| `detect` | `query: str` | 检测匹配的物体 |
| `scan` | — | 移动到扫描位置 |
| `home` | — | 返回原位 |
| `gripper_open` | — | 张开夹爪 |
| `gripper_close` | — | 闭合夹爪 |
