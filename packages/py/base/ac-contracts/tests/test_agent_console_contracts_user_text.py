"""사용자 문구 금지 패턴(5.2R.5, ux-overhaul §1.5-C): 데이터 한 곳 + 계약 설명 위반 0건."""

from __future__ import annotations

from agent_console_contracts.schema import build_schema
from agent_console_contracts.user_text import (
    find_forbidden_text,
    scan_forbidden_text,
    user_text_rules,
    user_text_rules_data,
)


def test_rules_come_from_one_data_file_and_compile() -> None:
    ids = [r.id for r in user_text_rules()]
    assert ids == [r["id"] for r in user_text_rules_data()["patterns"]]
    assert len(ids) == len(set(ids))
    assert all(r.scopes for r in user_text_rules())


def test_known_bad_texts_are_caught_and_good_texts_pass() -> None:
    bad = {
        "옛 문구(design §5R.6)": "design-ref",
        "ux-overhaul §1.5 참고": "section-number",
        "요구사항 R14.2에 따라": "requirement-id",
    }
    for text, rule in bad.items():
        assert rule in [v.rule for v in find_forbidden_text(text, scope="description")], text
    assert [v.rule for v in find_forbidden_text("노드 'n12' 실패", scope="messages")] == ["node-id"]
    # 노드 id 규칙은 사용자 문구에만 적용된다
    assert find_forbidden_text("예: 'n1'", scope="description") == []
    goods = ["'안내원'을(를) 실행할 백엔드가 정해지지 않았습니다.", "5R 이후 형식", "버전 0.8.0"]
    for good in goods:
        assert find_forbidden_text(good, scope="messages") == [], good


def test_scan_walks_json_and_can_limit_keys() -> None:
    doc = {"description": "좋음", "items": [{"title": "x §2"}], "value": "R1.1"}
    assert [v.path for v in scan_forbidden_text(doc, scope="description")] == [
        "/items/0/title",
        "/value",
    ]
    only = scan_forbidden_text(doc, scope="description", keys={"description", "title"})
    assert [v.path for v in only] == ["/items/0/title"]


def test_contract_descriptions_have_no_forbidden_patterns() -> None:
    schema = build_schema()
    schema["x-constants"].pop("USER_TEXT_RULES")  # 규칙 데이터 자신은 패턴을 담는다
    found = scan_forbidden_text(schema, scope="description", keys={"description", "title"})
    assert found == [], "\n".join(f"{v.path}: {v.match} — {v.text[:80]}" for v in found)


def test_generated_constant_matches_data() -> None:
    assert build_schema()["x-constants"]["USER_TEXT_RULES"] == user_text_rules_data()
