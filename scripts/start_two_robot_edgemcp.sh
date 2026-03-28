#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}"

echo "[edgemcp-2r] starting robot_a + robot_b with ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"
docker compose -f deploy/multi_robot/docker-compose.two-robots.yml up --build

