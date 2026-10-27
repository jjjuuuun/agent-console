"""5.5R.7 C1: 맥락 구성 표지 `context_prepared_payload`(본문 없음)."""

from __future__ import annotations

import hashlib
from typing import Any

from agent_console_contracts import BundleSource, Resource, ResourceBundle
from agent_console_nodes_core import (
    CONTEXT_PREPARED_EVENT,
    content_digest,
    context_prepared_payload,
)
from agent_console_registry import Registry
from agent_console_resources import InMemoryResources, ResourceType, load_resource_types

SECRET = "sk-secret-zz9"


DEFINITIONS = [
    Resource.model_validate(
        {"id": "r1", "type": "rule", "name": "규칙", "content": {"file": "r.md"}}
    ),
    Resource.model_validate(
        {"id": "sk", "type": "skill", "name": "skill", "config": {"name": "review"}}
    ),
    Resource.model_validate({"id": "plain", "type": "instruction", "name": "p"}),
]


def _resources() -> InMemoryResources:
    return InMemoryResources(
        DEFINITIONS,
        contents={
            "r1": f"규칙 본문 {SECRET}",
            "sk": {"SKILL.md": b"# review", "scripts/run.sh": b"echo"},
        },
    )


def _types() -> Registry[ResourceType]:
    registry: Registry[ResourceType] = Registry("resource_types")
    load_resource_types(registry)
    return registry


def _bundle() -> ResourceBundle:
    return ResourceBundle(
        slots={"rules": ["…"], "skills": ["…"], "instructions": ["…"]},
        sources={
            "rules": [BundleSource(ref="r1", resource_type="rule")],
            "skills": [BundleSource(ref="sk", resource_type="skill")],
            "instructions": [
                BundleSource(ref="plain"),  # 종류를 모르면 칸 이름
                BundleSource(ref="r1", resource_type="rule"),  # 같은 id는 한 번만
            ],
        },
    )


def test_payload_has_only_ids_kinds_sizes_and_hashes() -> None:
    payload = context_prepared_payload(
        _bundle(), _resources(), resource_types=_types(), fragments=3
    )
    data: dict[str, Any] = payload.model_dump(mode="json")
    body = f"규칙 본문 {SECRET}".encode()
    tree = content_digest({"SKILL.md": b"# review", "scripts/run.sh": b"echo"})
    assert tree is not None
    assert data == {
        "resources": [
            {
                "id": "r1",
                "kind": "rule",
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            },
            {"id": "sk", "kind": "skill", "bytes": tree[0], "sha256": tree[1]},
            {"id": "plain", "kind": "instructions", "bytes": None, "sha256": None},
        ],
        "fragments": 3,
    }
    dumped = payload.model_dump_json()
    assert SECRET not in dumped
    assert "규칙 본문" not in dumped
    assert "# review" not in dumped
    assert CONTEXT_PREPARED_EVENT == "agent.context_prepared"


def test_without_lookup_or_bundle() -> None:
    assert context_prepared_payload(None).model_dump() == {"resources": [], "fragments": None}
    no_lookup = context_prepared_payload(_bundle(), fragments=0)
    assert [(r.id, r.bytes, r.sha256) for r in no_lookup.resources] == [
        ("r1", None, None),
        ("sk", None, None),
        ("plain", None, None),
    ]


def test_lookup_failure_leaves_size_unknown() -> None:
    class Broken(InMemoryResources):
        def read_content(self, resource: Resource) -> Any:
            raise OSError("디스크 오류")

    broken = Broken(DEFINITIONS, contents={"r1": "x"})
    payload = context_prepared_payload(_bundle(), broken)
    assert payload.resources[0].bytes is None


def test_content_digest_shapes() -> None:
    assert content_digest("가") == (3, hashlib.sha256("가".encode()).hexdigest())
    assert content_digest(b"ab") == (2, hashlib.sha256(b"ab").hexdigest())
    a = content_digest({"a.md": b"1", "b.md": b"2"})
    b = content_digest({"b.md": b"2", "a.md": b"1"})
    c = content_digest({"a.md": b"1", "c.md": b"2"})
    assert a == b
    assert a is not None
    assert c is not None
    assert a[1] != c[1]  # 경로가 바뀌면 해시도 바뀐다
    assert content_digest(None) is None
    assert content_digest({"a": 1}) is None
