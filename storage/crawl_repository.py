from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from storage.database import Database


class CrawlRepository:
    """
    High-level repository for crawl sessions and pages.
    Wraps Database with domain-specific operations.
    """

    def __init__(self, db: Database | None = None) -> None:
        self._db = db or Database()

    def start_crawl(self, url: str) -> str:
        return self._db.create_session(url)

    def mark_running(self, session_id: str) -> None:
        self._db.update_session(
            session_id,
            status="running",
            started_at=datetime.utcnow().isoformat(),
        )

    def mark_done(self, session_id: str, pages: int, endpoint_count: int,
                  doc_type: str = "") -> None:
        self._db.update_session(
            session_id,
            status="completed",
            finished_at=datetime.utcnow().isoformat(),
            pages_visited=pages,
            endpoint_count=endpoint_count,
            doc_type=doc_type,
        )

    def mark_failed(self, session_id: str, error: str) -> None:
        self._db.update_session(
            session_id,
            status="failed",
            finished_at=datetime.utcnow().isoformat(),
            error=error[:1000],
        )

    def get_status(self, session_id: str) -> dict | None:
        return self._db.get_session(session_id)

    def save_endpoints(self, session_id: str, endpoints: list[dict]) -> None:
        self._db.save_endpoints(session_id, endpoints)

    def get_endpoints(self, session_id: str) -> list[dict]:
        return self._db.get_endpoints(session_id)

    def save_export(self, session_id: str, fmt: str, file_path: str) -> None:
        self._db.save_export(session_id, fmt, file_path)

    def get_exports(self, session_id: str) -> list[dict]:
        return self._db.get_exports(session_id)

    def update_detail(self, session_id: str, detail: dict) -> None:
        self._db.update_session(session_id, detail=json.dumps(detail))
