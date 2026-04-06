# Vector OS Nano — Architecture Guide

## Repository Structure

```
vector_os_nano/
├── core/              Agent pipeline, SkillFlow protocol, Executor, WorldModel
│   ├── agent.py       Multi-stage pipeline: MATCH → CLASSIFY → PLAN → EXECUTE → ADAPT → SUMMARIZE
│   ├── skill.py       @skill decorator, SkillRegistry with alias matching
│   ├── executor.py    Deterministic task executor (topological sort, pre/postconditions)
│   ├── world_model.py Object + robot state tracking
│   ├── types.py       Frozen dataclasses: TaskPlan, TaskStep, ExecutionResult, SkillResult
│   └── config.py      YAML config loader with deep-merge
│
├── llm/               LLM providers + prompt engineering
│   ├── claude.py      ClaudeProvider: plan, classify, chat, summarize
│   ├── prompts.py     System prompts for each pipeline stage
│   └── base.py        LLMProvider protocol
│
├── perception/        Camera + VLM + tracking
│   ├── realsense.py   RealSense D405 driver
│   ├── vlm.py         Moondream VLM detector
│   ├── tracker.py     EdgeTAM object tracker
│   ├── pipeline.py    Unified detect → track → 3D pipeline
│   └── calibration.py Camera-to-arm coordinate transform
│
├── hardware/
│   ├── so101/         SO-101 arm driver (Feetech serial, Pinocchio IK)
│   ├── sim/           MuJoCo simulation (arm, gripper, perception, MJCF scene)
│   ├── arm.py         ArmProtocol (abstract interface)
│   └── gripper.py     GripperProtocol (abstract interface)
│
├── skills/            Built-in skills (all use @skill decorator)
│   ├── pick.py        PickSkill — grasp objects (hold or drop mode)
│   ├── place.py       PlaceSkill — place at named locations
│   ├── home.py        HomeSkill — return to home position
│   ├── scan.py        ScanSkill — move to observation pose
│   ├── detect.py      DetectSkill — VLM/sim object detection
│   └── gripper.py     GripperOpenSkill, GripperCloseSkill
│
├── cli/               Interactive CLI (Rich + prompt_toolkit)
│   ├── simple.py      AI chat, auto-complete, status bar, animated banner
│   ├── dashboard.py   Textual TUI dashboard
│   └── logo_braille.txt
│
├── web/               Localhost web dashboard (FastAPI + WebSocket)
└── ros2/              Optional ROS2 nodes (5 nodes)

config/
├── default.yaml       SDK defaults
├── user.yaml          User overrides (gitignored)
└── agent.md           V's system prompt
```

## SkillFlow — Declarative Skill Routing

All command routing is declarative via `@skill` decorator. See docs/skill-protocol.md.

```python
@skill(aliases=["grab", "抓"], auto_steps=["scan", "detect", "pick"])
class PickSkill: ...

@skill(aliases=["close", "夹紧"], direct=True)
class GripperCloseSkill: ...
```

## Agent Pipeline

```
User Input → registry.match(aliases)
                |
        ┌───────┴──────┐
    Matched          No match
        |                |
   direct? ──Yes→ Execute (zero LLM)
        |
   auto_steps? ──Yes→ Chain execute (zero LLM)
        |
   complex? ──Yes→ LLM PLAN → EXECUTE → SUMMARIZE
        |
        └─→ LLM CLASSIFY (chat/task/query) → route
```

Simple commands: zero LLM calls.
Common patterns: zero LLM calls.
Complex tasks: LLM plans + executes + summarizes.
