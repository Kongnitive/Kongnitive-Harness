# Kongnitive Harness — Quick Start

## 目标

给 AI 一个目标，AI 自主生成 ROS2 节点代码、热推执行、读取仿真反馈、迭代改进。
默认模式下，仿真包含 Go2 四足 + SO-101 机械臂的合并场景，Go2 负责巡逻移动，臂负责操作抓取，通过 ROS2 topic 协调。
ROS2 负责节点间通信，EdgeMCP 负责热推、生命周期与运行时能力视图。
**无需 Gazebo，无需 build，无需重启。**

支持两个仿真后端，通过 `EDGEMCP_SIM_BACKEND` 切换：

| 后端 | 变量值 | 特点 |
|------|--------|------|
| MuJoCo（默认） | `mujoco` | 启动快（2-5s），依赖轻，适合快速迭代 |
| Isaac Sim | `isaac` | NVIDIA PhysX，RTX 渲染，适合高保真仿真 |

## 前置条件

- **Windows 11** 或 Windows 10 22H2+（WSLg GUI 支持）
- **WSL2** with Ubuntu 22.04
- **ROS2 Humble** 已安装在 WSL2 内（见下文安装步骤）
- Python 3.11
- Isaac Sim 后端额外需要：NVIDIA GPU（RTX 20xx+），CUDA 12.x

## 0) 安装 ROS2 Humble（如未安装）

参考：https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html

```bash
# 设置 Locale
sudo apt update && sudo apt install locales
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8

# 启用 Universe 源
sudo apt install software-properties-common
sudo add-apt-repository universe

# 添加 ROS2 软件源
sudo apt update && sudo apt install curl -y
export ROS_APT_SOURCE_VERSION=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | grep -F "tag_name" | awk -F'"' '{print $4}')
curl -L -o /tmp/ros2-apt-source.deb "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.$(. /etc/os-release && echo ${UBUNTU_CODENAME:-${VERSION_CODENAME}})_all.deb"
sudo dpkg -i /tmp/ros2-apt-source.deb

# 安装 ROS2 Desktop
sudo apt update && sudo apt upgrade
sudo apt install ros-humble-desktop

# 写入 ~/.bashrc 自动生效
echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

## 1) WSL2 环境准备

```bash
# 进入 WSL2
wsl -d Ubuntu-22.04

# 安装 OpenGL 支持
sudo apt update
sudo apt install -y mesa-utils libgl1-mesa-glx

# 验证 ROS2
source /opt/ros/humble/setup.bash
ros2 topic list
# 应该能正常执行（可能输出为空，这是正常的）
```

## 2) 安装

### MuJoCo 后端

```bash
source /opt/ros/humble/setup.bash

# 安装 vector-os-nano（MuJoCo 仿真）
pip3 install -e /mnt/d/Projects/edgemcp/kongnitive-ros2-edgemcp/vector-os-nano[sim]

# 安装 kongnitive
cd /mnt/d/Projects/edgemcp/kongnitive-ros2-edgemcp
pip3 install -e .

# 验证
python3 -c "
from vector_os_nano.mcp.server import create_go2_arm_sim_agent
a = create_go2_arm_sim_agent(headless=True)
print('Skills:', a.skills)
a.disconnect()
"
```

### Isaac Sim 后端

Isaac Sim 5.1 支持 pip 直接安装，无需 Omniverse Launcher。**需要 Python 3.11**，建议用独立 venv 避免与 ROS2 依赖冲突。

```bash
# 建立独立 venv（必须用 Python 3.11）
python3.11 -m venv ~/isaac-venv
source ~/isaac-venv/bin/activate
pip install --upgrade pip

# 安装 Isaac Sim 5.1（约 15GB）
pip install isaacsim[all,extscache]==5.1.0 --extra-index-url https://pypi.nvidia.com

# 接受 EULA
export OMNI_KIT_ACCEPT_EULA=YES

# 验证
python -c "from isaacsim import SimulationApp; print('OK')"

# 安装 kongnitive（在同一 venv 内）
cd /mnt/d/Projects/edgemcp/kongnitive-ros2-edgemcp
pip install -e .
```

### Isaac Sim 后端（原生 Ubuntu）

原生 Ubuntu 22.04 上 CUDA 和 Vulkan 均可正常使用，Isaac Sim 支持无头和可视化两种模式。

**前置条件：**
- Ubuntu 22.04（原生，非 WSL2）
- NVIDIA 驱动 525+（`nvidia-smi` 可正常输出）
- CUDA 12.x（`nvcc --version` 可正常输出）
- ROS2 Humble

```bash
source /opt/ros/humble/setup.bash

