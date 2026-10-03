"""SQLite storage. Each operation owns its connection; writes are transactional."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import numpy as np


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError("Unsupported database schema; restore compatible software")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS samples (
                id TEXT PRIMARY KEY, person TEXT NOT NULL, embedding BLOB NOT NULL,
                dimensions INTEGER NOT NULL, model TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                UNIQUE(person, model, source_hash))""")
            db.execute("PRAGMA user_version=1")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA secure_delete=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def health(self) -> None:
        with self.connect() as db:
            db.execute("SELECT count(*) FROM samples").fetchone()

    def add(self, person: str, embedding: np.ndarray, model: str, source_hash: str, limit: int) -> str:
        embedding = np.asarray(embedding, dtype="<f4").reshape(-1)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT id FROM samples WHERE person=? AND model=? AND source_hash=?",
                (person, model, source_hash),
            ).fetchone()
            if existing:
                return existing[0]
            if db.execute("SELECT count(*) FROM samples").fetchone()[0] >= limit:
                raise ValueError("Enrollment capacity reached; delete unused samples")
            sample_id = str(uuid4())
            db.execute(
                """INSERT INTO samples
                (id,person,embedding,dimensions,model,source_hash) VALUES (?,?,?,?,?,?)""",
                (sample_id, person, embedding.tobytes(), embedding.size, model, source_hash),
            )
            return sample_id

    def embeddings(self, model: str) -> list[tuple[str, np.ndarray]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT person,embedding,dimensions FROM samples WHERE model=?", (model,)
            ).fetchall()
        result = []
        for row in rows:
            vector = np.frombuffer(row["embedding"], dtype="<f4")
            if vector.size != row["dimensions"] or not np.isfinite(vector).all():
                raise RuntimeError("Invalid stored embedding")
            result.append((row["person"], vector))
        return result

    def people(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT id,person,model,created_at FROM samples ORDER BY person,created_at,id")
            people: dict[str, dict] = {}
            for row in rows:
                person = people.setdefault(row["person"], {"name": row["person"], "samples": 0, "items": []})
                person["samples"] += 1
                person["items"].append({k: row[k] for k in ("id", "model", "created_at")})
            return list(people.values())

    def delete(self, person: str, sample_id: str | None = None) -> int:
        with self.connect() as db:
            if sample_id is None:
                count = db.execute("DELETE FROM samples WHERE person=?", (person,)).rowcount
            else:
                count = db.execute(
                    "DELETE FROM samples WHERE person=? AND id=?", (person, sample_id)
                ).rowcount
        return count
