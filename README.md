# Kongnitive Harness

**Simulation-in-the-loop 具身智能闭环开发系统（当前 MVP 基于 ROS2 + MCP + 仿真后端验证）**

Kongnitive 的目标，是把机器人开发从“人工改代码 → 手动跑仿真 → 看日志猜问题”，推进到“AI 生成节点 → 热推运行 → 读取结构化反馈 → 继续迭代”的闭环。

当前仓库聚焦在一个可运行 MVP：
- 用 `FastMCP` 暴露运行时工具给 AI agent
- 用 `ROS2` 管理可热更新的 Python 节点
- 用 `vector-os-nano` / MuJoCo（默认）或 Isaac Sim（可选）承接仿真执行
- 用 episode、metrics、failure trace 支持可复现调试与自动修复

> 这是一个持续演进中的探索项目。`README` 侧重说明“当前已经能做什么”；更细的环境配置和平台说明放在独立 quickstart 文档里。

## 它解决什么问题

在纯软件开发里，AI 已经能围绕测试和报错形成自我闭环；但在机器人系统里，失败常常只表现为运行期行为异常、时序问题、状态机切换错误或感知-动作衔接失效，反馈分散在仿真画面和日志里，难以直接驱动下一步修复。

Kongnitive 想做的是一层 **Harness**：
- 给 AI 一个稳定的运行入口，而不是一次性脚本
- 给 AI 一组结构化工具，而不是只读原始日志
- 给 AI 一个可重复执行的仿真回路，而不是一次性的人工验证

## 当前能力

### 1. 热推 ROS2 节点

通过 `ros_push_node(node_name, script)`，AI 可以把一个新的 Python ROS2 节点脚本写入运行环境并立即加载。节点脚本只需要满足最小约定：
- 使用 `rclpy`
- 定义 `Node` 子类
- 暴露 `create_node()` 工厂函数

### 2. 运行期观测

MCP server 提供系统与节点维度的可观测性：
- `get_status()`：CPU、内存、磁盘、温度、运行中节点
- `sys_get_logs()`：系统日志缓冲区
- `ros_list_nodes()`：当前热加载节点
- `ros_get_node(node_name)`：节点源码与元信息
- `ros_get_node_log(node_name)`：节点执行日志

### 3. 示例复用与经验沉淀

仓库内置若干示例节点，运行成功后也可以把脚本与最近日志写回成功样例库：
- `ros_get_successful_node_examples()`
- `ros_write_successful_node_examples()`

这让 AI 不必每次都从零生成节点，而是能优先参考“本项目里已经跑通过的做法”。

### 4. 可复现 episode 调试

仓库已经包含一套面向自动迭代的最小 episode 工具：
- `run_episode(seed, profile, strategy)`
- `get_metrics(run_id)`
- `get_failure_trace(run_id)`
- `patch_and_restart(node_name, code)`

其中 `patch_and_restart` 在 patch 失败时会自动回滚到旧版本，降低 AI 试错成本。

## 系统结构

```text
AI Agent
  │ MCP (stdio)
  ▼
Kongnitive FastMCP Server
  ├─ system tools        系统状态 / 系统日志
  ├─ node tools          ROS2 节点热推 / 查询 / 启停 / 删除
  ├─ episode tools       运行 episode / 指标 / failure trace / patch rollback
  └─ NodeManager         基于 rclpy MultiThreadedExecutor 管理节点生命周期
        │
        ├─ hot-pushed ROS2 nodes
        └─ shared sim agent
             ├─ MuJoCo via `vector-os-nano`（默认）
             └─ Isaac Sim（可选）
```

## 仓库结构

```text
kongnitive-ros2-edgemcp/
├─ README.md
├─ QUICKSTART.md
├─ QUICKSTART_LINUX_DOCKER.md
├─ config/
│  ├─ server_config.yaml
│  └─ system_prompt.txt
├─ kongnitive_ros2_edgemcp/
│  ├─ server.py
│  ├─ core/
│  │  ├─ node_manager.py
│  │  ├─ episode_manager.py
│  │  ├─ vector_bridge.py
│  │  └─ ...
│  ├─ tools/
│  └─ utils/
├─ examples/
│  ├─ detector_node.py
│  ├─ planner_node.py
│  ├─ observer_node.py
│  ├─ go2_patrol_node.py
│  ├─ arm_worker_node.py
│  └─ vector_sim_demo_node.py
├─ tests/
└─ vector-os-nano/
```

## 快速开始

### 前置条件

建议至少具备以下环境：
- Python `>=3.8`
- ROS2 Humble（提供 `rclpy`）
- 可用的仿真后端
  - 默认：`vector-os-nano[sim]` / MuJoCo
  - 可选：Isaac Sim

> `rclpy` 不是通过 `pip` 安装的；它由 ROS2 提供。