# 安装 Isaac Sim 5.1（约 15GB）
# 原生 Ubuntu 上 Isaac Sim 与 ROS2 可共存，建议用 Python 3.11 venv
python3.11 -m venv ~/isaac-venv
source ~/isaac-venv/bin/activate
pip install --upgrade pip
pip install isaacsim[all,extscache]==5.1.0 --extra-index-url https://pypi.nvidia.com

# 接受 EULA
export OMNI_KIT_ACCEPT_EULA=YES

# 验证
python -c "from isaacsim import SimulationApp; print('OK')"

# 安装 kongnitive
cd /path/to/kongnitive-ros2-edgemcp
pip install -e .
```

## 3) 启动服务

### MuJoCo 后端

```bash
source /opt/ros/humble/setup.bash

# 无头模式（默认）
python3 -m kongnitive_ros2_edgemcp.server

# 带可视化（MuJoCo 窗口显示在 Windows 桌面）
MUJOCO_HEADLESS=0 python3 -m kongnitive_ros2_edgemcp.server
```

### Isaac Sim 后端

```bash
source ~/isaac-venv/bin/activate
source /opt/ros/humble/setup.bash

# 无头模式（WSL2 唯一可用模式，PhysX 物理仿真走 CUDA 正常运行）
EDGEMCP_SIM_BACKEND=isaac python3 -m kongnitive_ros2_edgemcp.server
```

> **WSL2 不支持 Isaac Sim**：WSL2 内核不暴露 CUDA runtime（`nvidia-smi` 走的是 Windows 侧代理，不等于 CUDA 可用），Isaac Sim 启动时会因 `no CUDA-capable device` 直接 segfault。Isaac Sim 需要原生 Ubuntu 或 Windows 原生环境，WSL2 不可用。

### Isaac Sim 后端（原生 Ubuntu）

```bash
source /opt/ros/humble/setup.bash

# 无头模式
EDGEMCP_SIM_BACKEND=isaac python3 -m kongnitive_ros2_edgemcp.server

# 带可视化（原生 Ubuntu 支持，WSL2 不支持）
EDGEMCP_SIM_BACKEND=isaac ISAAC_HEADLESS=0 python3 -m kongnitive_ros2_edgemcp.server
```

启动成功输出：
```
# MuJoCo
INFO - vector-os-nano merged Go2+Arm MuJoCo agent ready
INFO - Starting Kongnitive ROS2 EdgeMCP server...

