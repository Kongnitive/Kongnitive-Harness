param(
    [int]$RosDomainId = 0,
    [string]$RmwImplementation = "rmw_fastrtps_cpp"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:ROS_DOMAIN_ID = "$RosDomainId"
$env:RMW_IMPLEMENTATION = $RmwImplementation

Write-Host "[edgemcp-1r] starting robot_a with ROS_DOMAIN_ID=$($env:ROS_DOMAIN_ID)"
docker compose -f deploy/single_robot/docker-compose.single-robot.yml up --build edgemcp_robot_a

