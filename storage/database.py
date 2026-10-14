from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from supabase import create_client, Client


class Database:
    def __init__(self, url: str = "", key: str = "") -> None:
        if not url or not key:
            from app.config import settings
            url = settings.supabase_url
            key = settings.supabase_key
        self._client: Client = create_client(url, key)

    # ── sessions ──────────────────────────────────────────────────────────

    def create_session(self, url: str) -> str:
        sid = str(uuid.uuid4())
        self._client.table("crawl_sessions").insert({
            "id": sid,
            "url": url,
            "status": "queued",
        }).execute()
        return sid

    def update_session(self, sid: str, **fields: Any) -> None:
        if not fields:
            return
        self._client.table("crawl_sessions").update(fields).eq("id", sid).execute()

    def get_session(self, sid: str) -> dict | None:
        result = self._client.table("crawl_sessions").select("*").eq("id", sid).execute()
        return result.data[0] if result.data else None

    # ── endpoints ─────────────────────────────────────────────────────────

    def save_endpoints(self, sid: str, endpoints: list[dict]) -> None:
        rows = []
        for ep in endpoints:
            rows.append({
                "id": str(uuid.uuid4()),
                "session_id": sid,
                "method": ep.get("method", "GET").upper(),
                "path": ep.get("path", "/"),
                "summary": ep.get("summary"),
                "description": ep.get("description"),
                "tags": ep.get("tags", []),
                "source_url": ep.get("source_url"),
                "parameters": ep.get("parameters", []),
                "request_body": ep.get("request_body"),
                "responses": ep.get("responses", {}),
                "auth_type": ep.get("auth_type", "unknown"),
                "deprecated": bool(ep.get("deprecated", False)),
            })
        if rows:
            self._client.table("endpoints").upsert(
                rows, on_conflict="session_id,method,path"
            ).execute()

    def get_endpoints(self, sid: str) -> list[dict]:
        result = (
            self._client.table("endpoints")
            .select("*")
            .eq("session_id", sid)
            .order("path")
            .execute()
        )
        return result.data or []

    # ── exports ───────────────────────────────────────────────────────────

    def save_export(self, sid: str, fmt: str, path: str) -> None:
        self._client.table("exports").upsert({
            "id": str(uuid.uuid4()),
            "session_id": sid,
            "format": fmt,
            "path": path,
            "created_at": datetime.utcnow().isoformat(),
        }, on_conflict="session_id,format,path").execute()

    def get_exports(self, sid: str) -> list[dict]:
        result = self._client.table("exports").select("*").eq("session_id", sid).execute()
        return result.data or []
