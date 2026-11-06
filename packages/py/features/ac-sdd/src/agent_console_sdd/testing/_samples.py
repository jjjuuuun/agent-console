"""테스트 표본 문서(체크 칸 작업 목록 형식의 작은 예, 기본 문법·프리셋이 아니다).

`render_tasks(names)`는 같은 문서를 다른 문법 이름(필드·상태 표시·단계 제목·구분자)으로 만든다.
`RENAMED_SYNTAX`는 그 이름에 맞춘 문법 데이터다(R0: 이름을 모두 바꿔도 같은 결과).
"""

from __future__ import annotations

from typing import Any

from agent_console_contracts.sdd import SpecDefinition

TASKS_TEMPLATE = """\
# 작업

{h2} Phase 6R — SDD

**묶음 1**

- [{done}] 6R.1 설계 [{owner}: pl] [{req}: R6.1{sep} R6.2] [{depends}: {none}]
  - 하는 일: 설계 문서.
  - 완료 기준: 승인.
- [{done}] 6R.2 화면 명세 [{owner}: web-designer-lead] [{req}: R6.1] [{depends}: 6R.1]
- [{todo}] 6R.3 계약 [{owner}: backend-lead] [{req}: R6.1{range}R6.3] [{depends}: 6R.1{sep} 6R.2]
- [{todo}] 6R.4 텍스트 틀 [{owner}: backend-lead] [{req}: R0.1] [{depends}: 6R.1]

{h3} 묶음 2 — 라이브러리

- [{todo}] 6R.10 `ac-sdd` 핵심: 문법 [{owner}: backend-lead] [{req}: R6.1{sep} R6.2{sep} R0.1] \
[{depends}: 6R.3{sep} 6R.4]
- [{todo}] 6R.11 계획·추적 [{owner}: backend-lead] [{req}: R6.3] [{depends}: 6R.10]
- [{todo}] 6R.12 통합 검증 [{owner}: qa-lead] [{req}: R6.1{range}R6.3] \
[{depends}: 6R.1{range}6R.11 전부]

예시(작업 아님):

```text
- [{todo}] 6R.99 코드 블록 안 [{depends}: 6R.1]
```

> - [{todo}] 6R.98 인용 안
"""

REQUIREMENTS = """\
# 요구사항

## R0 공통

**R0.1** 아무것도 하드코딩하지 않는다.

## R6 SDD

**R6.1** 웹에서 스펙 문서를 만들고 편집한다.

**R6.2** 작업을 실행과 잇는다.

**R6.3** 요구 ↔ 작업 ↔ 실행을 추적한다.

```text
**R9.9** 코드 블록 안은 요구가 아니다
```
"""

DEFAULT_NAMES: dict[str, str] = {
    "h2": "##",
    "h3": "###",
    "todo": " ",
    "done": "x",
    "owner": "owner",
    "req": "req",
    "depends": "depends",
    "sep": ",",
    "range": "~",
    "none": "—",
}

RENAMED_NAMES: dict[str, str] = {
    "h2": "####",
    "h3": "#####",
    "todo": ".",
    "done": "v",
    "owner": "who",
    "req": "needs",
    "depends": "after",
    "sep": ";",
    "range": "..",
    "none": "nothing",
}


def render_tasks(names: dict[str, str]) -> str:
    """표본 작업 문서를 `names`(키는 `DEFAULT_NAMES`와 같음)로 만든다."""
    return TASKS_TEMPLATE.format(**names)


def sample_spec(*docs: dict[str, Any]) -> SpecDefinition:
    """표본 스펙(문서를 주지 않으면 요구·설계·작업 세 문서)."""
    documents = list(docs) or [
        {
            "id": "requirements",
            "title": "요구",
            "file": "requirements.md",
            "roles": ["requirements"],
        },
        {"id": "design", "title": "설계", "file": "design.md"},
        {"id": "tasks", "title": "작업", "file": "tasks.md", "roles": ["tasks"]},
    ]
    return SpecDefinition.model_validate(
        {"kind": "spec", "id": "sample", "name": "표본", "documents": documents}
    )


def sample_files(names: dict[str, str] = DEFAULT_NAMES) -> dict[str, str]:
    """표본 스펙의 파일 → 본문."""
    return {
        "requirements.md": REQUIREMENTS,
        "design.md": "# 설계\n\n- [ ] 1.1 설계 문서의 체크 칸은 작업이 아니다\n",
        "tasks.md": render_tasks(names),
    }


RENAMED_SYNTAX: dict[str, Any] = {
    "task": {
        "list_item": "checkbox",
        "statuses": [
            {"id": "open", "label": "열림", "marker": "."},
            {"id": "closed", "label": "닫힘", "marker": ["v", "V"], "done": True},
        ],
        "id_pattern": r"^(?P<id>(?=[\w.\-]*\d)[0-9A-Za-z][\w.\-]*)\s+",
        "field_pattern": r"\[(?P<key>[\w\-]+):\s*(?P<value>[^\]]*)\]",
        "list_separator": ";",
        "range_separator": "..",
        "none_values": ["nothing", ""],
        "roles": {"after": "dependencies", "needs": "requirements", "who": "assignee"},
        "body": "nested",
    },
    "requirement": {
        "patterns": [
            r"^\*\*(?P<id>[A-Z][A-Za-z]*\d[\w.]*)\*\*",
            r"^#{2,6}\s+(?P<id>[A-Z][A-Za-z]*\d[\w.]*)\b",
        ]
    },
    "stage": {"heading_levels": [4, 5], "pattern": r"^(?P<id>\S+\s+\S+)"},
}
