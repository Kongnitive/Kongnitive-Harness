from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class EvolutionStore:
    """Small durable store for controller state and evidence."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS trajectories (
                id TEXT PRIMARY KEY,
                stage TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS candidates (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                base_revision TEXT NOT NULL,
                status TEXT NOT NULL,
                interface_changed INTEGER NOT NULL DEFAULT 0,
                approval_note TEXT,
                promotion_commit TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id TEXT NOT NULL,
                name TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self._connection.commit()

    def add_trajectory(self, trajectory_id: str, stage: str, payload: dict[str, Any]) -> None:
        self._connection.execute(
            "INSERT INTO trajectories(id, stage, payload) VALUES (?, ?, ?)",
            (trajectory_id, stage, json.dumps(payload, sort_keys=True)),
        )
        self._connection.commit()

    def add_candidate(self, candidate_id: str, path: Path, base_revision: str) -> None:
        self._connection.execute(
            "INSERT INTO candidates(id, path, base_revision, status) VALUES (?, ?, ?, 'created')",
            (candidate_id, str(path), base_revision),
        )
        self._connection.commit()

    def candidate(self, candidate_id: str) -> dict[str, Any]:
        row = self._connection.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown candidate: {candidate_id}")
        return dict(row)

    def set_candidate(self, candidate_id: str, status: str, **fields: Any) -> None:
        assignments = ["status = ?"]
        values: list[Any] = [status]
        for key, value in fields.items():
            assignments.append(f"{key} = ?")
            values.append(value)
        values.append(candidate_id)
        self._connection.execute(f"UPDATE candidates SET {', '.join(assignments)} WHERE id = ?", values)
        self._connection.commit()

    def add_evidence(self, candidate_id: str, kind: str, payload: dict[str, Any]) -> None:
        self._connection.execute(
            "INSERT INTO evidence(candidate_id, kind, payload) VALUES (?, ?, ?)",
            (candidate_id, kind, json.dumps(payload, sort_keys=True)),
        )
        self._connection.commit()

    def evidence(self, candidate_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT kind, payload, created_at FROM evidence WHERE candidate_id = ? ORDER BY id", (candidate_id,)
        ).fetchall()
        return [{"kind": row["kind"], "payload": json.loads(row["payload"]), "created_at": row["created_at"]} for row in rows]

    def add_skill(self, candidate_id: str, name: str, content: str) -> None:
        self._connection.execute(
            "INSERT INTO skills(candidate_id, name, content) VALUES (?, ?, ?)", (candidate_id, name, content),
        )
        self._connection.commit()

    def search_skills(self, query: str) -> list[dict[str, str]]:
        pattern = f"%{query}%"
        rows = self._connection.execute(
            "SELECT candidate_id, name, content FROM skills WHERE name LIKE ? OR content LIKE ? ORDER BY id DESC",
            (pattern, pattern),
        ).fetchall()
        return [dict(row) for row in rows]
