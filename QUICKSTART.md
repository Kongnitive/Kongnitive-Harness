# Kongnitive ROS2 EdgeMCP — Quick Start

## 目标

给 AI 一个目标，AI 自主生成 ROS2 节点代码、热推执行、读取 MuJoCo 仿真反馈、迭代改进。
**无需 Gazebo，无需 build，无需重启。**

## 前置条件

- **Windows 11** 或 Windows 10 22H2+（WSLg GUI 支持）
- **WSL2** with Ubuntu 22.04
- **ROS2 Humble** 已安装在 WSL2 内
- Python 3.10+

## 1) WSL2 环境准备

```bash
# 进入 WSL2
wsl -d Ubuntu-22.04

# 安装 OpenGL 支持（MuJoCo 可视化需要）
sudo apt update
sudo apt install -y mesa-utils libgl1-mesa-glx

# 验证 ROS2
source /opt/ros/humble/setup.bash
ros2 topic list
# 应该能正常执行（可能输出为空，这是正常的）
```

## 2) 安装

```bash
# 在 WSL2 内执行
source /opt/ros/humble/setup.bash

# 安装 vector-os-nano（MuJoCo 仿真）
pip3 install -e /mnt/d/Projects/edgemcp/kongnitive-ros2-edgemcp/vector-os-nano[sim]

# 安装 kongnitive
cd /mnt/d/Projects/edgemcp/kongnitive-ros2-edgemcp
pip3 install -e .

# 验证 MuJoCo 可用
python3 -c "
from vector_os_nano.mcp.server import create_sim_agent
a = create_sim_agent(headless=True)
print('Skills:', a.skills)
a.disconnect()
"
```

## 3) 启动服务

```bash
# 在 WSL2 内执行
source /opt/ros/humble/setup.bash

# 方式 1: 无头模式（默认，更快）
python3 -m kongnitive_ros2_edgemcp.server

# 方式 2: 带可视化（MuJoCo 窗口显示在 Windows 桌面）
MUJOCO_HEADLESS=0 python3 -m kongnitive_ros2_edgemcp.server
```

启动成功输出：
```
INFO - vector-os-nano MuJoCo agent ready
INFO - Starting Kongnitive ROS2 EdgeMCP server...
```

如果启用可视化，Windows 桌面会弹出 MuJoCo 仿真窗口。

## 4) 配置 Claude Code / Codex

### Claude Code

