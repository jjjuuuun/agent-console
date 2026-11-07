"""계약 0.14.4(묶음 4b V1, 더하기만): `projects` 3.4.0.

- `CopyPlanItem.blocked`·`issues` — 복사 계획 항목의 막힘과 항목 이슈(선택, 0.14.3 응답이 그대로
  읽힌다).
"""

from agent_console_contracts import (
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    CopyPlan,
    CopyPlanItem,
    Issue,
    KnownIssueCodes,
)
from agent_console_contracts.schema import build_schema


def test_contracts_version_is_0_14_4() -> None:
    assert CONTRACTS_VERSION == "0.14.4"
    assert build_schema()["x-constants"]["CONTRACTS_VERSION"] == "0.14.4"
    assert CONTRACT_VERSIONS == {
        "common": "1.12.0",
        "resources": "1.1.0",
        "logs": "1.2.0",
        "definitions": "1.7.0",
        "runs": "1.8.0",
        "usage": "1.1.0",
        "projects": "3.4.0",
        "chat": "1.3.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "architecture": "1.0.0",
        "memory": "1.1.0",
        "sdd": "1.2.0",
        "wiki": "1.2.0",
        "modules": "1.6.0",
    }


def test_old_plan_item_still_reads() -> None:
    item = CopyPlanItem.model_validate(
        {
            "kind": "agent",
            "id": "a",
            "reason": "requested",
            "source_version": "1",
            "target_state": "absent",
        }
    )
    assert item.blocked is False
    assert item.issues == []


def test_blocked_item_round_trip() -> None:
    issue = Issue(
        severity="error",
        code=KnownIssueCodes.SECRET_PLAIN_FOUND,
        message="m",
        path="/x",
        details={"kind": "agent", "id": "a", "path": "/x", "reason": "key_name"},
    )
    plan = CopyPlan(
        items=[
            CopyPlanItem(
                kind="agent",
                id="a",
                reason="requested",
                source_version="1",
                target_state="absent",
                default_action="skip",
                blocked=True,
                issues=[issue],
            )
        ]
    )
    again = CopyPlan.model_validate_json(plan.model_dump_json())
    assert again.items[0].blocked is True
    assert again.items[0].issues[0].code == "secret.plain_found"


def test_schema_documents_blocked_and_issues() -> None:
    props = build_schema()["$defs"]["CopyPlanItem"]["properties"]
    assert "blocked" in props
    assert "issues" in props