# Isaac Sim
INFO - isaac_bridge: Isaac Sim agent ready
INFO - Starting Kongnitive ROS2 EdgeMCP server...
```

## 4) 配置 MCP Server

### Claude Code

在项目根目录（Windows 侧）创建 `.mcp.json`：

**MuJoCo 后端：**
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

**Isaac Sim 后端：**
```json
{
  "mcpServers": {
    "kongnitive": {
      "command": "wsl",
      "args": [
        "-d", "Ubuntu-22.04",
        "bash", "-c",
        "source ~/isaac-venv/bin/activate && source /opt/ros/humble/setup.bash && cd /mnt/d/Projects/edgemcp/kongnitive-ros2-edgemcp && EDGEMCP_SIM_BACKEND=isaac python -m kongnitive_ros2_edgemcp.server"
      ]
    }
  }
}
```

重启 Claude Code 后，MCP 工具会自动加载。

### Codex

在 `~/.codex/config.toml` 中添加：

**MuJoCo 后端：**
```toml
[mcp_servers.kongnitive]
command = “wsl”
args = [
  “-d”, “Ubuntu-22.04”,
  “bash”, “-c”,
  “export LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 && source /opt/ros/humble/setup.bash && cd /mnt/d/Projects/edgemcp/kongnitive-ros2-edgemcp && python3 -m kongnitive_ros2_edgemcp.server”
]
startup_timeout_sec = 20
tool_timeout_sec = 120
```

**Isaac Sim 后端：**
```toml
[mcp_servers.kongnitive]
command = “wsl”
args = [
  “-d”, “Ubuntu-22.04”,
  “bash”, “-c”,
  “export LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 && source ~/isaac-venv/bin/activate && source /opt/ros/humble/setup.bash && cd /mnt/d/Projects/edgemcp/kongnitive-ros2-edgemcp && EDGEMCP_SIM_BACKEND=isaac python3 -m kongnitive_ros2_edgemcp.server”
]
startup_timeout_sec = 60
tool_timeout_sec = 120
```

> Isaac Sim 启动较慢（30-60s），`startup_timeout_sec` 设为 60。

或者直接用 CLI 添加（MuJoCo）：

```powershell
codex mcp add kongnitive -- wsl -d Ubuntu-22.04 bash -c “export LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 && source /opt/ros/humble/setup.bash && cd /mnt/d/Projects/edgemcp/kongnitive-ros2-edgemcp && python3 -m kongnitive_ros2_edgemcp.server”
```

添加后验证：

```powershell
codex mcp list
```

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

### 原生 Ubuntu — Isaac Sim 后端配置

**Claude Code 直接运行在 Ubuntu 机器上：**

```json
{
  "mcpServers": {
    "kongnitive": {
      "command": "bash",
      "args": [
        "-c",
        "source /opt/ros/humble/setup.bash && cd /path/to/kongnitive-ros2-edgemcp && EDGEMCP_SIM_BACKEND=isaac python -m kongnitive_ros2_edgemcp.server"
      ]
    }
  }
}
```

**Claude Code 在 Windows 上，通过 SSH 连接 Ubuntu 机器：**

```json
{
  "mcpServers": {
    "kongnitive": {
      "command": "ssh",
      "args": [
        "user@ubuntu-machine",
        "source /opt/ros/humble/setup.bash && cd /path/to/kongnitive-ros2-edgemcp && EDGEMCP_SIM_BACKEND=isaac python -m kongnitive_ros2_edgemcp.server"
      ]
    }
  }
}
```

**Codex（原生 Ubuntu）：**

```toml
[mcp_servers.kongnitive]
command = "bash"
args = [
  "-c",
  "source /opt/ros/humble/setup.bash && cd /path/to/kongnitive-ros2-edgemcp && EDGEMCP_SIM_BACKEND=isaac python3 -m kongnitive_ros2_edgemcp.server"
]
startup_timeout_sec = 60
tool_timeout_sec = 120
```

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
ros_write_successful_node_examples("pick_strategy", goal="pick place red lego left table")
  → 持久化当前成功模板，供后续 session 复用
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

# 查看当前 runtime 的节点、技能和核心 topics
ros_list_capabilities()

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
- `get_agent()` 返回进程级单例，所有节点共享同一个仿真实例（默认 MuJoCo Go2+臂合并；Isaac Sim 后端同理）
- 节点间协作优先通过 ROS2 topic/service；核心 topic 包括 `/world_model/state`、`/zone_events`、`/go2/position`、`/arm/task_request`、`/arm/task_result`
- 热推新版本时，旧节点日志自动清空
- `ros_get_successful_node_examples()` 会先查持久化成功模板，再查当前 session 成功节点，最后回退到内置 examples

## 可用技能

### 臂技能

| 技能 | 主要参数 | 说明 |
|------|---------|------|
| `pick` | `object_label, mode` | 检测并抓取物体。`mode='hold'` 保持夹持 |
| `place` | `x, y, z` | 放置到 arm base frame 坐标 |
| `detect` | `query` | 检测匹配的物体 |
| `scan` | — | 移动臂到观察位姿 |
| `home` | — | 臂回到初始位置 |
| `gripper_open` | — | 张开夹爪 |
| `gripper_close` | — | 闭合夹爪 |

### Go2 移动技能

| 技能 | 主要参数 | 说明 |
|------|---------|------|
| `walk` | `direction, distance` | 向指定方向行走 |
| `turn` | `angle` | 原地转向 |
| `navigate` | `room` | 导航到指定房间 |
| `stand` | — | 站立 |
| `sit` | — | 坐下 |
| `stop` | — | 紧急停止 |
| `where_am_i` | — | 报告当前位置和朝向 |
| `patrol` | `waypoints` | 巡逻一组路径点 |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `EDGEMCP_SIM_BACKEND` | `mujoco` | `mujoco` = MuJoCo 后端；`isaac` = Isaac Sim 后端 |
| `EDGEMCP_AGENT_MODE` | `go2_arm` | （MuJoCo 专用）`go2_arm` = Go2+臂合并；`arm_only` = 仅臂 |
| `MUJOCO_HEADLESS` | `1` | （MuJoCo 专用）`1` = 无头；`0` = 可视化窗口 |
| `ISAAC_HEADLESS` | `1` | （Isaac Sim 专用）`1` = 无头；`0` = 可视化窗口 |

仅臂模式（MuJoCo，不含 Go2 四足）：

```bash
EDGEMCP_AGENT_MODE=arm_only python3 -m kongnitive_ros2_edgemcp.server
```

## 观察节点示例

仓库内提供了 `examples/observer_node.py`：

- 订阅 `/world_model/state`
- 在对象跨越 left / center / right 区域时发布 `/zone_events`
- 通过 `node_log()` 上报 `zone_change` 事件，供 `ros_get_node_log("observer")` 读取

它用于演示“新增节点通过协议接入系统”，而不是把所有逻辑都塞进同一个控制节点。

## Go2 + 臂协作 Demo

这组步骤演示 Go2 巡逻 + 臂操作的异构节点协作。

### 1) 推送巡逻节点

```python
ros_push_node("go2_patrol", open("examples/go2_patrol_node.py").read())
```

Go2 会依次执行 `turn` + `walk` 巡逻到厨房岛台附近的 3 个路径点，并在 `/go2/position` 发布位置。

### 2) 推送臂操作节点

```python
ros_push_node("arm_worker", open("examples/arm_worker_node.py").read())
```

臂节点订阅 `/arm/task_request`，等待任务指令。`place_at` 为必填字段，坐标语义是 arm base frame。

### 3) 发送操作指令

通过 ROS2 topic 或协调节点发布任务：

```bash
# 在 WSL2 终端
source /opt/ros/humble/setup.bash
ros2 topic pub --once /arm/task_request std_msgs/String \
  '{"data": "{\"action\": \"pick_and_place\", \"object\": \"mug\", \"place_at\": {\"x\": 0.0, \"y\": 0.25, \"z\": 0.05}}"}'
