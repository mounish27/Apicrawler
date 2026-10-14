import pytest
from extraction.schema_extractor import SchemaExtractor


def test_infer_primitive_types():
    s = SchemaExtractor()
    assert s.infer("hello")["type"] == "string"
    assert s.infer(42)["type"] == "integer"
    assert s.infer(3.14)["type"] == "number"
    assert s.infer(True)["type"] == "boolean"
    assert s.infer(None)["nullable"] is True


def test_infer_object():
    s = SchemaExtractor()
    schema = s.infer({"name": "Alice", "age": 30})
    assert schema["type"] == "object"
    assert "name" in schema["properties"]
    assert "age" in schema["properties"]
    assert schema["properties"]["name"]["type"] == "string"
    assert schema["properties"]["age"]["type"] == "integer"


def test_infer_array():
    s = SchemaExtractor()
    schema = s.infer([{"id": 1}, {"id": 2}])
    assert schema["type"] == "array"
    assert schema["items"]["type"] == "object"


def test_merge_schemas():
    s = SchemaExtractor()
    a = s.infer({"id": 1, "name": "Alice"})
    b = s.infer({"id": 2, "name": "Bob", "email": "b@example.com"})
    merged = s.merge([a, b])
    assert "id" in merged["properties"]
    assert "name" in merged["properties"]
    assert "email" in merged["properties"]


def test_string_format_detection():
    s = SchemaExtractor()
    assert s.infer("2024-01-15")["format"] == "date"
    assert s.infer("2024-01-15T10:30:00Z")["format"] == "date-time"
    assert s.infer("123e4567-e89b-12d3-a456-426614174000")["format"] == "uuid"
    assert s.infer("user@example.com")["format"] == "email"


def test_infer_from_examples():
    s = SchemaExtractor()
    schema = s.infer_from_examples([
        {"id": 1, "status": "active"},
        {"id": 2, "status": "inactive", "note": "archived"},
    ])
    assert schema["type"] == "object"
    assert "id" in schema["properties"]
    assert "status" in schema["properties"]
    # note is in only one example → should be nullable
    assert "note" in schema["properties"]
