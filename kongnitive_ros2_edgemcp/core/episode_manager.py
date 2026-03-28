"""
EpisodeManager - reproducible pick-and-place simulation loop for AI iteration.

This module provides a deterministic, ROS-friendly task loop abstraction:
- run_episode(seed, profile)
- get_metrics(run_id)
- get_failure_trace(run_id)

The runtime is intentionally lightweight. It does not replace Gazebo/MoveIt2;
it provides a stable interface that can be backed by real simulators later.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import random
import time
import uuid
from typing import Any, Dict, List, Optional


class FailureCode(str, Enum):
    """Standardized failure codes for episode outcomes."""

    NONE = "none"
    PERCEPTION_FAILED = "perception_failed"
    GRASP_FAILED = "grasp_failed"
    PLACE_FAILED = "place_failed"
    TIMEOUT = "timeout"
    COLLISION = "collision"
    TORQUE_LIMIT = "torque_limit"


@dataclass
class RandomizationProfile:
    """Scenario perturbation profile for reproducible episode runs."""

    object_pose_jitter: float = 0.10
    camera_pose_jitter: float = 0.05
    lighting_jitter: float = 0.20
    friction_jitter: float = 0.15
    sensor_noise: float = 0.05
    torque_noise: float = 0.05
    obstacle_density: float = 0.10
    timeout_seconds: float = 5.0
    enable_camera_jitter: bool = True
    enable_dynamics_jitter: bool = True
    enable_sensor_noise: bool = True

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "RandomizationProfile":
        if not data:
            return cls()
        values = asdict(cls())
        for key in values.keys():
            if key in data:
                values[key] = data[key]
        return cls(**values)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EpisodeResult:
    """Unified episode result record returned by run_episode."""

    run_id: str
    seed: int
    success: bool
    failure_code: str
    duration_ms: int
    metrics: Dict[str, Any] = field(default_factory=dict)
    profile: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EpisodeManager:
    """
    Deterministic episode loop for hardcoded baseline strategy.

    The baseline intentionally has failure modes so AI-driven patching can
    iteratively improve task logic via EdgeMCP hot-swaps.
    """

    def __init__(self):
        self._results: Dict[str, EpisodeResult] = {}
        self._failure_traces: Dict[str, Dict[str, Any]] = {}

    async def run_episode(
        self,
        seed: int,
        profile: Optional[Dict[str, Any]] = None,
        strategy: str = "hardcoded_v1",
    ) -> Dict[str, Any]:
        run_id = str(uuid.uuid4())
        rng = random.Random(seed)
        cfg = RandomizationProfile.from_dict(profile)
        started = time.perf_counter()

        if strategy != "hardcoded_v1":
            result = EpisodeResult(
                run_id=run_id,
                seed=seed,
                success=False,
                failure_code=FailureCode.PERCEPTION_FAILED.value,
                duration_ms=1,
                metrics={
                    "strategy": strategy,
                    "error": "unsupported_strategy",
                    "collision_count": 0,
                    "torque_limit_exceeded_count": 0,
                },
                profile=cfg.to_dict(),
            )
            self._results[run_id] = result
            self._failure_traces[run_id] = {
                "run_id": run_id,
                "seed": seed,
                "strategy": strategy,
                "stage": "init",
                "reason": "unsupported_strategy",
                "trace": [],
            }
            return {"status": "success", "result": result.to_dict()}

        thresholds = self._build_thresholds(cfg)
        trace: List[Dict[str, Any]] = []

        collision_count = 0
        torque_exceeded_count = 0
        failure = FailureCode.NONE

        # 1) Perception stage
        perception_score = rng.random()
        trace.append(
            {"stage": "perception", "score": perception_score, "threshold": thresholds["perception"]}
        )
        if perception_score < thresholds["perception"]:
            failure = FailureCode.PERCEPTION_FAILED

        # 2) Grasp stage
        if failure == FailureCode.NONE:
            grasp_score = rng.random()
            trace.append({"stage": "grasp", "score": grasp_score, "threshold": thresholds["grasp"]})
            if grasp_score < thresholds["grasp"]:
                failure = FailureCode.GRASP_FAILED

        # 3) Place stage
        if failure == FailureCode.NONE:
            place_score = rng.random()
            trace.append({"stage": "place", "score": place_score, "threshold": thresholds["place"]})
            if place_score < thresholds["place"]:
                failure = FailureCode.PLACE_FAILED

        # Safety events
        if failure == FailureCode.NONE:
            collision_score = rng.random()
            if collision_score < thresholds["collision"]:
                collision_count = 1
                failure = FailureCode.COLLISION
            torque_score = rng.random()
            if torque_score < thresholds["torque"]:
                torque_exceeded_count = 1
                failure = FailureCode.TORQUE_LIMIT

        elapsed = time.perf_counter() - started
        if failure == FailureCode.NONE and elapsed > cfg.timeout_seconds:
            failure = FailureCode.TIMEOUT

        success = failure == FailureCode.NONE
        duration_ms = max(1, int(elapsed * 1000))
        result = EpisodeResult(
            run_id=run_id,
            seed=seed,
            success=success,
            failure_code=failure.value,
            duration_ms=duration_ms,
            metrics={
                "strategy": strategy,
                "collision_count": collision_count,
                "torque_limit_exceeded_count": torque_exceeded_count,
                "task_stages": ["perception", "grasp", "place", "validate"],
                "success_rate": self._projected_success_rate(success),
            },
            profile=cfg.to_dict(),
        )
        self._results[run_id] = result
        self._failure_traces[run_id] = {
            "run_id": run_id,
            "seed": seed,
            "strategy": strategy,
            "failure_code": failure.value,
            "trace": trace,
            "profile": cfg.to_dict(),
            "created_at": result.created_at,
        }
        return {"status": "success", "result": result.to_dict()}

    async def get_metrics(self, run_id: str) -> Dict[str, Any]:
        if run_id not in self._results:
            return {"status": "error", "message": f"run_id '{run_id}' not found"}

        current = self._results[run_id]
        all_results = list(self._results.values())
        total = len(all_results)
        success_count = sum(1 for r in all_results if r.success)
        failure_counts: Dict[str, int] = {}
        for r in all_results:
            failure_counts[r.failure_code] = failure_counts.get(r.failure_code, 0) + 1

        return {
            "status": "success",
            "run_id": run_id,
            "metrics": current.metrics,
            "summary": {
                "total_runs": total,
                "success_runs": success_count,
                "success_rate": (success_count / total) if total else 0.0,
                "failure_distribution": failure_counts,
            },
        }

    async def get_failure_trace(self, run_id: str) -> Dict[str, Any]:
        if run_id not in self._failure_traces:
            return {"status": "error", "message": f"run_id '{run_id}' not found"}
        return {"status": "success", "trace": self._failure_traces[run_id]}

    def _build_thresholds(self, cfg: RandomizationProfile) -> Dict[str, float]:
        # Higher jitter/noise means a stricter threshold and higher failure chance.
        perception = 0.08 + (cfg.sensor_noise if cfg.enable_sensor_noise else 0.0)
        grasp = 0.08 + cfg.object_pose_jitter + (0.05 * cfg.obstacle_density)
        place = 0.07 + cfg.object_pose_jitter + (0.05 * cfg.camera_pose_jitter)
        collision = 0.02 + (0.08 * cfg.obstacle_density)
        torque = 0.02 + (cfg.torque_noise if cfg.enable_dynamics_jitter else 0.0)
        return {
            "perception": min(max(perception, 0.01), 0.95),
            "grasp": min(max(grasp, 0.01), 0.95),
            "place": min(max(place, 0.01), 0.95),
            "collision": min(max(collision, 0.0), 0.95),
            "torque": min(max(torque, 0.0), 0.95),
        }

    def _projected_success_rate(self, current_success: bool) -> float:
        total = len(self._results) + 1
        prior_success = sum(1 for r in self._results.values() if r.success)
        success_count = prior_success + (1 if current_success else 0)
        return success_count / total
