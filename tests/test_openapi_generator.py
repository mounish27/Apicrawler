import pytest
from generators.openapi_generator import OpenAPIGenerator


SAMPLE_ENDPOINTS = [
    {
        "method": "GET",
        "path": "/api/v1/users",
        "summary": "List users",
        "description": "Returns all users",
        "tags": ["users"],
        "parameters": [
            {"name": "page", "location": "query", "type": "integer", "required": False,
             "description": "Page number", "enum": None, "example": 1},
        ],
        "request_body": None,
        "responses": {"200": {"description": "OK", "schema": {"type": "array"}}},
        "auth_type": "bearer",
        "deprecated": False,
        "operation_id": "listUsers",
    },
    {
        "method": "POST",
        "path": "/api/v1/users",
        "summary": "Create user",
        "description": "",
        "tags": ["users"],
        "parameters": [],
        "request_body": {
            "content_type": "application/json",
            "schema": {"type": "object", "properties": {"name": {"type": "string"}}},
            "required": True,
            "description": "",
        },
        "responses": {"201": {"description": "Created", "schema": None}},
        "auth_type": "bearer",
        "deprecated": False,
        "operation_id": "createUser",
    },
]


def test_generates_valid_openapi():
    gen = OpenAPIGenerator()
    spec = gen.generate(SAMPLE_ENDPOINTS, title="Test API", version="1.0.0")
    assert spec["openapi"] == "3.1.0"
    assert spec["info"]["title"] == "Test API"
    assert "/api/v1/users" in spec["paths"]


def test_get_operation():
    gen = OpenAPIGenerator()
    spec = gen.generate(SAMPLE_ENDPOINTS)
    op = spec["paths"]["/api/v1/users"]["get"]
    assert op["summary"] == "List users"
    assert op["operationId"] == "listUsers"
    assert any(p["name"] == "page" for p in op.get("parameters", []))


def test_post_has_request_body():
    gen = OpenAPIGenerator()
    spec = gen.generate(SAMPLE_ENDPOINTS)
    op = spec["paths"]["/api/v1/users"]["post"]
    assert "requestBody" in op
    assert "application/json" in op["requestBody"]["content"]


def test_security_schemes_from_auth():
    gen = OpenAPIGenerator()
    spec = gen.generate(SAMPLE_ENDPOINTS, auth_config={"auth_type": "bearer"})
    assert "components" in spec
    assert "securitySchemes" in spec["components"]
    assert "bearerAuth" in spec["components"]["securitySchemes"]


def test_tags_collected():
    gen = OpenAPIGenerator()
    spec = gen.generate(SAMPLE_ENDPOINTS)
    tag_names = [t["name"] for t in spec.get("tags", [])]
    assert "users" in tag_names
