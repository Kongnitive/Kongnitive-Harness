# Kongnitive ROS2 EdgeMCP Quick Start for Ubuntu 22.04 + Docker

## 0) Goal

Bring up the **single-robot** path on **Ubuntu 22.04 + Docker**:
- Gazebo runs on the Ubuntu host
- EdgeMCP runs in a Docker container

This is the simplest Linux-native path and matches the repository scripts.

## 1) Prerequisites

- Ubuntu 22.04
- ROS 2 Humble installed
- `ros_gz_sim` and related Gazebo bridge packages installed
- Docker Engine and Docker Compose available

Quick checks:

```bash
source /opt/ros/humble/setup.bash
ros2 pkg list | head -n 5

docker --version
docker compose version
docker info
```

If `docker info` reports `Cannot connect to the Docker daemon`, start Docker:

```bash
sudo systemctl enable --now docker
```

If your user cannot access Docker, add it to the `docker` group and re-login:

```bash
sudo usermod -aG docker $USER
```

## 2) Enter the Repository

```bash
cd /path/to/kongnitive-ros2-edgemcp
```

All following commands assume you are in the repository root.

## 3) Start Gazebo on the Host

Open terminal 1 and start Gazebo with the same `ROS_DOMAIN_ID` that the container will use:

```bash
cd /path/to/kongnitive-ros2-edgemcp
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=0
bash ./scripts/start_gazebo_host.sh "ros2 launch ros_gz_sim gz_sim.launch.py gz_args:='deploy/single_robot/worlds/tabletop.sdf -r'"
```

If the GUI is unstable, verify in headless mode first:

```bash
cd /path/to/kongnitive-ros2-edgemcp
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=0
bash ./scripts/start_gazebo_host.sh "ros2 launch ros_gz_sim gz_sim.launch.py gz_args:='deploy/single_robot/worlds/tabletop.sdf -r -s'"
```

Notes:
- `-r` starts the simulation immediately
- `-s` runs Gazebo in server/headless mode

## 4) Start EdgeMCP in Docker

Open terminal 2 and start the single-robot EdgeMCP container:

```bash
cd /path/to/kongnitive-ros2-edgemcp
export ROS_DOMAIN_ID=0
bash ./scripts/start_single_robot_edgemcp.sh
```

This script uses:
- `deploy/single_robot/docker-compose.single-robot.yml`

Inside the container it runs:
- `source /opt/ros/humble/setup.bash`
- `pip3 install -e .`
- `python3 -m kongnitive_ros2_edgemcp.server`

## 5) Stop

Stop the EdgeMCP container:

```bash
cd /path/to/kongnitive-ros2-edgemcp
docker compose -f deploy/single_robot/docker-compose.single-robot.yml down
```

Stop Gazebo with `Ctrl+C` in the Gazebo terminal.

## 6) Validation

- Gazebo and EdgeMCP must use the same `ROS_DOMAIN_ID`
- The examples here use `ROS_DOMAIN_ID=0`
- Single-robot config entry points:
  - `deploy/single_robot/docker-compose.single-robot.yml`
  - `deploy/single_robot/config/server_config.yaml`

To validate the Compose file before starting:

```bash
docker compose -f deploy/single_robot/docker-compose.single-robot.yml config
```

## 7) Troubleshooting

### `Permission denied`

If a script fails with:

```bash
./scripts/start_gazebo_host.sh: Permission denied
```

Run it with `bash`:

```bash
bash ./scripts/start_gazebo_host.sh "..."
bash ./scripts/start_single_robot_edgemcp.sh
```

Or make the scripts executable:

```bash
chmod +x ./scripts/start_gazebo_host.sh ./scripts/start_single_robot_edgemcp.sh
```

### Docker Not Reachable

Check:

```bash
docker info
systemctl status docker --no-pager
groups
```

If Docker is not running:

```bash
sudo systemctl enable --now docker
```

### Gazebo and Container Cannot See the Same ROS Topics

Check that both sides use the same `ROS_DOMAIN_ID`, for example:

```bash
export ROS_DOMAIN_ID=0
```

## 8) Multi-Robot

Once the single-robot path is stable, continue with:

- `deploy/multi_robot/README.md`
- `scripts/start_two_robot_edgemcp.sh`
