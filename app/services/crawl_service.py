from __future__ import annotations

import asyncio
import json
import traceback
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from app.config import settings
from crawler.recursive_crawler import RecursiveCrawler, PageResult
from parsers.doc_detector import DocDetector, DocType
from parsers.swagger_parser import SwaggerParser
from parsers.generic_parser import GenericParser
from parsers.graphql_parser import GraphQLParser
from parsers.ukg_parser import UKGParser
from parsers.workday_parser import WorkdayParser
from parsers.adp_parser import ADPParser
from parsers.dayforce_parser import DayforceParser
from parsers.toast_parser import ToastParser
from extraction.auth_detector import AuthDetector
from normalization.deduplicator import Deduplicator
from normalization.endpoint_normalizer import EndpointNormalizer
from normalization.schema_merger import SchemaMerger
from generators.openapi_generator import OpenAPIGenerator
from generators.swagger_generator import SwaggerGenerator
from generators.postman_generator import PostmanGenerator
from generators.graphql_generator import GraphQLGenerator
from storage.crawl_repository import CrawlRepository
from storage.schema_repository import SchemaRepository
from parsers.html_parser import HTMLParser
from extraction.example_parser import ExampleParser
from extraction.response_extractor import ResponseExtractor


_VENDOR_MAP = {
    "ukg": UKGParser,
    "workday": WorkdayParser,
    "adp": ADPParser,
    "dayforce": DayforceParser,
    "toast": ToastParser,
}

_STATUS_CALLBACKS: dict[str, list[str]] = {}


def get_status_log(session_id: str) -> list[str]:
    return _STATUS_CALLBACKS.get(session_id, [])


