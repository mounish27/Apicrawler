from __future__ import annotations

import uuid
from datetime import datetime

from storage.database import Database


class SchemaRepository:
    """
    Stores inferred schemas and auth configs per crawl session.
    """

    def __init__(self, db: Database | None = None) -> None:
        self._db = db or Database()

    @property
    def _client(self):
        return self._db._client

    def save_schema(self, session_id: str, name: str, schema: dict, source: str = "") -> str:
        sid = str(uuid.uuid4())
        self._client.table("crawl_schemas").insert({
            "id": sid,
            "session_id": session_id,
            "name": name,
            "schema_json": schema,
            "source": source,
            "created_at": datetime.utcnow().isoformat(),
        }).execute()
        return sid

    def get_schemas(self, session_id: str) -> list[dict]:
        result = (
            self._client.table("crawl_schemas")
            .select("*")
            .eq("session_id", session_id)
            .execute()
        )
        rows = result.data or []
        for r in rows:
            r["schema"] = r.pop("schema_json", {})
        return rows

    def save_auth(self, session_id: str, auth_config: dict) -> None:
        self._client.table("auth_configs").upsert({
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "auth_type": auth_config.get("auth_type", "unknown"),
            "config_json": auth_config,
            "created_at": datetime.utcnow().isoformat(),
        }, on_conflict="session_id").execute()

    def get_auth(self, session_id: str) -> dict | None:
        result = (
            self._client.table("auth_configs")
            .select("config_json")
            .eq("session_id", session_id)
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]["config_json"]
