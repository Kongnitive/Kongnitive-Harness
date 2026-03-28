# Kongnitive ROS2 EdgeMCP Quick Start

## 0) 目标

先跑通 **单机器人**：
- Gazebo 在 WSL (`Ubuntu-22.04`)
- EdgeMCP 在 Docker 容器

## 1) 前置条件

- WSL 发行版：`Ubuntu-22.04`
- ROS2 Humble 与 Gazebo 桥接已安装
- Docker Desktop 可用

快速检查：

```powershell
wsl -l -v
wsl -d Ubuntu-22.04 --% bash -lc "source /opt/ros/humble/setup.bash && ros2 pkg list | head -n 3"
docker --version
docker compose version
```

## 2) 启动 Gazebo（PowerShell）

```powershell
Set-Location D:\Projects\edgemcp\kongnitive-ros2-edgemcp
.\scripts\start_gazebo_host.ps1 -LaunchCommand "ros2 launch ros_gz_sim gz_sim.launch.py gz_args:='/mnt/d/Projects/edgemcp/kongnitive-ros2-edgemcp/deploy/single_robot/worlds/tabletop.sdf -r'" -RosDomainId 0 -WslDistro Ubuntu-22.04
```

如果 GUI 崩溃，先用 headless 验证：

```powershell
.\scripts\start_gazebo_host.ps1 -LaunchCommand "ros2 launch ros_gz_sim gz_sim.launch.py gz_args:='/mnt/d/Projects/edgemcp/kongnitive-ros2-edgemcp/deploy/single_robot/worlds/tabletop.sdf -r -s'" -RosDomainId 0 -WslDistro Ubuntu-22.04
```

## 3) 启动 EdgeMCP（新开一个 PowerShell）

```powershell
Set-Location D:\Projects\edgemcp\kongnitive-ros2-edgemcp
.\scripts\start_single_robot_edgemcp.ps1 -RosDomainId 0
```

## 4) 停止

```powershell
Set-Location D:\Projects\edgemcp\kongnitive-ros2-edgemcp
docker compose -f deploy/single_robot/docker-compose.single-robot.yml down
```

## 5) 关键约束

- Gazebo 与 EdgeMCP 必须使用相同 `ROS_DOMAIN_ID`（当前示例是 `0`）。
- 单机器人入口使用：
  - `deploy/single_robot/docker-compose.single-robot.yml`
  - `deploy/single_robot/config/server_config.yaml`

## 6) 多机器人（可选，后续）

```powershell
Set-Location D:\Projects\edgemcp\kongnitive-ros2-edgemcp
.\scripts\start_two_robot_edgemcp.ps1 -RosDomainId 0
```

详情见：
- `deploy/multi_robot/README.md`
