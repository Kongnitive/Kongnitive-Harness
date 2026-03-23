"""
System monitoring tools for Kongnitive ROS2 EdgeMCP

Provides system status and log retrieval capabilities.
"""

import psutil
import platform
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


async def get_status(node_manager=None) -> Dict[str, Any]:
    """
    Get comprehensive system status.

    Returns CPU, memory, disk, temperature, and ROS node information.

    Args:
        node_manager: Optional NodeManager instance for ROS node info

    Returns:
        Dict with system status metrics
    """
    try:
        # CPU info
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()

        # Memory info
        memory = psutil.virtual_memory()

        # Disk info
        disk = psutil.disk_usage('/')

        # Temperature (if available)
        temperature = None
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                # Try to get CPU temperature
                for name, entries in temps.items():
                    if entries:
                        temperature = entries[0].current
                        break
        except (AttributeError, OSError):
            # sensors_temperatures not available on all platforms
            pass

        # ROS nodes info
        ros_nodes = []
        if node_manager:
            nodes_result = await node_manager.list_nodes()
            if nodes_result["status"] == "success":
                ros_nodes = nodes_result["nodes"]

        # Build status response
        status = {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "system": {
                "platform": platform.system(),
                "platform_release": platform.release(),
                "platform_version": platform.version(),
                "architecture": platform.machine(),
                "hostname": platform.node(),
                "python_version": platform.python_version()
            },
            "cpu": {
                "percent": cpu_percent,
                "count": cpu_count,
                "frequency_mhz": cpu_freq.current if cpu_freq else None
            },
            "memory": {
                "total_mb": memory.total / (1024 * 1024),
                "available_mb": memory.available / (1024 * 1024),
                "used_mb": memory.used / (1024 * 1024),
                "percent": memory.percent
            },
            "disk": {
                "total_gb": disk.total / (1024 * 1024 * 1024),
                "used_gb": disk.used / (1024 * 1024 * 1024),
                "free_gb": disk.free / (1024 * 1024 * 1024),
                "percent": disk.percent
            },
            "temperature_celsius": temperature,
            "ros_nodes": {
                "count": len(ros_nodes),
                "nodes": ros_nodes
            }
        }

        return status

    except Exception as e:
        logger.error(f"Failed to get system status: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


class LogBuffer:
    """
    Simple circular log buffer for storing recent log entries.
    """

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.logs: List[Dict[str, Any]] = []

    def add(self, level: str, message: str, source: str = "system"):
        """Add a log entry."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "source": source,
            "message": message
        }
        self.logs.append(entry)

        # Keep only recent logs
        if len(self.logs) > self.max_size:
            self.logs = self.logs[-self.max_size:]

    def get_logs(
        self,
        filter_text: Optional[str] = None,
        level: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get logs with optional filtering.

        Args:
            filter_text: Filter by message content
            level: Filter by log level
            source: Filter by source
            limit: Maximum number of logs to return

        Returns:
            List of log entries
        """
        filtered = self.logs

        if filter_text:
            filtered = [log for log in filtered if filter_text.lower() in log["message"].lower()]

        if level:
            filtered = [log for log in filtered if log["level"].lower() == level.lower()]

        if source:
            filtered = [log for log in filtered if log["source"].lower() == source.lower()]

        # Return most recent logs
        return filtered[-limit:]


# Global log buffer
_log_buffer = LogBuffer()
_default_log_limit = 100


def configure(buffer_size: Optional[int] = None, default_limit: Optional[int] = None):
    """Configure log buffer and default query limit."""
    global _log_buffer
    global _default_log_limit

    if buffer_size is not None:
        _log_buffer = LogBuffer(max_size=max(1, int(buffer_size)))

    if default_limit is not None:
        _default_log_limit = max(1, int(default_limit))


def get_log_buffer() -> LogBuffer:
    """Get the global log buffer instance."""
    return _log_buffer


async def sys_get_logs(
    filter_text: Optional[str] = None,
    level: Optional[str] = None,
    source: Optional[str] = None,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get system and ROS logs with optional filtering.

    Args:
        filter_text: Filter by message content
        level: Filter by log level (DEBUG, INFO, WARNING, ERROR)
        source: Filter by source (system, node name)
        limit: Maximum number of logs to return

    Returns:
        Dict with log entries
    """
    try:
        effective_limit = _default_log_limit if limit is None else max(1, int(limit))
        logs = _log_buffer.get_logs(
            filter_text=filter_text,
            level=level,
            source=source,
            limit=effective_limit
        )

        return {
            "status": "success",
            "count": len(logs),
            "logs": logs
        }

    except Exception as e:
        logger.error(f"Failed to get logs: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


async def sys_reboot() -> Dict[str, Any]:
    """
    Reboot the system (Phase 4 - deferred).

    Returns:
        Status dict
    """
    return {
        "status": "error",
        "message": "sys_reboot not implemented in Phase 1"
    }
