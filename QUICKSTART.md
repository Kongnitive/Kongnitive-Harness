# Kongnitive ROS2 EdgeMCP Quick Start Guide

## Installation

### 1. Prerequisites

```bash
# Verify ROS2 Humble is installed
ros2 --version

# Verify Python 3.8+
python3 --version
```

### 2. Install Kongnitive ROS2 EdgeMCP

```bash
cd ~/ros2_ws/src
git clone https://github.com/kongnitive/kongnitive-ros2-edgemcp.git
cd kongnitive-ros2-edgemcp

# Install dependencies
pip3 install -r requirements.txt

# Install package
pip3 install -e .
```

## Running the Server

### Start Kongnitive ROS2 EdgeMCP

```bash
# Option 1: Using installed command
kongnitive-ros2-edgemcp

# Option 2: Direct Python execution
python3 -m kongnitive_ros2_edgemcp.server

# Option 3: From source
cd ~/ros2_ws/src/kongnitive-ros2-edgemcp
python3 kongnitive_ros2_edgemcp/server.py
```

The server will start and listen on stdio for MCP commands.

## Testing Hot-Swap

### Manual Test (Python)

```python
import asyncio
from kongnitive_ros2_edgemcp.core.node_manager import NodeManager

async def test_hotswap():
    # Initialize NodeManager
    nm = NodeManager()

    # Read example node
    with open('examples/detector_node.py') as f:
        script = f.read()

    # Push node
    result = await nm.push_node('detector', script)
    print(f"Push result: {result}")

    # List nodes
    nodes = await nm.list_nodes()
    print(f"Running nodes: {nodes}")

    # Modify script (change detect logic)
    modified_script = script.replace(
        'return f"EVEN: {value}"',
        'return f"EVEN_MODIFIED: {value}"'
    )

    # Hot-reload
    result = await nm.push_node('detector', modified_script)
    print(f"Hot-reload result: {result}")

    # Cleanup
    nm.shutdown()

# Run test
asyncio.run(test_hotswap())
```

### Using MCP Client

If you have an MCP client (like Claude Desktop):

```python
# 1. Get system status
result = await get_status()
print(result)

# 2. Push detector node
with open('examples/detector_node.py') as f:
    script = f.read()

result = await ros_push_node('detector', script)
print(result)

# 3. Verify it's running
result = await ros_list_nodes()
print(result)

# 4. Check logs
result = await sys_get_logs(filter='detector', limit=10)
print(result)

# 5. Hot-reload with modified script
# Edit the detect() method
modified_script = script.replace(
    'if value % 2 == 0:',
    'if value % 3 == 0:'
)

result = await ros_push_node('detector', modified_script)
print(result)
# Node reloads in <100ms!
```

## Verifying Installation

### Run Tests

```bash
cd ~/ros2_ws/src/kongnitive-ros2-edgemcp
pytest tests/ -v
```

### Check ROS2 Integration

```bash
# In terminal 1: Start Kongnitive ROS2 EdgeMCP
kongnitive-ros2-edgemcp

# In terminal 2: Check ROS2 nodes
ros2 node list
# Should show nodes managed by Kongnitive ROS2 EdgeMCP

# Check topics
ros2 topic list
```

## Example Workflow

### 1. Start with Detector Node

```bash
# Terminal 1: Start server
kongnitive-ros2-edgemcp
```

```python
# Terminal 2: Push detector
from kongnitive_ros2_edgemcp.tools import node_tools
from kongnitive_ros2_edgemcp.core.node_manager import NodeManager

nm = NodeManager()

with open('examples/detector_node.py') as f:
    script = f.read()

result = await node_tools.ros_push_node(nm, 'detector', script)
```

### 2. Monitor Logs

```python
from kongnitive_ros2_edgemcp.tools import system_tools

# Get recent logs
logs = await system_tools.sys_get_logs(limit=20)
for log in logs['logs']:
    print(f"[{log['level']}] {log['message']}")

# Filter for detector
logs = await system_tools.sys_get_logs(filter='detector')
```

### 3. Modify and Hot-Reload

```python
# Modify detect() logic
modified_script = """
import rclpy
from rclpy.node import Node

class DetectorNode(Node):
    def __init__(self):
        super().__init__('detector')
        self.timer = self.create_timer(1.0, self.timer_callback)
        self.counter = 0
        self.get_logger().info('DetectorNode started - MODIFIED VERSION')

    def timer_callback(self):
        self.counter += 1
        result = self.detect(self.counter)
        self.get_logger().info(f'Detection: {result}')

    def detect(self, value):
        # NEW LOGIC: Detect multiples of 3
        if value % 3 == 0:
            return f"MULTIPLE_OF_3: {value}"
        else:
            return f"NOT_MULTIPLE_OF_3: {value}"

def create_node():
    return DetectorNode()
"""

# Hot-reload
result = await node_tools.ros_push_node(nm, 'detector', modified_script)
print(result)
# Switchover happens in <100ms!
```

### 4. Verify Changes

```python
# Check logs to see new behavior
logs = await system_tools.sys_get_logs(filter='MULTIPLE_OF_3', limit=5)
for log in logs['logs']:
    print(log['message'])
```

## Troubleshooting

### Server won't start

```bash
# Check ROS2 is sourced
source /opt/ros/humble/setup.bash

# Check Python path
which python3
python3 -c "import rclpy; print('ROS2 OK')"

# Check dependencies
pip3 list | grep -E "fastmcp|rclpy|psutil"
```

### Node won't load

```python
# Check script syntax
python3 -m py_compile your_node.py

# Verify create_node() exists
grep "def create_node" your_node.py

# Check logs for errors
logs = await sys_get_logs(level='ERROR')
```

### Hot-swap fails

```python
# Check node manager status
status = await get_status()
print(status['ros_nodes'])

# Try stopping and restarting
await ros_stop_node('detector')
await ros_start_node('detector')
```

## Next Steps

1. **Explore examples** - See `examples/` for more node templates
2. **Read system prompt** - `config/system_prompt.txt` has AI instructions
3. **Monitor performance** - Use `get_status()` to track resources
4. **Build custom nodes** - Follow the template pattern
5. **Integrate with AI** - Connect MCP client for autonomous iteration

## Configuration

Edit `config/server_config.yaml` to customize:

```yaml
nodes:
  script_dir: "~/.kongnitive_ros2_edgemcp/nodes"  # Where scripts are stored
  max_nodes: 10                                   # Max concurrent nodes

logging:
  buffer_size: 1000   # Log buffer size
  default_limit: 100  # Default log query limit
```

## Support

- GitHub Issues: [Your Issues URL]
- Documentation: See README.md
- Examples: See examples/ directory
