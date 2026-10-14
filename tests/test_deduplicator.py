import pytest
from normalization.deduplicator import Deduplicator
from normalization.endpoint_normalizer import EndpointNormalizer


def ep(method, path, **kwargs):
    return {"method": method, "path": path, "summary": None, "description": None,
            "tags": [], "parameters": [], "request_body": None, "responses": {},
            "auth_type": "unknown", "deprecated": False, **kwargs}


def test_deduplicates_identical():
    dedup = Deduplicator()
    endpoints = [ep("GET", "/users"), ep("GET", "/users")]
    result = dedup.deduplicate(endpoints)
    assert len(result) == 1


def test_normalizes_id_segments():
    dedup = Deduplicator()
    endpoints = [ep("GET", "/users/123"), ep("GET", "/users/456")]
    result = dedup.deduplicate(endpoints)
    assert len(result) == 1
    assert "{" in result[0]["path"]


def test_keeps_different_methods():
    dedup = Deduplicator()
    endpoints = [ep("GET", "/users"), ep("POST", "/users")]
    result = dedup.deduplicate(endpoints)
    assert len(result) == 2


def test_merges_description():
    dedup = Deduplicator()
    endpoints = [
        ep("GET", "/users"),
        ep("GET", "/users", description="Returns a list of users"),
    ]
    result = dedup.deduplicate(endpoints)
    assert result[0]["description"] == "Returns a list of users"


def test_normalizer_singularizes():
    norm = EndpointNormalizer()
    assert norm.normalize_path("/users/123") == "/users/{userId}"
    assert norm.normalize_path("/orders/abc-def/items") in (
        "/orders/{orderId}/items", "/orders/{id}/items"
    )