在项目根目录（Windows 侧）创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "kongnitive": {
      "command": "wsl",
      "args": [
        "-d", "Ubuntu-22.04",
        "bash", "-c",
        "source /opt/ros/humble/setup.bash && cd /mnt/d/Projects/edgemcp/kongnitive-ros2-edgemcp && python -m kongnitive_ros2_edgemcp.server"
      ]
    }
  }
}
```

**带可视化版本**（调试时推荐）：
```json
{
  "mcpServers": {
    "kongnitive": {
      "command": "wsl",
      "args": [
        "-d", "Ubuntu-22.04",
        "bash", "-c",
        "source /opt/ros/humble/setup.bash && cd /mnt/d/Projects/edgemcp/kongnitive-ros2-edgemcp && MUJOCO_HEADLESS=0 python -m kongnitive_ros2_edgemcp.server"
      ]
    }
  }
}
```

重启 Claude Code 后，MCP 工具会自动加载。

### Codex

当前 Codex 已公开文档和 CLI 可直接确认的 MCP 配置方式，是共享配置：

- `codex mcp add ...`
- `~/.codex/config.toml` 下的 `[mcp_servers.<name>]`

如果你在 Codex 里执行 `/mcp`，显示 `No MCP servers configured`，通常说明 Codex **没有识别到该配置**。  
目前不要使用下面这种“项目作用域 MCP”写法，因为当前版本下它不会被 `/mcp` 识别：

```toml
[projects.'D:\Projects\edgemcp\kongnitive-ros2-edgemcp'.mcp_servers.kongnitive]
```

建议先使用 Codex 当前可识别的标准写法，在 `~/.codex/config.toml` 中添加：

```toml
[mcp_servers.kongnitive]
command = "wsl"
args = [
  "-d", "Ubuntu-22.04",
  "bash", "-c",
  "export LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 && source /opt/ros/humble/setup.bash && cd /mnt/d/Projects/edgemcp/kongnitive-ros2-edgemcp && python3 -m kongnitive_ros2_edgemcp.server"
]
startup_timeout_sec = 20
tool_timeout_sec = 120
```

**带可视化版本**：

```toml
[mcp_servers.kongnitive]
command = "wsl"
args = [
  "-d", "Ubuntu-22.04",
  "bash", "-c",
  "export LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 && source /opt/ros/humble/setup.bash && cd /mnt/d/Projects/edgemcp/kongnitive-ros2-edgemcp && MUJOCO_HEADLESS=0 python3 -m kongnitive_ros2_edgemcp.server"
]
startup_timeout_sec = 20
tool_timeout_sec = 120
```

或者直接用 CLI 添加：

```powershell
codex mcp add kongnitive -- wsl -d Ubuntu-22.04 bash -c "export LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 && source /opt/ros/humble/setup.bash && cd /mnt/d/Projects/edgemcp/kongnitive-ros2-edgemcp && python3 -m kongnitive_ros2_edgemcp.server"
```

添加后可验证：

```powershell
codex mcp list
```

如果这里能看到 `kongnitive`，Codex 里的 `/mcp` 才会显示它。

### 关于“只在特定目录生效”

当前能确认的官方写法是共享 MCP 配置，没有看到 Codex 官方文档提供“按目录自动启用 MCP server”的配置格式。  
也就是说，**当前版本更稳妥的结论是：Codex MCP 先按全局共享配置处理，不要依赖目录级 `mcp_servers` 自动生效。**

如果你必须做隔离，现实可行的做法一般是：

- 为不同项目使用不同的 server 名称，按需启用/删除
- 用不同的 Codex 配置环境或不同系统用户隔离
- 先保留全局 MCP，再在项目里的 `AGENTS.md` 约束何时使用它

### Codex 闪退 / 日志排查

如果 MCP server 启动后立刻消失，优先看 Codex 自己的日志：

```powershell
Get-Content "$env:USERPROFILE\.codex\log\codex-tui.log" -Tail 200
```

常见关键字：

- `Failed to read MCP server stderr`
- `stream did not contain valid UTF-8`
- `startup timeout`
- `failed to spawn`

如果要确认到底是服务本身退出，还是被 Codex 判定为异常，直接在 PowerShell 手工跑同一条命令：

```powershell
wsl -d Ubuntu-22.04 bash -lc "export LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1; source /opt/ros/humble/setup.bash && cd /mnt/d/Projects/edgemcp/kongnitive-ros2-edgemcp && python3 -m kongnitive_ros2_edgemcp.server"
```

如果想保留启动报错，避免窗口一闪而过，可把 stderr 落盘到 WSL 文件：

```powershell
wsl -d Ubuntu-22.04 bash -lc "export LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1; source /opt/ros/humble/setup.bash && cd /mnt/d/Projects/edgemcp/kongnitive-ros2-edgemcp && python3 -m kongnitive_ros2_edgemcp.server 2>/tmp/kongnitive-mcp.stderr.log"
```

然后查看：

```powershell
wsl -d Ubuntu-22.04 cat /tmp/kongnitive-mcp.stderr.log
```

如果日志里出现 `stream did not contain valid UTF-8`，通常说明服务往 stderr 打了非 UTF-8 内容。上面的 `LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1` 一般能解决；若仍存在，就需要继续排查是哪个依赖在输出异常编码。

## 5) 第一个 AI 迭代 Demo

在 Claude Code 中给出目标：

```
目标：把 MuJoCo 场景中的红色乐高移到桌子左边
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
