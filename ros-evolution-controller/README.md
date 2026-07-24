# ROS Evolution Controller

`ROS Evolution Controller` is a deterministic control plane for evolving a ROS 2
workspace safely. It is not a ROS node and it does not contain an LLM. Hermes or
another coding agent calls it through MCP to create isolated candidate worktrees,
run evidence-producing validation, request human approval, promote an approved
change, and roll it back.

## Design

```text
Agent / Hermes -- MCP --> Evolution Controller -- subprocesses --> ROS workspace
                                  |
                                  +--> SQLite evidence and skill store
                                  +--> isolated git worktrees
```

The production workspace is read-only until a candidate is approved. Interface
files (`*.msg`, `*.srv`, `*.action`) need explicit interface approval even after
normal candidate approval.

## ROS 2 Jazzy usage

On Ubuntu 24.04 with ROS 2 Jazzy and `colcon` installed:

```bash
cd ros-evolution-controller
python -m pip install -e '.[mcp,dev]'
ros-evolution-mcp --runtime-workspace /opt/robot/runtime --state-dir /var/lib/ros-evolution
```

The default validation pipeline executes, in the candidate workspace:

```bash
colcon build --symlink-install
colcon test
colcon test-result --verbose
```

`inspect_runtime` additionally invokes the ROS CLI graph commands for nodes,
topics, services, and actions. The controller records command output and errors
as evidence instead of assuming ROS is available.

## MCP workflow

1. `inspect_runtime` creates an observation trajectory.
2. The agent calls `create_candidate` and edits only the returned worktree.
3. `run_validation` stores build/test evidence and compares supplied metrics to
   a baseline.
4. `submit_for_approval` moves a passing candidate to the approval queue.
5. A human calls `approve_candidate`; interface changes require
   `approve_interfaces=true`.
6. `promote` applies and commits the approved patch to the runtime workspace.
7. `rollback` uses `git revert` to create a recoverable rollback commit.

Only promoted candidates may be saved as reusable skills.
