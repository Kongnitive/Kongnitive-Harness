#!/usr/bin/env python3
"""
Verification script for Kongnitive ROS2 EdgeMCP Phase 1 implementation.

Checks that all required files exist and have correct structure.
"""

from pathlib import Path
import sys


def check_file_exists(path: Path, description: str) -> bool:
    """Check if a file exists."""
    if path.exists():
        print(f"[OK] {description}: {path.name}")
        return True
    else:
        print(f"[MISSING] {description}: {path}")
        return False


def check_directory_exists(path: Path, description: str) -> bool:
    """Check if a directory exists."""
    if path.exists() and path.is_dir():
        print(f"[OK] {description}: {path.name}/")
        return True
    else:
        print(f"[MISSING] {description}: {path}")
        return False


def verify_implementation():
    """Verify Phase 1 implementation is complete."""
    print("=" * 60)
    print("Kongnitive ROS2 EdgeMCP Phase 1 Verification")
    print("=" * 60)

    root = Path(__file__).parent  # Script is in project root
    all_ok = True

    # Check directories
    print("\n[Directories]")
    all_ok &= check_directory_exists(root / "kongnitive_ros2_edgemcp", "Main package")
    all_ok &= check_directory_exists(root / "kongnitive_ros2_edgemcp" / "core", "Core module")
    all_ok &= check_directory_exists(root / "kongnitive_ros2_edgemcp" / "tools", "Tools module")
    all_ok &= check_directory_exists(root / "examples", "Examples")
    all_ok &= check_directory_exists(root / "config", "Configuration")
    all_ok &= check_directory_exists(root / "tests", "Tests")

    # Check core files
    print("\n[Core Implementation]")
    all_ok &= check_file_exists(root / "kongnitive_ros2_edgemcp" / "server.py", "FastMCP server")
    all_ok &= check_file_exists(root / "kongnitive_ros2_edgemcp" / "core" / "node_manager.py", "NodeManager")
    all_ok &= check_file_exists(root / "kongnitive_ros2_edgemcp" / "tools" / "system_tools.py", "System tools")
    all_ok &= check_file_exists(root / "kongnitive_ros2_edgemcp" / "tools" / "node_tools.py", "Node tools")

    # Check __init__ files
    print("\n[Package Structure]")
    all_ok &= check_file_exists(root / "kongnitive_ros2_edgemcp" / "__init__.py", "Package init")
    all_ok &= check_file_exists(root / "kongnitive_ros2_edgemcp" / "core" / "__init__.py", "Core init")
    all_ok &= check_file_exists(root / "kongnitive_ros2_edgemcp" / "tools" / "__init__.py", "Tools init")
    all_ok &= check_file_exists(root / "tests" / "__init__.py", "Tests init")

    # Check examples
    print("\n[Examples]")
    all_ok &= check_file_exists(root / "examples" / "detector_node.py", "Detector node")
    all_ok &= check_file_exists(root / "examples" / "planner_node.py", "Planner node")
    all_ok &= check_file_exists(root / "examples" / "mcp_client_example.py", "MCP client demo")

    # Check configuration
    print("\n[Configuration]")
    all_ok &= check_file_exists(root / "config" / "server_config.yaml", "Server config")
    all_ok &= check_file_exists(root / "config" / "system_prompt.txt", "System prompt")

    # Check tests
    print("\n[Tests]")
    all_ok &= check_file_exists(root / "tests" / "test_phase1.py", "Unit tests")
    all_ok &= check_file_exists(root / "tests" / "test_integration.py", "Integration test")

    # Check documentation
    print("\n[Documentation]")
    all_ok &= check_file_exists(root / "README.md", "Main README")
    all_ok &= check_file_exists(root / "QUICKSTART.md", "Quick start guide")
    all_ok &= check_file_exists(root / "IMPLEMENTATION_SUMMARY.md", "Implementation summary")

    # Check project files
    print("\n[Project Files]")
    all_ok &= check_file_exists(root / "requirements.txt", "Requirements")
    all_ok &= check_file_exists(root / "setup.py", "Setup script")
    all_ok &= check_file_exists(root / ".gitignore", "Git ignore")
    all_ok &= check_file_exists(root / "LICENSE", "License")

    # Verify key content
    print("\n[Content Verification]")

    # Check NodeManager has hot-swap method
    node_manager_path = root / "kongnitive_ros2_edgemcp" / "core" / "node_manager.py"
    if node_manager_path.exists():
        content = node_manager_path.read_text(encoding='utf-8')
        if "async def push_node" in content:
            print("[OK] NodeManager has push_node method")
        else:
            print("[MISSING] NodeManager missing push_node method")
            all_ok = False

        if "importlib" in content:
            print("[OK] NodeManager uses importlib")
        else:
            print("[MISSING] NodeManager missing importlib import")
            all_ok = False

    # Check server has MCP tools
    server_path = root / "kongnitive_ros2_edgemcp" / "server.py"
    if server_path.exists():
        content = server_path.read_text(encoding='utf-8')
        tools = [
            "get_status",
            "get_system_prompt",
            "sys_get_logs",
            "ros_push_node",
            "ros_list_nodes",
            "ros_get_node",
            "ros_start_node",
            "ros_stop_node",
            "ros_restart_node"
        ]
        for tool in tools:
            if f"async def {tool}" in content:
                print(f"[OK] Tool registered: {tool}")
            else:
                print(f"[MISSING] Tool missing: {tool}")
                all_ok = False

    # Check examples have create_node
    for example in ["detector_node.py", "planner_node.py"]:
        example_path = root / "examples" / example
        if example_path.exists():
            content = example_path.read_text(encoding='utf-8')
            if "def create_node()" in content:
                print(f"[OK] {example} has create_node()")
            else:
                print(f"[MISSING] {example} missing create_node()")
                all_ok = False

    # Final result
    print("\n" + "=" * 60)
    if all_ok:
        print("[SUCCESS] VERIFICATION PASSED")
        print("=" * 60)
        print("\nPhase 1 implementation is complete!")
        print("\nNext steps:")
        print("1. Install dependencies: pip install -r requirements.txt")
        print("2. Install package: pip install -e .")
        print("3. Run tests: pytest tests/ -v")
        print("4. Start server: kongnitive-ros2-edgemcp")
        return 0
    else:
        print("[FAILED] VERIFICATION FAILED")
        print("=" * 60)
        print("\nSome files are missing or incomplete.")
        print("Please review the errors above.")
        return 1


def main():
    """Main entry point."""
    try:
        sys.exit(verify_implementation())
    except Exception as e:
        print(f"\n[ERROR] Verification error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
