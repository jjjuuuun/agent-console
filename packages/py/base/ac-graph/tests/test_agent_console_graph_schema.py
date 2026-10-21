"""공개 JSON Schema 검사기(`compile_schema`·`check_instance`)."""

import pytest

from agent_console_graph import InvalidSchemaError, check_instance, compile_schema


def test_check_instance_reports_pointer() -> None:
    schema = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}
    [violation] = check_instance(schema, {"n": "x"})
    assert violation.pointer == "/n"
    assert violation.validator == "type"
    assert check_instance(schema, {"n": 1}) == []


def test_empty_schema_accepts_anything() -> None:
    assert compile_schema({})({"any": [1, 2]}) == []


def test_invalid_schema_raises() -> None:
    with pytest.raises(InvalidSchemaError):
        compile_schema({"type": 3})
