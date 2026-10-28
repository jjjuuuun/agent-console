"""5.7R.33e 경로 지킴(design §PI.5 K33-7, X33): `x-path` 주석만 보고 폴더 밖 경로를 찾는다."""

from __future__ import annotations

import json
from typing import Any

import pytest

from agent_console_contracts import AgentSettings
from agent_console_projects import outside_paths, path_fields

ROOT = "/w/app"
STATE = "/srv/console/.state"


def _schema(name_cwd: str = "working_directory", name_dirs: str = "directories") -> dict[str, Any]:
    return {
        "type": "object",
        "$defs": {
            "Limits": {
                "type": "object",
                "properties": {
                    name_dirs: {
                        "anyOf": [
                            {"type": "array", "items": {"type": "string"}},
                            {"type": "null"},
                        ],
                        "x-path": "directory",
                    }
                },
            }
        },
        "properties": {
            name_cwd: {"anyOf": [{"type": "string"}, {"type": "null"}], "x-path": "directory"},
            "limits": {"anyOf": [{"$ref": "#/$defs/Limits"}, {"type": "null"}]},
            "files": {"type": "array", "items": {"type": "string", "x-path": "file"}},
            "env": {"type": "object", "additionalProperties": {"type": "string"}},
            "model": {"type": "string"},
            "nodes": {
                "type": "object",
                "additionalProperties": {
                    "type": "object",
                    "properties": {"cwd": {"type": "string", "x-path": "directory"}},
                },
            },
        },
    }


def _value(cwd_key: str = "working_directory", dirs_key: str = "directories") -> dict[str, Any]:
    return {
        cwd_key: "packages/web",  # 상대 → 폴더 안
        "limits": {dirs_key: ["/w/app/docs", "../secret", "{workspace}/tmp", STATE + "/rules"]},
        "files": ["notes.md", "/etc/passwd"],
        "env": {"HOME_DIR": "/root"},  # x-path 아님: 보지 않는다
        "model": "/also/not/a/path",
        "nodes": {"n1": {"cwd": "~/elsewhere"}},
    }


def _outside(schema: dict[str, Any], value: dict[str, Any]) -> list[tuple[str, str | None, str]]:
    found = outside_paths(
        value,
        schema,
        ROOT,
        [STATE],
        flavor="posix",
        placeholders={"workspace": ROOT},
        environ={"HOME": "/home/me"},
        layer="팀",
    )
    return [(p.value, p.resolved, p.pointer) for p in found]


def test_outside_paths_table() -> None:
    assert _outside(_schema(), _value()) == [
        ("../secret", "/w/secret", "/limits/directories/1"),
        ("/etc/passwd", "/etc/passwd", "/files/1"),
        ("~/elsewhere", "/home/me/elsewhere", "/nodes/n1/cwd"),
    ]


def test_renaming_fields_gives_same_result() -> None:
    """R0: 필드 이름을 바꿔도 x-path 주석만 같으면 같은 결과(코드에 필드 이름 없음)."""
    renamed = _outside(_schema("cwd_folder", "allowed"), _value("cwd_folder", "allowed"))
    expected = [
        (v, r, p.replace("/directories/", "/allowed/")) for v, r, p in _outside(_schema(), _value())
    ]
    assert renamed == expected
    without_annotation = json.loads(json.dumps(_schema()).replace('"x-path"', '"x-other"'))
    assert _outside(without_annotation, _value()) == []


@pytest.mark.parametrize(
    ("value", "inside"),
    [
        ("src", True),
        ("./src/../lib", True),
        ("..", False),
        ("/w/app", True),
        ("/w/app/", True),
        ("/w/apple", False),  # 앞부분만 같음
        ("/srv/console/.state/runs/x", True),  # 앱 허용 폴더
        ("/srv/console", False),
        ("C:\\x", False),  # 이 서버에서 쓸 수 없는 경로 → 밖
        ("~/x", False),  # 홈을 모르면 밖
    ],
)
def test_single_value_table(value: str, inside: bool) -> None:
    schema = {"properties": {"p": {"x-path": "directory"}}}
    found = outside_paths({"p": value}, schema, ROOT, [STATE], flavor="posix")
    assert (found == []) is inside


def test_windows_case_insensitive_root() -> None:
    schema = {"properties": {"p": {"x-path": "directory"}}}
    assert outside_paths({"p": "c:\\WORK\\app\\x"}, schema, "C:\\Work\\App", flavor="windows") == []
    assert outside_paths({"p": "D:\\x"}, schema, "C:\\Work\\App", flavor="windows") != []


def test_realpath_injection_catches_link_out() -> None:
    schema = {"properties": {"p": {"x-path": "directory"}}}

    def realpath(path: str) -> str:
        return "/etc" if path == "/w/app/link" else path

    found = outside_paths({"p": "link"}, schema, ROOT, flavor="posix", realpath=realpath)
    assert [p.value for p in found] == ["link"]


def test_contract_schema_annotations_are_found() -> None:
    """계약 AgentSettings의 x-path(작업 폴더·허용 디렉터리)가 그대로 걸린다."""
    schema = AgentSettings.model_json_schema()
    value = {"working_directory": "/tmp/x", "limits": {"directories": ["sub", "/opt"]}}
    fields = path_fields(schema, value)
    assert [(f.pointer, f.kind) for f in fields] == [
        ("/working_directory", "directory"),
        ("/limits/directories/0", "directory"),
        ("/limits/directories/1", "directory"),
    ]
    bad = outside_paths(value, schema, ROOT, flavor="posix", pointer_prefix="/settings")
    assert [p.pointer for p in bad] == [
        "/settings/working_directory",
        "/settings/limits/directories/1",
    ]


def test_empty_and_non_string_values_are_ignored() -> None:
    schema = {"properties": {"p": {"x-path": "file"}, "q": {"x-path": "directory"}}}
    assert path_fields(schema, {"p": "", "q": 3}) == []
    assert path_fields(schema, "not an object") == []
    assert path_fields({"$ref": "#/nope"}, {"a": "b"}) == []
