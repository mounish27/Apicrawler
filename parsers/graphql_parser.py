from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import httpx


_INTROSPECTION_QUERY = """
{
  __schema {
    queryType { name }
    mutationType { name }
    subscriptionType { name }
    types {
      name kind description
      fields(includeDeprecated: true) {
        name description isDeprecated deprecationReason
        args { name description type { ...TypeRef } defaultValue }
        type { ...TypeRef }
      }
      inputFields { name description type { ...TypeRef } defaultValue }
      interfaces { ...TypeRef }
      enumValues(includeDeprecated: true) { name description isDeprecated }
      possibleTypes { ...TypeRef }
    }
    directives {
      name description locations
      args { name description type { ...TypeRef } defaultValue }
    }
  }
}
fragment TypeRef on __Type {
  kind name
  ofType { kind name ofType { kind name ofType { kind name ofType { kind name } } } }
}
"""


class GraphQLParser:
    """
    Phase 13 — Detects GraphQL endpoints and runs introspection.
    """

    async def detect_and_introspect(self, page_url: str, html: str = "") -> dict | None:
        """Find the GraphQL endpoint from the page URL or HTML and run introspection."""
        candidates = self._candidate_endpoints(page_url, html)
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, verify=False) as client:
            for url in candidates:
                result = await self._introspect(client, url)
                if result:
                    return {"url": url, "introspection": result}
        return None

    def parse_introspection(self, data: dict) -> dict:
        """Normalise a raw introspection result."""
        if "__schema" in data:
            return data
        if "data" in data and "__schema" in data["data"]:
            return data["data"]
        return data

    # ── private ───────────────────────────────────────────────────────────

    def _candidate_endpoints(self, page_url: str, html: str) -> list[str]:
        candidates: list[str] = []
        # Common GraphQL paths
        for path in ("/graphql", "/api/graphql", "/gql", "/query"):
            candidates.append(urljoin(page_url, path))
        # Scan HTML for graphql references
        for m in re.finditer(r'["\']([^"\']*graphql[^"\']*)["\']', html, re.IGNORECASE):
            url = urljoin(page_url, m.group(1))
            if url not in candidates:
                candidates.append(url)
        return candidates

    async def _introspect(self, client: httpx.AsyncClient, url: str) -> dict | None:
        try:
            payload = {"query": _INTROSPECTION_QUERY}
            resp = await client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if "data" in data and "__schema" in data.get("data", {}):
                return data
            if "__schema" in data:
                return data
        except Exception:
            pass
        return None