```

### 4) 查看执行结果

```python
ros_get_node_log("go2_patrol")   # 巡逻日志
ros_get_node_log("arm_worker")   # 操作日志
```

协调 topic 一览：
- `/go2/position` — Go2 位置（JSON）
- `/arm/task_request` — 操作指令（JSON，必须包含 `place_at`，且使用 arm base frame）
- `/arm/task_result` — 操作结果

## 多节点协作 Demo（观察节点）

这组步骤用于验证本轮新增的三项能力：

- `WorldModel` 会主动发布到 `/world_model/state`
- observer 节点可以在运行时热推加入系统
- `ros_list_capabilities()` 能返回当前 runtime 的能力视图

### 1) 启动服务

先按上文方式启动 `kongnitive_ros2_edgemcp.server`。

### 2) 观察 world state topic

在 WSL2 新开一个终端：

```bash
source /opt/ros/humble/setup.bash
ros2 topic echo /world_model/state
```

正常情况下，启动后就应能看到 world state JSON 快照，后续检测或机器人状态变化时会继续更新。

### 3) 热推 observer 节点

在 Claude Code、Codex 或任意 MCP 客户端中执行：

```python
ros_push_node("observer", open("examples/observer_node.py").read())
```

然后确认节点已加入当前 runtime：

```python
ros_list_capabilities()
```

预期返回中应至少包含：

- `managed_nodes` 里有 `observer`
- `topics` 里有 `/world_model/state`
- `topics` 里有 `/zone_events`

### 4) 观察 zone events

再开一个 WSL2 终端：

```bash
source /opt/ros/humble/setup.bash
ros2 topic echo /zone_events
```

此时 observer 已经在等待 world state 更新，并会在物体跨越 left / center / right 区域时发布事件。

### 5) 触发一次对象移动

可用任一现有控制节点让场景物体位置变化，例如：

```python
ros_push_node("vector_demo", open("examples/vector_sim_demo_node.py").read())
```

等待一个 timer 周期后，`vector_demo` 会执行 scan / detect / pick / place。  
如果物体位置跨过 observer 的区域边界，`/zone_events` 会收到 `zone_change` 事件。

### 6) 读取 observer 的结构化日志

在 MCP 客户端中执行：

```python
ros_get_node_log("observer")
```

预期会看到 observer 写入的结构化事件，例如：

- `event: "zone_change"`
- `object_id`
- `label`
- `zone`
- `position`
- `timestamp`

### 7) 验证这次改动的叙事

如果上面三路都成立，就说明这次改动已经形成了完整演示链路：

- 世界状态通过 ROS2 topic 对外广播，而不只靠 service query
- observer 可以在不修改主控制节点的情况下被热推加入系统
- EdgeMCP 提供的是控制面能力视图，而节点间协作本身走 ROS2 协议
