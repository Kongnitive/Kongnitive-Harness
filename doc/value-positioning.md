# Kongnitive ROS2 EdgeMCP 价值定位记录

记录时间：2026-03-14

## 核心结论

`kongnitive-ros2-edgemcp` 的核心价值不在于替代通用 ROS MCP 的“观测/调用”能力，而在于提供：

- 运行时热插拔（hot-swap）
- AI 直接生成并上线新 ROS2 Python 节点
- 无需重启系统、无需完整重编译部署

一句话：

- 通用 ROS MCP：操作已有系统
- Kongnitive ROS2 EdgeMCP：让系统在运行中获得新能力（自进化）

## 与通用 ROS MCP 的能力边界

通用 ROS MCP（行业常见）通常强调：

- 列出 topic/service/type
- 查看消息类型定义（含自定义）
- 发布/订阅 topic
- 调用 service
- 参数读写
- （计划中）action 与权限控制

Kongnitive ROS2 EdgeMCP（当前 Phase 1）强调：

- `ros_push_node` + NodeManager 动态加载
- 节点生命周期管理（list/get/start/stop/restart）
- AI 迭代闭环（读状态 -> 分析 -> 生成 -> 热更新）

## 什么时候“用别人的 ROS MCP 就够了”

- 目标是调试、巡检、运维
- 系统能力已具备，只需调用现有接口
- 不要求在线新增能力或在线改业务逻辑

## 什么时候“必须保留这套”

- 需要远程在线修复生产机器人
- 需要持续无人值守优化（自动迭代）
- 现场无法接受频繁重启与完整部署链路

## 当前短板（客观）

截至当前版本（Phase 1）：

- topic/service/action 工具尚未补齐
- 权限控制尚未落地
- 更偏“能力注入内核”，通用 ROS 调试面还不完整

## 推荐路线

- 短期：补齐通用 ROS MCP 基础能力（topic/service/action/param）
- 中期：保留并强化 hot-swap/AI 生成上线能力作为差异化护城河
- 策略：与通用 ROS MCP 形成“组合能力”而非互斥替代