### 1. 安装项目

```bash
cd /path/to/kongnitive-ros2-edgemcp
pip install -e .
```

如果你要使用默认 MuJoCo 仿真后端，还需要先安装仓库内的 `vector-os-nano`：

```bash
pip install -e /path/to/kongnitive-ros2-edgemcp/vector-os-nano[sim]
```

### 2. 启动 MCP Server

```bash
python -m kongnitive_ros2_edgemcp.server
```

常见环境变量：
- `EDGEMCP_SIM_BACKEND=mujoco`：默认后端
- `EDGEMCP_SIM_BACKEND=isaac`：切到 Isaac Sim
- `MUJOCO_HEADLESS=0`：打开 MuJoCo 可视化窗口
- `ISAAC_HEADLESS=0`：打开 Isaac Sim 可视化窗口
- `EDGEMCP_AGENT_MODE=arm_only`：使用单机械臂模式；默认 `go2_arm`

### 3. 用示例节点验证

仓库里已经提供了几个适合快速试跑的示例：
- `examples/vector_sim_demo_node.py`
- `examples/go2_patrol_node.py`
- `examples/arm_worker_node.py`
- `examples/observer_node.py`

如果你是从 Codex / Claude / 其他 MCP 客户端接入，推荐先做三件事：
1. 调 `get_status()` 确认服务正常
2. 调 `ros_list_capabilities()` 看当前可用能力
3. 将 `examples/` 下的节点脚本通过 `ros_push_node()` 推上去验证链路

## MCP 工具一览

### 系统工具

| 工具 | 作用 |
| --- | --- |
| `get_status()` | 查看系统资源、温度和 ROS 节点状态 |
| `get_system_prompt()` | 获取项目级系统提示词 |
| `sys_get_logs()` | 查询系统日志缓冲区 |

### 节点工具

| 工具 | 作用 |
| --- | --- |
| `ros_push_node(node_name, script)` | 热推并加载一个 ROS2 节点 |
| `ros_list_nodes()` | 列出运行中的节点 |
| `ros_list_capabilities()` | 列出当前可用技能 / 能力 |
| `ros_get_node(node_name)` | 获取节点源码与元信息 |
| `ros_get_node_log(node_name)` | 获取节点执行日志 |
| `ros_start_node(node_name)` | 启动已保存节点 |
| `ros_stop_node(node_name)` | 停止运行中节点 |
| `ros_restart_node(node_name)` | 重启节点 |
| `ros_delete_node(node_name)` | 删除节点脚本与注册信息 |
| `ros_get_successful_node_examples()` | 读取成功样例 |
| `ros_write_successful_node_examples()` | 写入成功样例 |

### Episode / 修复工具

| 工具 | 作用 |
| --- | --- |
| `run_episode(seed, profile, strategy)` | 运行一次可复现仿真 |
| `get_metrics(run_id)` | 查询 episode 指标 |
| `get_failure_trace(run_id)` | 查询阶段级失败诊断 |
| `patch_and_restart(node_name, code)` | 打补丁并自动回滚失败版本 |

## 配置说明

默认配置位于 `config/server_config.yaml`，核心项包括：
- `server.transport`：默认 `stdio`
- `nodes.script_dir`：热推脚本保存目录
- `nodes.max_nodes`：同时运行的节点数量上限
- `logging.buffer_size` / `logging.default_limit`：日志缓冲参数
- `ros2.executor_threads`：ROS2 executor 线程数
- `episode.*`：episode 默认策略与阈值

项目级系统提示词位于 `config/system_prompt.txt`。

## 测试

安装开发依赖后可运行：

```bash
pytest tests
```

当前测试主要覆盖：
- 系统工具与日志缓冲
- 示例节点结构约定
- episode 工具和 rollback 行为
- 无 ROS2 环境下的部分 mock 测试

## 文档导航

如果你只是想尽快跑起来：
- 看 `QUICKSTART.md`

如果你在 Linux / Docker 环境里部署：
- 看 `QUICKSTART_LINUX_DOCKER.md`

如果你想理解项目定位与规划：
- 看 `doc/value-positioning.md`
- 看 `doc/ROS2_Visual_Sim_Closed_Loop_Plan.md`

## 当前状态与边界

这个仓库当前更像一个 **MVP / research harness**，而不是已经稳定封装好的生产系统：
- 核心价值在于“AI + 热推 + 仿真反馈 + 自动迭代”这条链路
- 默认路径仍然绑定 ROS2 与当前仿真后端
- 更广义的 Harness 抽象还在演进中

如果你现在开始使用，最推荐的姿势是：
- 先把它当成一个面向 AI agent 的 MCP runtime
- 先跑通示例节点与 episode 工具
- 再基于你自己的机器人任务逐步扩展行为节点和评估 profile
