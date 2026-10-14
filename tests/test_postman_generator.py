import json
import pytest
from generators.postman_generator import PostmanGenerator


ENDPOINTS = [
    {
        "method": "GET",
        "path": "/api/v1/employees",
        "summary": "List employees",
        "tags": ["employees"],
        "parameters": [
            {"name": "page", "location": "query", "type": "integer", "required": False,
             "description": "", "enum": None, "example": 1},
        ],
        "request_body": None,
        "responses": {"200": {"description": "OK"}},
        "auth_type": "bearer",
        "deprecated": False,
    },
    {
        "method": "POST",
        "path": "/api/v1/employees",
        "summary": "Create employee",
        "tags": ["employees"],
        "parameters": [],
        "request_body": {
            "content_type": "application/json",
            "schema": {"type": "object", "properties": {"name": {"type": "string"}}},
            "required": True,
            "description": "",
        },
        "responses": {"201": {"description": "Created"}},
        "auth_type": "bearer",
        "deprecated": False,
    },
]


def test_collection_structure():
    gen = PostmanGenerator()
    col = gen.generate(ENDPOINTS, title="Test", base_url="https://api.example.com")
    assert col["info"]["name"] == "Test"
    assert "_postman_id" in col["info"]
    assert col["info"]["schema"].endswith("collection.json")


def test_folder_grouping():
    gen = PostmanGenerator()
    col = gen.generate(ENDPOINTS)
    # Should have an "employees" folder
    folders = [item for item in col["item"] if "item" in item]
    assert any(f["name"] == "employees" for f in folders)


def test_request_body_present():
    gen = PostmanGenerator()
    col = gen.generate(ENDPOINTS)
    folder = next(f for f in col["item"] if f.get("name") == "employees")
    post_req = next(r for r in folder["item"] if r["request"]["method"] == "POST")
    assert "body" in post_req["request"]
    raw = json.loads(post_req["request"]["body"]["raw"])
    assert isinstance(raw, dict)


def test_query_params():
    gen = PostmanGenerator()
    col = gen.generate(ENDPOINTS)
    folder = next(f for f in col["item"] if f.get("name") == "employees")
    get_req = next(r for r in folder["item"] if r["request"]["method"] == "GET")
    query = get_req["request"]["url"].get("query", [])
    assert any(q["key"] == "page" for q in query)


def test_environment_generation():
    gen = PostmanGenerator()
    env = gen.generate_environment("Test Env", "https://api.example.com",
                                   {"auth_type": "bearer"})
    keys = [v["key"] for v in env["values"]]
    assert "baseUrl" in keys
    assert "accessToken" in keys
