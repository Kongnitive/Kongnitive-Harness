# Kongnitive Harness

**Simulation-in-the-Loop 具身智能闭环开发系统 — Harness Engineering for Robot AI**

> **近期计划**：当前实现以 ROS2 + MuJoCo 为载体完成 MVP 验证。近期将对整体架构进行重构，使 Harness 层与底层通信框架（ROS2）和仿真后端解耦，具备更广泛的适用性。

> 这是个人业余时间的探索项目，进度和更新节奏以兴趣驱动为主。

## 背景与问题

以 Codex、Claude Code 为代表的 AI 编程工具，已经在软件开发领域初步实现了"写代码→运行→报错→修复"的自我闭环。给定一个明确的目标，AI 可以自主迭代，直到代码通过测试。这套模式在纯软件场景下运转良好，因为执行环境是确定的，失败信息是结构化的，反馈可以直接驱动下一次修改。

但在机器人和具身智能领域，这套闭环尚未建立。当前的机器人仿真和调试流程基本还是传统路径：人工改代码、手动部署 ROS2 节点、在仿真器里跑测试、肉眼看行为是否正常、再判断问题出在哪。整个流程割裂、慢、依赖人的经验判断。

根本原因在于，机器人系统的"执行环境"比普通软件复杂得多——时序问题、状态机切换、感知与动作衔接、物理约束，这些问题在静态代码里看不出来，只有在运行中才会暴露。而现有工具链并没有把仿真执行的结果结构化地接回开发流程，每次失败的证据都停留在日志文件里，需要人去消化再决定怎么改。

## Harness Engineering：驾驭 AI Agent 的工程

在讨论"让 AI 做机器人开发"之前，有一个更基础的问题需要先回答：如何设计一套系统，让 AI agent 在给定目标和边界约束下，真正自主、高效地完成任务，而不是频繁失控、偏离方向或等待人工干预？

这个问题本身就是一门工程，我们把它称为 **Harness Engineering**——驾驭工程。

它不是在问"AI 能不能做"，而是在问"怎么搭架子，让 AI 做得稳"。核心设计挑战有三个：

**目标要足够可操作。** 自然语言目标对人清晰，对 AI 执行来说太模糊。Harness Engineering 的第一步是把目标转化为结构化的任务描述——包含任务类型、成功标准、约束条件和评估 profile。这是 AI agent 行动的锚点，也是判断每次执行是否有效的依据。

**边界要通过环境而非指令来约束。** 单靠 prompt 告诉 AI "不要做 X"是脆弱的。更可靠的方式是在运行时环境上划定边界：哪些 behavior 可以修改、哪些节点在保护范围内、哪些操作需要人工确认。Kongnitive 的权限分层和 behavior backend 设计，本质上都是这类边界的工程实现。

**反馈要结构化到可以直接驱动行动。** AI agent 的自主能力上限，取决于它能读到多高质量的反馈。如果失败信息只是一堆原始日志，agent 需要大量推理才能定位问题，效率和准确率都会下降。Kongnitive 把 failure trace、metrics 和 node log 统一结构化，目的是让 agent 拿到的不是"发生了什么"，而是"哪里出了什么问题"——从而让 patch 有据可依，而不是靠猜。

## 项目目标

Kongnitive Harness 的目标是把 simulation 从测试工具变成开发主循环的一部分，在 Harness Engineering 的设计原则下，构建一套 simulation-in-the-loop 的具身智能闭环开发系统。

人负责定义目标、约束和优化方向；AI 依托 Kongnitive Harness 提供的运行时能力，在仿真环境中持续修改行为代码，驱动仿真执行，读取结构化反馈，再根据证据继续迭代——最终形成一个可验证、可复用、经验可沉淀的闭环。

