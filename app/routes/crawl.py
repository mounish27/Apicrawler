from __future__ import annotations

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse

from app.models.requests import CrawlRequest
from app.models.responses import CrawlStarted, CrawlStatus, EndpointList, EndpointItem
from app.services.crawl_service import CrawlService, get_status_log
from app.config import settings
from storage.crawl_repository import CrawlRepository

router = APIRouter()
_service = CrawlService()
_repo = CrawlRepository()


@router.post("/crawl", response_model=CrawlStarted, status_code=202)
async def start_crawl(req: CrawlRequest, background_tasks: BackgroundTasks):
    """Kick off an async crawl job. Returns session_id for polling."""
    session_id = _repo.start_crawl(req.url)
    background_tasks.add_task(
        _service._run, session_id, req.url, req.max_depth, req.max_pages, req.vendor, req.auto
    )
    return CrawlStarted(session_id=session_id, status="queued", message="Crawl started")


@router.get("/status/{session_id}", response_model=CrawlStatus)
async def get_status(session_id: str):
    row = _repo.get_status(session_id)
    if not row:
        raise HTTPException(404, "Session not found")
    return CrawlStatus(
        session_id=row["id"],
        url=row["url"],
        status=row["status"],
        doc_type=row.get("doc_type"),
        pages_visited=row.get("pages_visited", 0),
        endpoint_count=row.get("endpoint_count", 0),
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
        error=row.get("error"),
    )


@router.get("/status/{session_id}/log")
async def get_log(session_id: str):
    return {"session_id": session_id, "log": get_status_log(session_id)}


@router.get("/endpoints/{session_id}", response_model=EndpointList)
async def get_endpoints(session_id: str, method: str | None = None, tag: str | None = None):
    row = _repo.get_status(session_id)
    if not row:
        raise HTTPException(404, "Session not found")
    endpoints = _repo.get_endpoints(session_id)

    if method:
        endpoints = [ep for ep in endpoints if ep["method"].upper() == method.upper()]
    if tag:
        endpoints = [ep for ep in endpoints if tag in ep.get("tags", [])]

    return EndpointList(
        session_id=session_id,
        total=len(endpoints),
        endpoints=[
            EndpointItem(
                id=ep.get("id", ""),
                method=ep["method"],
                path=ep["path"],
                summary=ep.get("summary"),
                description=ep.get("description"),
                tags=ep.get("tags", []),
                auth_type=ep.get("auth_type", "unknown"),
                deprecated=bool(ep.get("deprecated", False)),
                parameters=ep.get("parameters") or [],
                request_body=ep.get("request_body"),
                responses=ep.get("responses") or {},
            )
            for ep in endpoints
        ],
    )


@router.get("/export/{session_id}/{format}")
async def export(session_id: str, format: str):
    """Download a generated export file."""
    row = _repo.get_status(session_id)
    if not row:
        raise HTTPException(404, "Session not found")
    if row["status"] != "completed":
        raise HTTPException(400, f"Crawl is not complete (status: {row['status']})")

    format_map = {
        "openapi": "openapi.yaml",
        "swagger": "swagger.json",
        "postman": "postman_collection.json",
        "inventory": "endpoint_inventory.json",
        "report": "crawl_report.json",
        "graphql": "schema.graphql",
    }
    filename = format_map.get(format.lower())
    if not filename:
        raise HTTPException(400, f"Unknown format '{format}'. Valid: {list(format_map)}")

    file_path = settings.exports_dir / session_id / filename
    if not file_path.exists():
        raise HTTPException(404, f"Export file not found: {filename}")

    media_type = "application/json" if filename.endswith(".json") else (
        "text/yaml" if filename.endswith(".yaml") else "text/plain"
    )
    return FileResponse(str(file_path), filename=filename, media_type=media_type)
