param(
    [int]$RosDomainId = 0,
    [string]$RmwImplementation = "rmw_fastrtps_cpp"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:ROS_DOMAIN_ID = "$RosDomainId"
$env:RMW_IMPLEMENTATION = $RmwImplementation

Write-Host "[edgemcp-2r] starting robot_a + robot_b with ROS_DOMAIN_ID=$($env:ROS_DOMAIN_ID)"
docker compose -f deploy/multi_robot/docker-compose.two-robots.yml up --build

