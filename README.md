# Kongnitive ROS2 EdgeMCP

**AI-Driven Hot-Swapping of ROS2 Nodes on Jetson**

Kongnitive ROS2 EdgeMCP is a FastMCP server that enables AI to push, reload, and manage ROS2 nodes dynamically without system restart. Built for Jetson platforms, it extends the EdgeMCP concept (proven on ESP32 with Lua) to ROS2 with Python.

## Problem Solved

Traditional ROS2 development requires recompilation and redeployment for every change (5-20 min/iteration). Remote debugging and fixing production robots is difficult. Kongnitive ROS2 EdgeMCP enables:

- **Hot-swap nodes in <100ms** - AI pushes Python scripts that reload instantly
- **Autonomous iteration** - AI reads logs, analyzes issues, pushes fixes, verifies
- **Remote robot management** - Fix production robots without physical access
- **Rapid prototyping** - Test ideas in seconds, not minutes

## Architecture

```
┌─────────────────────────────────────────────┐
│           AI (Claude via MCP)               │
└─────────────────┬───────────────────────────┘
                  │ MCP Tools
┌─────────────────▼───────────────────────────┐
│         FastMCP Server (stdio)              │
│  ┌──────────────────────────────────────┐   │
│  │  9 Core Tools (Phase 1)              │   │
│  │  - get_status                        │   │
│  │  - get_system_prompt                 │   │
│  │  - sys_get_logs                      │   │
│  │  - ros_push_node (hot-swap!)         │   │
│  │  - ros_list_nodes                    │   │
│  └──────────────────────────────────────┘   │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│          NodeManager                        │
│  - Dynamic Python import (importlib)        │
│  - MultiThreadedExecutor                    │
│  - Script storage & lifecycle               │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│      Hot-Swappable ROS2 Nodes               │
│  - Detector, Planner, Controller, etc.      │
│  - <100ms reload time                       │
│  - Zero-downtime switchover                 │
└─────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Ubuntu 20.04/22.04
- ROS2 Humble (LTS)
- Python 3.8+
- JetPack 5.0+ (for Jetson)

### Installation

```bash
# Clone repository
cd ~/ros2_ws/src
git clone https://github.com/kongnitive/kongnitive-ros2-edgemcp.git
cd kongnitive-ros2-edgemcp

# Install dependencies
pip install -r requirements.txt

# Install package
pip install -e .
```

### Running the Server

```bash
# Start Kongnitive ROS2 EdgeMCP server
kongnitive-ros2-edgemcp

# Or run directly
python -m kongnitive_ros2_edgemcp.server
```

### Testing Hot-Swap

```python
# In another terminal, use MCP client to push a node
# (Example using Claude Desktop or other MCP client)

# 1. Get system status
await get_status()

# 2. Push detector node
script = open('examples/detector_node.py').read()
await ros_push_node('detector', script)

# 3. Verify it's running
await ros_list_nodes()

# 4. Check logs
await sys_get_logs(filter='detector')

# 5. Hot-reload with modified script
# Edit detect() method in script
await ros_push_node('detector', modified_script)
# Node reloads in <100ms!
```

## Node Script Template

Every AI-pushed node must follow this pattern:

```python
import rclpy
from rclpy.node import Node

class MyNode(Node):
    def __init__(self):
        super().__init__('my_node')
        # Your initialization here

def create_node():
    """Required factory function"""
    return MyNode()
```

See `examples/` for complete examples.

## MCP Tools (Phase 1)

### System Tools

- **get_status()** - CPU, memory, disk, temperature, ROS nodes
- **get_system_prompt()** - AI instructions for this project
- **sys_get_logs(filter, level, source, limit)** - Filtered log retrieval

### Node Management

- **ros_push_node(node_name, script)** - Hot-swap a node
- **ros_list_nodes()** - List running nodes
- **ros_get_node(node_name)** - Get node source code
- **ros_start_node(node_name)** - Start saved node
- **ros_stop_node(node_name)** - Stop running node
- **ros_restart_node(node_name)** - Restart node

## AI Workflow

1. **Understand** - `get_status()` shows system state
2. **Diagnose** - `sys_get_logs()` reveals issues
3. **Fix** - `ros_push_node()` deploys updated code
4. **Verify** - Check `ros_list_nodes()` and logs
5. **Iterate** - Repeat until working

## Hot-Swap Mechanism

```python
# NodeManager hot-swap process:
1. Save script to ~/.kongnitive_ros2_edgemcp/nodes/
2. Unload old node (if exists)
3. Dynamic import via importlib
4. Create node instance
5. Add to MultiThreadedExecutor
6. ROS2 topics auto-reconnect
# Total time: <100ms
```

## Project Structure

```
kongnitive-ros2-edgemcp/
├── kongnitive_ros2_edgemcp/
│   ├── server.py              # FastMCP server entry point
│   ├── core/
│   │   └── node_manager.py    # Hot-swap engine
│   ├── tools/
│   │   ├── system_tools.py    # System monitoring
│   │   └── node_tools.py      # Node management
│   └── ...
├── examples/
│   ├── detector_node.py       # Simple example
│   └── planner_node.py        # Advanced example
├── config/
│   ├── server_config.yaml
│   └── system_prompt.txt
├── requirements.txt
├── setup.py
└── README.md
```

## Development Phases

### ✅ Phase 1 (Current) - MVP
- Core hot-swap capability
- 5 essential MCP tools
- System monitoring
- Log management
- Example nodes

### 🔄 Phase 2 (Next) - ROS Communication
- Topic tools (list, echo, pub, info)
- Service tools (list, call)
- Action tools (list, send_goal)
- Enhanced node management

### 📋 Phase 3 (Later) - GPU Integration
- TensorRT model management
- Model hot-swapping
- Inference tools
- Performance profiling

### 📋 Phase 4 (Future) - Multi-Device
- mDNS device discovery
- Remote node deployment
- Fleet management

## Performance Targets

- Node hot-swap time: <100ms ✅
- Tool response time: <500ms
- Memory overhead: <200MB
- CPU usage (idle): <5%
- Support 5+ concurrent nodes

## Testing

```bash
# Run tests
pytest tests/

# Test hot-swap manually
python examples/detector_node.py
```

## Configuration

Edit `config/server_config.yaml`:

```yaml
nodes:
  script_dir: "~/.kongnitive_ros2_edgemcp/nodes"
  max_nodes: 10

logging:
  buffer_size: 1000
  default_limit: 100
```

Config loading priority:
1. `KONGNITIVE_CONFIG_DIR` (if set)
2. `config/` in repository root
3. packaged default config (`kongnitive_ros2_edgemcp/config/`)

## Troubleshooting

### Node won't load
- Check script has `create_node()` function
- Verify imports are correct
- Check for syntax errors
- Review logs: `sys_get_logs(filter='error')`

### Hot-swap fails
- Ensure ROS2 is initialized
- Check script directory permissions
- Verify node name is unique

### Performance issues
- Monitor with `get_status()`
- Check CPU/memory usage
- Reduce number of concurrent nodes

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request

## License

MIT License

## Acknowledgments

- Built on FastMCP framework
- Inspired by EdgeMCP (ESP32/Lua)
- Powered by ROS2 Humble

## Contact

- GitHub: https://github.com/kongnitive/kongnitive-ros2-edgemcp
- Issues: https://github.com/kongnitive/kongnitive-ros2-edgemcp/issues

---

**Status**: Phase 1 MVP Complete ✅

**Next**: Phase 2 - ROS Communication Tools
