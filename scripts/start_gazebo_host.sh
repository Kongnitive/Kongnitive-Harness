#!/usr/bin/env bash
set -eo pipefail

if [[ $# -eq 0 && -z "${GAZEBO_LAUNCH_CMD:-}" ]]; then
  echo "Usage: $0 '<your gazebo launch command>'"
  echo "Example:"
  echo "  $0 'ros2 launch my_pick_place_sim tabletop.launch.py'"
  echo "Or set GAZEBO_LAUNCH_CMD and run without args."
  exit 1
fi

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
LAUNCH_CMD="${*:-${GAZEBO_LAUNCH_CMD}}"
export AMENT_TRACE_SETUP_FILES="${AMENT_TRACE_SETUP_FILES:-}"

source /opt/ros/humble/setup.bash

echo "[gazebo-host] ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"
echo "[gazebo-host] launching: ${LAUNCH_CMD}"
exec bash -lc "source /opt/ros/humble/setup.bash && export ROS_DOMAIN_ID=${ROS_DOMAIN_ID} && ${LAUNCH_CMD}"
