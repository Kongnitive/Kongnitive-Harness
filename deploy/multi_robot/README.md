# Two-Robot MVP (Shared Gazebo World)

This folder provides a minimal, practical scaffold for:
- one shared Gazebo scene
- two robot software stacks (`robot_a`, `robot_b`)
- one EdgeMCP instance per robot

## Target Topology

- Shared simulation: one Gazebo world
- Robot A stack: `NemoClaw A -> EdgeMCP A -> ROS2 namespace /robot_a`
- Robot B stack: `NemoClaw B -> EdgeMCP B -> ROS2 namespace /robot_b`
- Same `ROS_DOMAIN_ID` for all components

## Files

- `docker-compose.two-robots.yml`:
  runs `edgemcp_robot_a` and `edgemcp_robot_b`.
- `config/robot_a/server_config.yaml`:
  EdgeMCP config for robot A.
- `config/robot_b/server_config.yaml`:
  EdgeMCP config for robot B.
- `templates/multi_robot_shared_world.launch.py`:
  ROS2 launch template for one Gazebo world + two robots.

## Start EdgeMCP (two robots)

From repository root:

```powershell
.\scripts\start_two_robot_edgemcp.ps1 -RosDomainId 0
```

```bash
./scripts/start_two_robot_edgemcp.sh
```

## Start Gazebo Shared World

Use your own launch package, or adapt the template in
`deploy/multi_robot/templates/multi_robot_shared_world.launch.py`.

PowerShell example:

```powershell
.\scripts\start_gazebo_host.ps1 -LaunchCommand "ros2 launch my_pick_place_sim multi_robot_shared_world.launch.py" -RosDomainId 0 -WslDistro Ubuntu
```

## Namespace and Isolation Rules

- Keep one namespace per robot:
  - `/robot_a/*`
  - `/robot_b/*`
- Keep separate EdgeMCP script directories per robot.
- Keep control topics/services/actions namespaced.
