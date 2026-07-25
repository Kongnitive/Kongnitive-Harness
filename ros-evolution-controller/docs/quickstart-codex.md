# Codex Quick Start

This guide connects Codex to the local ROS Evolution Controller over stdio MCP.
Codex can inspect the ROS runtime, create an isolated candidate worktree, and
run validation. It cannot approve, promote, monitor, or roll back releases;
those remain operator actions in a trusted terminal.

## 1. Prepare ROS and install the controller

Follow steps 1 and 2 in [Hermes and MCP Quick Start](quickstart-hermes.md) on
Ubuntu 24.04 with ROS 2 Jazzy. You need:

- a clean, committed Git runtime workspace at `/opt/robot/runtime`;
- the controller installed at `/opt/venvs/ros-evolution`; and
- `/opt/ros/jazzy/setup.bash` available to the Codex host process.

## 2. Add the Codex MCP server

Prefer project-scoped configuration so this server is available only for the
robot workspace. Create or extend the trusted project's `.codex/config.toml`:

```toml
[mcp_servers.ros_evolution]
command = "bash"
args = [
  "-lc",
  "source /opt/ros/jazzy/setup.bash && exec /opt/venvs/ros-evolution/bin/ros-evolution-mcp --runtime-workspace /opt/robot/runtime --state-dir /var/lib/ros-evolution",
]
tool_timeout_sec = 600
enabled_tools = [
  "inspect_runtime",
  "create_candidate",
  "run_validation",
  "get_evidence",
  "submit_for_approval",
  "search_skills",
]
```

Codex only loads project `.codex/config.toml` after the project is trusted. For
a personal development machine where this controller should be available to all
projects, add the same table to `~/.codex/config.toml` instead.

Restart Codex or open a new task in the configured project. The controller is a
local stdio child process; do not start a separate long-running
`ros-evolution-mcp` process for this integration.

## 3. Give Codex the operating contract

Use this task instruction when delegating an evolution run:

```text
Use only the ros_evolution MCP tools for ROS runtime observation and candidate
validation. Begin with inspect_runtime. Create and edit code only in the
worktree returned by create_candidate, never in /opt/robot/runtime. Run
validation against the supplied baseline metrics and inspect all evidence.
Submit a passing candidate for human review; do not attempt approval, promotion,
monitoring, or rollback. Treat every .msg, .srv, and .action change as requiring
separate human interface approval.
```

The MCP allow-list provides a second enforcement layer: Codex is not given the
approval or production-release tools in the first place.

## 4. First run

1. Ask Codex to call `inspect_runtime` and summarize graph evidence.
2. Ask it to call `create_candidate`; make all package/node edits in the
   returned worktree only.
3. Ask it to run `run_validation` with the candidate metrics and current
   approved baseline. The default Jazzy pipeline runs `colcon build`, `colcon
   test`, and `colcon test-result --verbose`.
4. Review `get_evidence` and `submit_for_approval` yourself.
5. Use the trusted operator CLI from the Hermes quick start to run `approve`,
   `promote`, and `monitor`.

## Troubleshooting

- **MCP server is not listed in Codex**: verify the TOML table name,
  `command`, and absolute paths; restart Codex after changing configuration.
- **Project config is ignored**: trust the project, or place the configuration
  in `~/.codex/config.toml` for a user-level setup.
- **`ros2` or `colcon` is unavailable**: retain the `bash -lc` wrapper that
  sources `/opt/ros/jazzy/setup.bash` before starting the MCP server.
- **Tool call times out during a build**: raise `tool_timeout_sec` only after
  confirming the build is expected to take longer; do not disable the tool
  allow-list to work around a timeout.

For the current Codex MCP configuration reference, see the
[Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp).
