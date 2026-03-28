param(
    [Parameter(Mandatory = $true)]
    [string]$LaunchCommand,
    [int]$RosDomainId = 0,
    [string]$WslDistro = "Ubuntu-22.04"
)

$ErrorActionPreference = "Stop"

$env:ROS_DOMAIN_ID = "$RosDomainId"

Write-Host "[gazebo-host] ROS_DOMAIN_ID=$($env:ROS_DOMAIN_ID)"
Write-Host "[gazebo-host] launching: $LaunchCommand"

$bashCmd = @"
source /opt/ros/humble/setup.bash
if [ -f ~/ros2_ws/install/setup.bash ]; then
  source ~/ros2_ws/install/setup.bash
fi
export ROS_DOMAIN_ID=$($env:ROS_DOMAIN_ID)
$LaunchCommand
"@

if (Get-Command wsl -ErrorAction SilentlyContinue) {
    $wslList = wsl -l -q
    if (-not ($wslList -contains $WslDistro)) {
        throw "WSL distro '$WslDistro' not found. Available distros: $($wslList -join ', ')"
    }
    Write-Host "[gazebo-host] using WSL distro: $WslDistro"
    wsl -d $WslDistro bash -lc $bashCmd
} elseif (Get-Command bash -ErrorAction SilentlyContinue) {
    bash -lc $bashCmd
} else {
    throw "Neither 'bash' nor 'wsl' is available. Install Git Bash or WSL first."
}
