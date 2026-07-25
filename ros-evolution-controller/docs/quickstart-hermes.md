# Hermes And MCP Quick Start

This guide connects a local ROS Evolution Controller to Hermes Agent or any
other MCP client that supports stdio servers. The controller owns deployment
state and evidence; the agent only proposes changes and invokes MCP tools.

## 1. Prepare the runtime workspace

Use Ubuntu 24.04 with ROS 2 Jazzy and `colcon`. The runtime workspace must be a
Git worktree because promotion creates a commit and rollback creates a `git
revert` commit.

```bash
source /opt/ros/jazzy/setup.bash
cd /opt/robot/runtime
git init
git add -A
git commit -m 'Initial approved robot runtime'
```

Build the approved runtime once before connecting an agent:

```bash
colcon build --symlink-install
source install/setup.bash
```

## 2. Install the controller

Install it in a dedicated Python environment. Replace `/srv/ros-evolution-controller`
with the location of this repository.

```bash
cd /srv/ros-evolution-controller
python3 -m venv /opt/venvs/ros-evolution
source /opt/venvs/ros-evolution/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[mcp]'
```

The MCP server is started by the MCP client. Its executable needs the Jazzy
environment so it can call `ros2` and `colcon`.

```bash
source /opt/ros/jazzy/setup.bash
/opt/venvs/ros-evolution/bin/ros-evolution-mcp \
  --runtime-workspace /opt/robot/runtime \
  --state-dir /var/lib/ros-evolution
```

Do not start a second copy manually when using stdio MCP: the client owns the
server process and restarts it as needed.

## 3. Connect Hermes Agent

Hermes reads MCP clients from `~/.hermes/config.yaml` under `mcp_servers`.
Add this entry, preserving any existing servers:

```yaml
mcp_servers:
  ros_evolution:
    command: bash
    args:
      - -lc
      - >-
        source /opt/ros/jazzy/setup.bash &&
        exec /opt/venvs/ros-evolution/bin/ros-evolution-mcp
        --runtime-workspace /opt/robot/runtime
        --state-dir /var/lib/ros-evolution
    tools:
      include:
        - inspect_runtime
        - create_candidate
        - run_validation
        - get_evidence
        - submit_for_approval
        - search_skills
```

Restart Hermes, then ask it to call `inspect_runtime`. A successful call returns
a trajectory ID and command evidence for `ros2 node/topic/service/action list`.

For the current Hermes MCP configuration reference, see the
[Hermes MCP documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp).

## 4. Connect another MCP client

Use the equivalent local stdio configuration in the target agent. This is the
common JSON shape used by MCP desktop clients:

```json
{
  "mcpServers": {
    "ros-evolution": {
      "command": "bash",
      "args": [
        "-lc",
        "source /opt/ros/jazzy/setup.bash && exec /opt/venvs/ros-evolution/bin/ros-evolution-mcp --runtime-workspace /opt/robot/runtime --state-dir /var/lib/ros-evolution"
      ]
    }
  }
}
```

For an agent that starts its tools inside an already sourced ROS shell, the
`bash -lc` wrapper can be replaced with the absolute `ros-evolution-mcp` command
and its arguments. Keep the executable path absolute so the agent does not
depend on an interactive shell `PATH`.

## 5. Give the agent a constrained task

Give the connected agent an instruction equivalent to this:

```text
Use the ros_evolution MCP tools as the deployment boundary.
First call inspect_runtime. Create changes only in the worktree returned by
create_candidate. Run validation with baseline metrics and inspect all evidence.
Never call approval, promotion, monitoring, or rollback commands. Do not change
ROS .msg, .srv, or .action files unless the human explicitly approves the
interface change.
```

The controller enforces the promotion and interface-approval checks even if the
agent ignores this instruction.

## 6. First evolution run

1. Ask the agent to call `inspect_runtime` and summarize unavailable nodes,
   graph errors, and command evidence.
2. Ask it to call `create_candidate`; edit only the reported candidate path.
3. Call `run_validation` with measured candidate metrics and the approved
   baseline. On Jazzy the default build pipeline is `colcon build`, `colcon
   test`, then `colcon test-result --verbose`.
4. Review `get_evidence` and `submit_for_approval`. The operator approves from a
   separate terminal, not through the Agent's MCP tool list:

   ```bash
   ros-evolution-controller --runtime-workspace /opt/robot/runtime \
     --state-dir /var/lib/ros-evolution approve <candidate-id> \
     --note 'reviewed build and metrics'
   ```

   Add `--approve-interfaces` only after separately reviewing a Msg/Srv/Action
   change.
5. The operator publishes and monitors from the same trusted terminal:

   ```bash
   ros-evolution-controller --runtime-workspace /opt/robot/runtime \
     --state-dir /var/lib/ros-evolution promote <candidate-id>
   ros-evolution-controller --runtime-workspace /opt/robot/runtime \
     --state-dir /var/lib/ros-evolution monitor <candidate-id> \
     --metrics '{"latency_ms": 14}' --baseline '{"latency_ms": 10}'
   ```

   A metric regression creates a recoverable rollback commit automatically.

## Common failures

- **`ros2: command not found`**: the MCP process was started without sourcing
  `/opt/ros/jazzy/setup.bash`; retain the `bash -lc` wrapper.
- **`Runtime workspace is not a git worktree`**: initialize and commit the
  approved runtime workspace before connecting the controller.
- **`Candidate changes ROS interfaces`**: this is intentional. A human must
  run the operator `approve` command with `--approve-interfaces` after reviewing
  the Msg/Srv/Action change.
- **Promotion fails with a dirty runtime workspace**: restore or commit the
  operator's unrelated runtime changes first. The controller only promotes onto
  a clean approved baseline.
