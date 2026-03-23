#!/usr/bin/env python3
"""
Simple MCP Client for Testing Kongnitive ROS2 EdgeMCP

This script demonstrates how to interact with Kongnitive ROS2 EdgeMCP server
using the MCP protocol over stdio.

Usage:
    python mcp_client_example.py
"""

import asyncio
import json
import sys
from pathlib import Path


class SimpleMCPClient:
    """
    Minimal MCP client for testing.

    Communicates with Kongnitive ROS2 EdgeMCP server via stdio.
    """

    def __init__(self):
        self.request_id = 0

    def _next_id(self):
        """Get next request ID."""
        self.request_id += 1
        return self.request_id

    async def call_tool(self, tool_name: str, arguments: dict = None):
        """
        Call an MCP tool.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments (optional)

        Returns:
            Tool result
        """
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments or {}
            }
        }

        # Send request
        print(f"\n→ Calling {tool_name}...")
        print(json.dumps(request, indent=2))

        # In a real implementation, this would send to server via stdio
        # For this example, we'll just show the request format
        print("\n(This is a demonstration - actual server communication not implemented)")

        return None


async def demo_workflow():
    """
    Demonstrate typical AI workflow with Kongnitive ROS2 EdgeMCP.
    """
    print("=" * 60)
    print("Kongnitive ROS2 EdgeMCP MCP Client Demo")
    print("=" * 60)

    client = SimpleMCPClient()

    # 1. Get system status
    print("\n[Step 1] Get system status")
    await client.call_tool("get_status")

    # 2. Get system prompt
    print("\n[Step 2] Get AI instructions")
    await client.call_tool("get_system_prompt")

    # 3. Push detector node
    print("\n[Step 3] Push detector node")
    detector_path = Path(__file__).parent.parent / "examples" / "detector_node.py"
    if detector_path.exists():
        script = detector_path.read_text()
        await client.call_tool("ros_push_node", {
            "node_name": "detector",
            "script": script
        })
    else:
        print("(Detector script not found - using placeholder)")
        await client.call_tool("ros_push_node", {
            "node_name": "detector",
            "script": "# Placeholder script"
        })

    # 4. List nodes
    print("\n[Step 4] List running nodes")
    await client.call_tool("ros_list_nodes")

    # 5. Get logs
    print("\n[Step 5] Get recent logs")
    await client.call_tool("sys_get_logs", {
        "filter": "detector",
        "limit": 10
    })

    # 6. Hot-reload node
    print("\n[Step 6] Hot-reload with modified script")
    await client.call_tool("ros_push_node", {
        "node_name": "detector",
        "script": "# Modified script"
    })

    # 7. Verify changes
    print("\n[Step 7] Verify changes in logs")
    await client.call_tool("sys_get_logs", {
        "filter": "detector",
        "limit": 5
    })

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)
    print("\nTo actually run these commands:")
    print("1. Start Kongnitive ROS2 EdgeMCP server: kongnitive-ros2-edgemcp")
    print("2. Connect with a real MCP client (e.g., Claude Desktop)")
    print("3. Use the tools shown above")


def main():
    """Main entry point."""
    try:
        asyncio.run(demo_workflow())
    except KeyboardInterrupt:
        print("\n\nDemo interrupted")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