> **仿真说明**：当前 MVP 阶段借助 [vector-os-nano](https://github.com/vector-robotics/vector-os-nano) 提供的 MuJoCo 仿真环境进行验证。vector-os-nano 仅作为仿真后端使用，Kongnitive 的核心架构（热推引擎、MCP 工具层、AI 迭代闭环）与具体仿真实现无耦合。

## 系统概览

传统 ROS2 开发：修改代码 → 编译 → 重启 → 验证（5-20 分钟/轮）

Kongnitive：AI 生成代码 → 热推 → 观察仿真结果 → 再迭代（< 5 秒/轮）

在当前实现里，ROS2 负责节点间通信骨干，EdgeMCP 负责热推、生命周期和运行时能力视图。

## 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Claude (AI Agent)                         │
│  目标："让 Go2 巡逻到厨房，用臂抓取杯子放到岛台左边"          │
└───────────┬─────────────────────────────────────────────────┘
            │ MCP (stdio)
            ▼
┌─────────────────────────────────────────────────────────────┐
│              kongnitive FastMCP Server                       │
│                                                              │
│  ┌──────────────────┐   ┌───────────────────────────────┐   │
│  │   MCP Tools      │   │      NodeManager              │   │
│  │                  │   │  (rclpy MultiThreadedExecutor)│   │
│  │ ros_push_node ───┼──►│   热推/卸载 ROS2 节点         │   │
│  │ ros_get_node_log─┼──►│   NodeLogStore (per-node log) │   │
│  │ patch_and_restart│   └───────────┬───────────────────┘   │
│  │ ros_list_capab. │               │ executor spin          │
│  │ ros_list_nodes   │               ▼                        │
│  │ get_status       │      ┌────────────────────┐           │
│  └──────────────────┘      │  AI 生成的 ROS2 节点│           │
│                             │  go2_patrol (巡逻)  │           │
│                             │  arm_worker (操作)  │           │
│                             │  observer (观察)    │           │
│                             └────────┬───────────┘           │
│                                      │ ROS2 topics           │
│                                      ▼                       │
│              /go2/position  /arm/task_request  /zone_events  │
│              /world_model/state      /arm/task_result         │
└──────────────────────────────────────┼───────────────────────┘
                                       │ agent.execute_skill()
                                       ▼
                          ┌────────────────────────┐
                          │   物理仿真后端（MVP）    │
                          │  MuJoCo · Go2 + SO-101  │
                          │  success / failure 反馈  │
                          └────────────────────────┘
                    (当前使用 vector-os-nano 仿真库验证；
                     生产环境可替换为真实硬件驱动)
```

### Go2 + 臂合并仿真

默认模式下，`get_agent()` 返回一个同时控制 Go2 四足和 SO-101 机械臂的 Agent：

- 臂固定在 Go2 背部（`pos="0.1 0 0.08"`）
- 单一 MuJoCo 物理实例，1kHz 物理线程同时驱动步态和关节
- 物体放在 20m×14m 室内场景的厨房岛台上
- Go2 技能（walk/turn/patrol）和臂技能（pick/place/detect）共存于同一个 Agent
- 异构节点通过 ROS2 topic 协调：巡逻节点只调移动技能，操作节点只调臂技能

## AI 自主迭代闭环

```
输入：目标 + 边界条件
        │
        ▼
  AI 生成节点代码  ← 策略：扫描→检测→抓取→放置
        │ ros_push_node(name, script)
        ▼
  节点热推加载     ← <100ms 零停机
        │ executor 运行
        ▼
  节点执行技能     ← agent.execute_skill() → MuJoCo 真实物理
  写入执行日志     ← node_log(result)
        │ ros_get_node_log(name)
        ▼
  AI 分析结果
        │
   ┌────┴────┐
   ▼         ▼
达到目标   未达到目标
  结束     patch_and_restart → 回到"热推加载"
```

## 快速开始

### 前置条件

- **Windows 11** 或 Windows 10 22H2+（WSLg GUI 支持）
- **WSL2** with Ubuntu 22.04
- **ROS2 Humble** 已安装在 WSL2 内
- Python 3.10+
- [vector-os-nano](https://github.com/vector-robotics/vector-os-nano)（提供 MuJoCo 仿真）

### 安装

```bash
# 进入 WSL2
wsl -d Ubuntu-22.04

# 安装 OpenGL 支持（MuJoCo 可视化需要）
sudo apt update
sudo apt install -y mesa-utils libgl1-mesa-glx

# 验证 ROS2
source /opt/ros/humble/setup.bash
ros2 topic list

# 安装 vector-os-nano（MuJoCo 仿真）
pip install -e /mnt/d/Projects/edgemcp/kongnitive-ros2-edgemcp/vector-os-nano[sim]

# 安装 kongnitive
cd /mnt/d/Projects/edgemcp/kongnitive-ros2-edgemcp
pip install -e .
```

### 启动服务

```bash
# 在 WSL2 内执行
source /opt/ros/humble/setup.bash

# 方式 1: 无头模式（默认，更快）
python -m kongnitive_ros2_edgemcp.server

# 方式 2: 带可视化（MuJoCo 窗口显示在 Windows 桌面）
MUJOCO_HEADLESS=0 python -m kongnitive_ros2_edgemcp.server
```

启动成功输出：
```
INFO - vector-os-nano merged Go2+Arm MuJoCo agent ready
INFO - Starting Kongnitive ROS2 EdgeMCP server...
```

如果启用可视化，Windows 桌面会弹出 MuJoCo 仿真窗口。

### 配置 Claude Code MCP

在项目根目录（Windows 侧）创建或更新 `.mcp.json`：

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

## MCP 工具列表

### 系统工具

| 工具 | 说明 |
|------|------|
| `get_status()` | CPU、内存、磁盘、温度、ROS 节点状态 |
| `get_system_prompt()` | 获取 AI 操作指引 |
| `sys_get_logs(filter, level, source, limit)` | 过滤系统日志 |

### 节点管理

| 工具 | 说明 |
|------|------|
| `ros_push_node(node_name, script)` | **热推 ROS2 节点（核心工具）** |
| `ros_get_node_log(node_name, limit)` | **读取节点实时执行日志** |
| `ros_list_capabilities()` | 查看当前 runtime 可见的节点、技能与核心 topic |
| `ros_get_successful_node_examples(goal_filter, limit)` | 检索成功模板，优先持久化样本，再看当前 session，最后回退到内置 examples |
| `ros_write_successful_node_examples(node_name, goal, summary, tags, ...)` | 将当前成功节点显式持久化为可复用模板 |
| `ros_list_nodes()` | 列出运行中的节点 |
| `ros_get_node(node_name)` | 获取节点当前源码 |
| `ros_start_node(node_name)` | 启动已保存的节点 |
| `ros_stop_node(node_name)` | 停止节点 |
| `ros_restart_node(node_name)` | 重启节点 |
| `patch_and_restart(node_name, code)` | 打补丁并重启（失败自动回滚） |

### AI 迭代工具

| 工具 | 说明 |
|------|------|
| `run_episode(seed, profile, strategy)` | 运行可复现的仿真 episode |
| `get_metrics(run_id)` | 获取 episode 指标和聚合统计 |
| `get_failure_trace(run_id)` | 获取 episode 阶段级失败诊断 |

## 节点脚本模板

所有 AI 生成的机器人控制节点必须遵循此模式：

```python
import rclpy
from rclpy.node import Node
from kongnitive_ros2_edgemcp.core.vector_bridge import get_agent
from kongnitive_ros2_edgemcp.core.node_log import node_log

class MyStrategyNode(Node):
    def __init__(self):
        super().__init__('my_strategy')
        self.agent = get_agent()          # 共享 MuJoCo Agent（单例）
        self.timer = self.create_timer(3.0, self.run_task)

    def run_task(self):
        result = self.agent.execute_skill("pick", {"object_label": "red_cube"})

        # 必须上报 — AI 通过 ros_get_node_log 读取
        node_log(self.get_name(), {
            "skill": "pick",
            "success": result.success,
            "failure_reason": result.failure_reason,
        })

def create_node():
    return MyStrategyNode()
```

### 可用技能

#### 臂技能

| 技能 | 主要参数 | 说明 |
|------|---------|------|
| `pick` | `object_label, mode` | 检测并抓取物体。`mode='hold'` 保持夹持（后接 place 时必须用） |
| `place` | `x, y, z` | 放置到 arm base frame 坐标 |
| `detect` | `query` | 检测匹配的物体 |
| `scan` | — | 移动臂到观察位姿 |
| `home` | — | 臂回到初始位置 |
| `gripper_open` | — | 张开夹爪 |
| `gripper_close` | — | 闭合夹爪 |

#### Go2 移动技能

| 技能 | 主要参数 | 说明 |
|------|---------|------|
| `walk` | `direction, distance` | 向指定方向行走 |
| `turn` | `angle` | 原地转向（角度） |
| `navigate` | `room` | 导航到指定房间 |
| `stand` | — | 站立 |
| `sit` | — | 坐下 |
| `lie_down` | — | 趴下 |
| `stop` | — | 紧急停止 |
| `where_am_i` | — | 报告当前位置和朝向 |
| `patrol` | `waypoints` | 巡逻一组路径点 |

### 示例节点

| 文件 | 说明 |
|------|------|
| `examples/vector_sim_demo_node.py` | 完整臂操作示例（推荐起点） |
| `examples/go2_patrol_node.py` | Go2 巡逻节点，使用 `turn` + `walk` 巡逻并发布位置到 `/go2/position` |
| `examples/arm_worker_node.py` | 臂操作节点，订阅 `/arm/task_request` 执行 pick/place；`place_at` 必填且使用 arm base frame |
| `examples/observer_node.py` | 观察节点，订阅 `/world_model/state`，发布 `/zone_events` |

## 热推机制

```
NodeManager.push_node() 执行流程：
  1. 保存脚本到 ~/.kongnitive_ros2_edgemcp/nodes/
  2. 卸载旧节点（如存在）
  3. importlib 动态加载新模块
  4. 调用 create_node() 创建实例
  5. 添加到 MultiThreadedExecutor
  6. 清空旧日志（AI 只看新版本结果）
  总耗时：< 100ms
```

## 项目结构

```
kongnitive-ros2-edgemcp/
├── kongnitive_ros2_edgemcp/
│   ├── server.py                  # FastMCP 服务入口
│   ├── core/
│   │   ├── node_manager.py        # 热推引擎
│   │   ├── node_log.py            # 节点执行日志 store
│   │   ├── vector_bridge.py       # vector-os-nano Agent 单例（支持 go2_arm / arm_only）
│   │   └── episode_manager.py     # 可复现 episode 循环
│   ├── tools/
│   │   ├── system_tools.py        # 系统监控
│   │   ├── node_tools.py          # 节点管理
│   │   └── episode_tools.py       # Episode + patch 工具
├── examples/
│   ├── vector_sim_demo_node.py    # MuJoCo 臂操作示例（推荐起点）
│   ├── go2_patrol_node.py         # Go2 巡逻节点示例
│   ├── arm_worker_node.py         # 臂操作 worker 节点示例
│   ├── observer_node.py           # 观察节点示例
│   └── detector_node.py           # 基础节点示例
├── vector-os-nano/                # MuJoCo 仿真库（子目录）
│   └── vector_os_nano/hardware/sim/
│       ├── mujoco_go2_with_arm.py # Go2+臂合并控制器
│       ├── mujoco_go2.py          # Go2 四足控制器
│       └── mujoco_arm.py          # 单臂控制器
└── README.md
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `EDGEMCP_AGENT_MODE` | `go2_arm` | `go2_arm` = Go2+臂合并 agent；`arm_only` = 仅臂 agent |
| `MUJOCO_HEADLESS` | `1` | `1` = 无头模式；`0` = 打开 MuJoCo 可视化窗口 |

## 性能指标

| 指标 | 目标 |
|------|------|
| 节点热推时间 | < 100ms ✅ |
| 工具响应时间 | < 500ms |
| 并发节点数 | 10+ |

## 故障排查

**节点加载失败**
- 确认脚本定义了 `create_node()` 函数
- 确认 `create_node()` 返回 `rclpy.node.Node` 实例
- 查看日志：`sys_get_logs(filter="error")`

**MuJoCo Agent 未就绪**
- 确认已安装 `vector-os-nano[sim]`：`pip install -e /path/to/vector-os-nano[sim]`
- 服务启动日志应包含 `vector-os-nano merged Go2+Arm MuJoCo agent ready`

**ros_get_node_log 返回空**
- 节点脚本中必须调用 `node_log()` 上报结果
- 等待至少一个 timer 周期（默认 3s）后再读取

**ros_get_successful_node_examples 返回空或不稳定**
- 当前版本会优先读取持久化成功样本
- 若当前 session 有任意 `success: true` 日志，也会自动纳入候选，`skill == "goal"` 的样本仅排序更高
- 若前两者都没有，会回退到 `examples/` 下的内置模板
- 任务跑通后可调用 `ros_write_successful_node_examples(...)` 显式持久化

## License

MIT License