class CrawlService:
    """
    Phase 15 — Orchestrates the full crawl + parse + generate pipeline.
    Runs asynchronously, stores progress in SQLite.
    """

    def __init__(self) -> None:
        self._repo = CrawlRepository()
        self._schema_repo = SchemaRepository()
        self._detector = DocDetector()
        self._generic = GenericParser()
        self._swagger_parser = SwaggerParser()
        self._auth_detector = AuthDetector()
        self._dedup = Deduplicator()
        self._normalizer = EndpointNormalizer()
        self._schema_merger = SchemaMerger()
        self._openapi_gen = OpenAPIGenerator()
        self._swagger_gen = SwaggerGenerator()
        self._postman_gen = PostmanGenerator()
        self._gql_gen = GraphQLGenerator()
        self._gql_parser = GraphQLParser()
        self._html_parser = HTMLParser()
        self._example_parser = ExampleParser()
        self._response_extractor = ResponseExtractor()

    def start_crawl(self, url: str, max_depth: int = 3, max_pages: int = 100,
                    vendor: str | None = None) -> str:
        session_id = self._repo.start_crawl(url)
        _STATUS_CALLBACKS[session_id] = []
        asyncio.create_task(
            self._run(session_id, url, max_depth, max_pages, vendor)
        )
        return session_id

    async def _run(self, session_id: str, url: str, max_depth: int | None,
                   max_pages: int | None, vendor: str | None,
                   auto: bool = True) -> None:
        log = _STATUS_CALLBACKS.setdefault(session_id, [])

        def on_status(msg: str) -> None:
            log.append(msg)

        self._repo.mark_running(session_id)
        try:
            await self._crawl_and_generate(session_id, url, max_depth, max_pages, vendor, auto, on_status)
        except Exception as e:
            tb = traceback.format_exc()
            self._repo.mark_failed(session_id, f"{type(e).__name__}: {e}\n{tb[:4000]}")
            on_status(f"ERROR: {type(e).__name__}: {e}")

    async def _crawl_and_generate(
        self, session_id: str, url: str, max_depth: int | None,
        max_pages: int | None, vendor: str | None, auto: bool, on_status
    ) -> None:
        on_status("Starting crawl pipeline...")

        # Phase 1: detect vendor
        vendor_parser = self._get_vendor_parser(vendor, url)

        # Phase 2/3: crawl
        crawler = RecursiveCrawler(
            auto=auto,
            max_depth=max_depth,
            max_pages=max_pages,
            on_status=on_status,
        )
        pages: list[PageResult] = await crawler.crawl(url)

        on_status(f"Crawled {len(pages)} page(s). Parsing...")

        all_endpoints: list[dict] = []
        all_examples: list[Any] = []
        auth_config: dict = {"auth_type": "unknown"}
        doc_type = DocType.STATIC_HTML
        title = ""
        spec_version = "1.0.0"
        servers: list[str] = []
        graphql_introspection: dict | None = None
        raw_spec: dict | None = None

        for page in pages:
            # Intercepted spec (fast path)
            if page.intercepted_specs:
                newly_added: list[dict] = []
                for intercepted in page.intercepted_specs:
                    spec_data = intercepted.get("data", {})
                    parsed = self._generic.parse_spec(spec_data, intercepted.get("url", url))
                    newly_added.extend(parsed["endpoints"])
                    if parsed.get("auth"):
                        auth_config = parsed["auth"]
                    if not title and parsed.get("title"):
                        title = parsed["title"]
                    if parsed.get("servers"):
                        servers = parsed["servers"]
                    if parsed.get("version"):
                        spec_version = parsed["version"]
                    doc_type = DocType.OPENAPI_SPEC
                    raw_spec = spec_data
                all_endpoints.extend(newly_added)
                # Enrich with h1, p, examples, responses from the rendered HTML
                if page.html:
                    page_title, page_examples = self._enrich_from_html(
                        page.html, page.url, newly_added
                    )
                    if not title and page_title:
                        title = page_title
                    all_examples.extend(page_examples)
                continue

            if page.json_data:
                det = self._detector.from_json(page.json_data, page.url)
                if det.spec_data:
                    parsed = self._generic.parse_spec(det.spec_data, page.url)
                    newly_added = parsed["endpoints"]
                    all_endpoints.extend(newly_added)
                    doc_type = DocType.OPENAPI_SPEC
                    raw_spec = det.spec_data
                    if parsed.get("auth"):
                        auth_config = parsed["auth"]
                    if page.html:
                        page_title, page_examples = self._enrich_from_html(
                            page.html, page.url, newly_added
                        )
                        if not title and page_title:
                            title = page_title
                        all_examples.extend(page_examples)
                continue

            if page.html:
                if vendor_parser:
                    parsed = vendor_parser.parse_html(page.html, page.url)
                else:
                    parsed = self._generic.parse_page(page.html, page.url)

                all_endpoints.extend(parsed.get("endpoints", []))
                all_examples.extend(parsed.get("examples", []))
                if parsed.get("auth", {}).get("auth_type", "unknown") not in ("unknown", "none"):
                    auth_config = parsed["auth"]
                if not title:
                    title = self._html_parser.extract_title(page.html)
                doc_type = parsed.get("doc_type", DocType.STATIC_HTML)

                # Check for GraphQL
                if doc_type == DocType.GRAPHQL or not all_endpoints:
                    gql = await self._gql_parser.detect_and_introspect(page.url, page.html)
                    if gql:
                        graphql_introspection = gql["introspection"]
                        doc_type = DocType.GRAPHQL

        on_status(f"Extracted {len(all_endpoints)} raw endpoints. Normalizing...")

        # Phase 11: normalize + deduplicate
        all_endpoints = self._normalizer.normalize_all(all_endpoints)
        all_endpoints = self._dedup.deduplicate(all_endpoints)

        # Enrich POST/PUT bodies with inferred schemas
        if all_examples:
            all_endpoints = self._schema_merger.enrich_endpoint_schemas(all_endpoints, all_examples)

        on_status(f"{len(all_endpoints)} unique endpoints after dedup. Generating specs...")

        # Save to DB
        self._repo.save_endpoints(session_id, all_endpoints)
        self._schema_repo.save_auth(session_id, auth_config)

        # Phase 9/10: generate outputs
        parsed_url = urlparse(url)
        host = parsed_url.netloc
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

        openapi_spec = self._openapi_gen.generate(
            endpoints=all_endpoints,
            title=title or f"{host} API",
            version=spec_version,
            servers=servers or [base_url],
            auth_config=auth_config,
            security_schemes=auth_config.get("security_schemes"),
        )

        swagger_spec = self._swagger_gen.generate(
            endpoints=all_endpoints,
            title=title or f"{host} API",
            version=spec_version,
            host=host,
            auth_config=auth_config,
        )

        postman_col = self._postman_gen.generate(
            endpoints=all_endpoints,
            title=title or f"{host} API",
            base_url=base_url,
            auth_config=auth_config,
        )

        postman_env = self._postman_gen.generate_environment(
            title=f"{title or host} Environment",
            base_url=base_url,
            auth_config=auth_config,
        )

        # Endpoint inventory
        inventory = {
            "session_id": session_id,
            "source_url": url,
            "doc_type": str(doc_type),
            "total_endpoints": len(all_endpoints),
            "endpoints": [
                {
                    "method": ep["method"],
                    "path": ep["path"],
                    "summary": ep.get("summary"),
                    "tags": ep.get("tags", []),
                    "auth_type": ep.get("auth_type", "unknown"),
                    "deprecated": ep.get("deprecated", False),
                }
                for ep in all_endpoints
            ],
        }

        # Crawl report
        crawl_report = {
            "session_id": session_id,
            "url": url,
            "doc_type": str(doc_type),
            "pages_crawled": len(pages),
            "endpoints_found": len(all_endpoints),
            "auth_type": auth_config.get("auth_type"),
            "has_graphql": graphql_introspection is not None,
            "title": title,
            "servers": servers,
            "status_log": get_status_log(session_id),
        }

        # Write files
        out_dir = settings.exports_dir / session_id
        out_dir.mkdir(parents=True, exist_ok=True)

        files = {
            "openapi.yaml": yaml.dump(openapi_spec, default_flow_style=False, allow_unicode=True),
            "swagger.json": json.dumps(swagger_spec, indent=2),
            "postman_collection.json": json.dumps(postman_col, indent=2),
            "postman_environment.json": json.dumps(postman_env, indent=2),
            "endpoint_inventory.json": json.dumps(inventory, indent=2),
            "crawl_report.json": json.dumps(crawl_report, indent=2),
        }

        if graphql_introspection:
            gql_schema = self._gql_gen.generate_schema(graphql_introspection)
            gql_postman = self._gql_gen.generate_postman_requests(graphql_introspection, url)
            files["schema.graphql"] = gql_schema
            files["graphql_postman.json"] = json.dumps(gql_postman, indent=2)

        for filename, content in files.items():
            path = out_dir / filename
            path.write_text(content, encoding="utf-8")
            fmt = filename.rsplit(".", 1)[-1]
            self._repo.save_export(session_id, fmt, str(path))

        self._repo.mark_done(
            session_id,
            pages=len(pages),
            endpoint_count=len(all_endpoints),
            doc_type=str(doc_type),
        )
        on_status(f"Done. {len(all_endpoints)} endpoints exported to {out_dir}")

    def _enrich_from_html(
        self,
        html: str,
        page_url: str,
        endpoints: list[dict],
    ) -> tuple[str, list]:
        """
        Parse the fully-rendered HTML of a page and use it to fill in fields
        that the spec alone doesn't provide: summary, description, request/response
        examples, and response status codes.
        Only fills blanks — never overwrites values already set by the spec.
        Returns (page_title, raw_example_data_list).
        """
        if not html:
            return "", []

        page_title = self._html_parser.extract_title(html)
        page_desc = self._html_parser.extract_lead_paragraph(html)
        raw_examples = self._example_parser.extract_from_html(html)
        responses = self._response_extractor.extract_from_html(html)

        for ep in endpoints:
            if not ep.get("summary") and page_title:
                ep["summary"] = page_title
            if not ep.get("description") and page_desc:
                ep["description"] = page_desc
            # Only apply HTML responses when the spec gave us nothing meaningful
            if not ep.get("responses") and responses:
                ep["responses"] = responses

        if raw_examples:
            self._example_parser.attach_to_endpoints(endpoints, raw_examples)

        return page_title, [e["data"] for e in raw_examples]

    def _get_vendor_parser(self, vendor: str | None, url: str):
        if vendor and vendor.lower() in _VENDOR_MAP:
            return _VENDOR_MAP[vendor.lower()]()
        # Auto-detect by domain keywords
        domain = urlparse(url).netloc.lower()
        for keyword, parser_cls in [
            ("ukg", UKGParser), ("ultipro", UKGParser), ("kronos", UKGParser),
            ("workday", WorkdayParser),
            ("adp", ADPParser),
            ("dayforce", DayforceParser), ("ceridian", DayforceParser),
            ("toasttab", ToastParser), ("pos.toasttab", ToastParser),
        ]:
            if keyword in domain:
                return parser_cls()
        return None
