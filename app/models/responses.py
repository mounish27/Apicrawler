from __future__ import annotations

from typing import Any
from pydantic import BaseModel


class CrawlStarted(BaseModel):
    session_id: str
    status: str = "queued"
    message: str = "Crawl queued"


class CrawlStatus(BaseModel):
    session_id: str
    url: str
    status: str
    doc_type: str | None = None
    pages_visited: int = 0
    endpoint_count: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None


class EndpointItem(BaseModel):
    id: str
    method: str
    path: str
    summary: str | None = None
    description: str | None = None
    tags: list[str] = []
    auth_type: str = "unknown"
    deprecated: bool = False
    parameters: list[Any] = []
    request_body: Any | None = None
    responses: dict[str, Any] = {}


class EndpointList(BaseModel):
    session_id: str
    total: int
    endpoints: list[EndpointItem]


class ExportInfo(BaseModel):
    session_id: str
    format: str
    download_url: str
