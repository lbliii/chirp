"""Persistence for :class:`~chirp.settings.registry.SettingsRegistry`."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypedDict, runtime_checkable

from chirp.data.database import Database

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS _chirp_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    version INTEGER NOT NULL,
    body TEXT NOT NULL
)
"""
_LOAD_SQL = "SELECT version, body FROM _chirp_settings WHERE id = 1"
_EXISTS_SQL = "SELECT 1 AS present FROM _chirp_settings WHERE id = 1"
_UPDATE_SQL = "UPDATE _chirp_settings SET version = ?, body = ? WHERE id = 1"
_INSERT_SQL = "INSERT INTO _chirp_settings (id, version, body) VALUES (1, ?, ?)"


class SettingsDocument(TypedDict):
    version: int
    values: dict[str, Any]


@runtime_checkable
class SettingsStore(Protocol):
    async def load(self) -> SettingsDocument | None: ...

    async def save(self, doc: SettingsDocument) -> None: ...


@dataclass(frozen=True, slots=True)
class FileSettingsStore:
    """Single JSON file — atomic replace on write."""

    path: Path

    async def load(self) -> SettingsDocument | None:
        if not self.path.exists():
            return None
        raw = self.path.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        data = json.loads(raw)
        if not isinstance(data, dict):
            msg = f"settings file {self.path} must contain a JSON object"
            raise TypeError(msg)
        version = int(data.get("version", 0))
        values = data.get("values", {})
        if not isinstance(values, dict):
            msg = f"settings file {self.path} 'values' must be an object"
            raise TypeError(msg)
        return {"version": version, "values": values}

    async def save(self, doc: SettingsDocument) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(doc, sort_keys=True, separators=(",", ":"))
        fd, tmp = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


@dataclass(frozen=True, slots=True)
class DatabaseSettingsStore:
    """Single-row JSON document in ``_chirp_settings``."""

    db: Database

    async def load(self) -> SettingsDocument | None:
        await self.db.execute_script(_CREATE_TABLE_SQL)
        rows = await self.db.fetch_raw(_LOAD_SQL)
        if not rows:
            return None
        row = rows[0]
        version, body = row["version"], row["body"]
        data = json.loads(body)
        if not isinstance(data, dict):
            msg = "_chirp_settings.body must be a JSON object"
            raise TypeError(msg)
        values = data.get("values", data)
        if not isinstance(values, dict):
            msg = "_chirp_settings.body 'values' must be an object"
            raise TypeError(msg)
        return {"version": int(version), "values": values}

    async def save(self, doc: SettingsDocument) -> None:
        await self.db.execute_script(_CREATE_TABLE_SQL)
        body = json.dumps({"values": doc["values"]}, sort_keys=True, separators=(",", ":"))
        existing = await self.db.fetch_raw(_EXISTS_SQL)
        if existing:
            await self.db.execute(
                _UPDATE_SQL,
                doc["version"],
                body,
            )
        else:
            await self.db.execute(
                _INSERT_SQL,
                doc["version"],
                body,
            )
