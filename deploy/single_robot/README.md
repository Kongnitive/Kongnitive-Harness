# Single Robot MVP (Recommended First Run)

Use this as the default path to get one robot running end-to-end:
- shared Gazebo world on host/WSL
- one EdgeMCP container
- one robot namespace (`/robot_a`)

## Files

- `docker-compose.single-robot.yml`
- `config/server_config.yaml`

## Start EdgeMCP

PowerShell:

```powershell
Set-Location D:\Projects\edgemcp\kongnitive-ros2-edgemcp
.\scripts\start_single_robot_edgemcp.ps1 -RosDomainId 0
```

Bash:

```bash
cd /path/to/kongnitive-ros2-edgemcp
./scripts/start_single_robot_edgemcp.sh
```

## Start Gazebo (host/WSL)

PowerShell:

```powershell
.\scripts\start_gazebo_host.ps1 -LaunchCommand "ros2 launch my_pick_place_sim tabletop.launch.py" -RosDomainId 0 -WslDistro Ubuntu
```

## Stop

```powershell
docker compose -f deploy/single_robot/docker-compose.single-robot.yml down
```

## Notes

- Keep the same `ROS_DOMAIN_ID` between Gazebo and EdgeMCP.
- This setup is intentionally minimal; extend to multi-robot after single robot is stable.
