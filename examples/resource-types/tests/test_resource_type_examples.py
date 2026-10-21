"""선언형 리소스 종류 예제(`examples/resource-types/*.yaml`)가 로더를 통과하고 기여를 만드는지.

서버와 같은 로더(`load_declarative_types`)로 이 폴더를 읽는다(workspace 폴더와 같은 형식).
"""

from __future__ import annotations

from pathlib import Path

from agent_console_contracts import Resource, ResourceAttachment
from agent_console_resources import (
    ContributeContext,
    load_declarative_types,
    new_resource_types,
    validate_resource,
)

EXAMPLES = Path(__file__).resolve().parents[1]


def test_every_example_file_loads() -> None:
    registry = new_resource_types()
    reports = load_declarative_types(EXAMPLES, registry)
    assert reports, "예제 파일이 하나도 없다"
    assert [(r.source, r.error) for r in reports if r.status != "loaded"] == []
    assert {e.key for e in registry.list()} >= {"prompt-snippet"}


def test_prompt_snippet_contributes_title_and_body_to_instructions() -> None:
    registry = new_resource_types()
    load_declarative_types(EXAMPLES, registry)
    snippet = registry.get("prompt-snippet")
    assert snippet.descriptor.declarative is True
    assert snippet.descriptor.contributes == ["instructions"]
    resource = Resource.model_validate(
        {
            "schema_version": 1,
            "id": "polite",
            "type": "prompt-snippet",
            "name": "공손",
            "config": {"tone": "formal"},
        }
    )
    ctx = ContributeContext(attachment=ResourceAttachment(ref="polite"))
    [contribution] = snippet.contribute(resource, "항상 존댓말.", ctx)
    assert contribution.slot == "instructions"
    assert contribution.value == ["## 공손\n항상 존댓말."]


def test_removed_example_reports_unknown_type_warning() -> None:
    """README 주장 고정: 파일을 지우면(등록 없음) 리소스는 남고 `resource.unknown_type` 경고."""
    resource = Resource.model_validate(
        {"id": "polite", "type": "prompt-snippet", "name": "공손", "config": {"tone": "formal"}}
    )
    issues = validate_resource(resource, new_resource_types())
    assert [(i.severity, i.code) for i in issues] == [("warning", "resource.unknown_type")]
