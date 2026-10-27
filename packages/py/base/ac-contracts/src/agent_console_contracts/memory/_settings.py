"""메모리 사용자 데이터: 설정 섹션 `memory`, 범위 종류, 리소스 `memory`의 접근 설정(모르는 키 보존).

- `MemorySettings`: 워크스페이스 설정의 `memory` 섹션(메모리 모듈이 소유). 공통 설정 모델에는 필드를
  두지 않는다(구조도 설정과 같은 방식, design §5.7R.1.4). 공통 설정이 모르는 키를 보존하므로
  왕복된다.
- `MemoryScopeKindSpec`: 범위 종류 데이터 한 칸(design §5.7R.1.2). 이름은 사용자 데이터다.
- `MemoryAccessConfig`: 리소스 종류 `memory`의 config(design §5.7R.1.3). 도구 이름·설명·결과 머리
  줄의 기본값은 패키지 데이터 `data/memory_access_defaults.json`에서 온다(코드에 두지 않음).

모델 docstring은 설정 폼의 설명이라 사용자 말로 쓰고, 개발자용 설명은 `#` 주석에 둔다.
"""

import json
from functools import cache
from importlib.resources import files
from typing import Any, Literal

from pydantic import ConfigDict, Field

from agent_console_contracts._base import DefinitionModel, NonEmptyStr, Slug
from agent_console_contracts.common import x_ui
from agent_console_contracts.runs import ConditionSpec

_DEFAULTS_FILE = "memory_access_defaults.json"

MemoryAccessOp = Literal["read", "search", "write", "delete"]
"""범위별 허용 동작(고정 어휘 — 도구 처리 코드가 아는 동작). 도구 하나가 동작 하나다."""

MemorySecretPolicy = Literal["reject", "redact"]
"""쓰기에서 비밀 의심 값을 찾았을 때: reject = 거부, redact = 가리고 저장."""

MemoryRetentionAction = Literal["archive", "delete"]
"""정리 규칙 동작: archive = 보관, delete = 표시 삭제(되돌릴 수 있음)."""

_ACCESS_LABELS = {"read": "읽기", "search": "검색", "write": "쓰기", "delete": "지우기"}


@cache
def memory_access_defaults() -> dict[str, Any]:
    """접근 설정 기본값 데이터 원본(`data/memory_access_defaults.json`).

    반환: `{version, tools: {search|read|write|delete: {name, description}}, result_header,
    max_result_chars}`. 같은 객체를 돌려주므로 고치지 말고 복사해 쓴다.
    """
    raw = files("agent_console_contracts").joinpath("data", _DEFAULTS_FILE).read_text("utf-8")
    data: dict[str, Any] = json.loads(raw)
    return data


def _default_access() -> list[MemoryAccessOp]:
    return ["read", "search"]


def _tool_default(op: str) -> dict[str, Any]:
    return dict(memory_access_defaults()["tools"][op])


class MemoryScopeKindSpec(DefinitionModel):
    """메모리를 나누는 범위 한 종류입니다(예: 팀, 프로젝트, 공용). 이름과 나누는 규칙을 둡니다."""

    # 사용자 `memory.scope_kinds`의 값 하나. 키(범위 종류 id)는 바깥 dict의 키다. `id`는 접근
    # 맥락(`MemoryAccessContext`)의 JSON 포인터 틀(대응표 `{/pointer}`와 같은 문법)이고, 푼 값이
    # 비면 그 범위는 그 실행에서 쓸 수 없다(`memory.scope_unavailable`). 빈 틀 = 범위 하나뿐.

    model_config = ConfigDict(title="범위 종류")

    label: NonEmptyStr = Field(
        title="이름",
        description="화면과 에이전트 도구 결과에 보이는 범위 이름입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="범위를 다른 이름으로 부르고 싶을 때 바꾸세요.", example="팀"
        ),
    )
    description: str = Field(
        default="",
        title="설명",
        description="이 범위에 어떤 기록을 두는지 적습니다. 화면에 함께 보입니다.",
        json_schema_extra=x_ui(tier="advanced", example="실행한 팀 구성의 기록"),
    )
    id: str = Field(
        default="",
        title="범위를 나누는 값",
        description=(
            "실행 정보에서 범위를 나눌 값을 고릅니다. 비우면 모두가 같은 범위 하나를 씁니다."
        ),
        json_schema_extra=x_ui(
            tier="basic",
            when="팀이나 프로젝트마다 기록을 따로 두고 싶을 때 적으세요.",
            example="{/project_id}",
        ),
    )


class MemoryScopeAccess(DefinitionModel):
    """에이전트가 이 범위에서 할 수 있는 일입니다."""

    model_config = ConfigDict(title="범위 권한")

    kind: Slug = Field(
        title="범위 종류",
        description="권한을 줄 범위 종류입니다. 메모리 설정의 범위 종류 목록에서 고릅니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="에이전트가 쓸 범위를 바꾸고 싶을 때 고르세요.",
            example="notes",
            widget="memory-scope-kind",
        ),
    )
    access: list[MemoryAccessOp] = Field(
        default_factory=_default_access,
        title="허용할 일",
        description="읽기·검색·쓰기·지우기 중 허용할 것을 고릅니다. 고른 일의 도구만 줍니다.",
        json_schema_extra={
            "default": ["read", "search"],
            **x_ui(
                tier="basic",
                when="에이전트가 기록을 남기게 하려면 쓰기를 더하세요.",
                enum_labels=_ACCESS_LABELS,
            ),
        },
    )


class MemoryToolText(DefinitionModel):
    """에이전트에게 보이는 도구 이름과 설명입니다."""

    model_config = ConfigDict(title="도구 표시")

    name: str = Field(
        pattern=r"^[A-Za-z0-9_-]{1,64}$",
        title="도구 이름",
        description="에이전트가 부르는 이름입니다. 영문·숫자·밑줄·빼기만 씁니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="다른 도구와 이름이 겹치거나 팀 규칙에 맞추고 싶을 때 바꾸세요.",
            example="team_notes_search",
        ),
    )
    description: str = Field(
        title="도구 설명",
        description="에이전트가 언제 이 도구를 쓸지 판단하는 설명입니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="에이전트가 도구를 너무 자주 쓰거나 안 쓸 때 고치세요.",
            example="팀 결정 기록을 찾습니다.",
        ),
    )


class MemoryTools(DefinitionModel):
    """동작마다 에이전트에게 보이는 도구 이름과 설명입니다. 비우면 기본값을 씁니다."""

    # 동작 이름(search·read·write·delete)은 계약 어휘다. 모델에게 보이는 이름·설명만 데이터이고
    # 기본값은 패키지 데이터에서 온다. 지우기 도구는 지우기를 허용한 범위가 있을 때만 준다.

    model_config = ConfigDict(title="도구")

    search: MemoryToolText = Field(
        default_factory=lambda: MemoryToolText.model_validate(_tool_default("search")),
        title="검색 도구",
        description="기록을 찾는 도구입니다.",
        json_schema_extra={"default": _tool_default("search"), **x_ui(tier="advanced")},
    )
    read: MemoryToolText = Field(
        default_factory=lambda: MemoryToolText.model_validate(_tool_default("read")),
        title="읽기 도구",
        description="키 하나의 기록을 읽는 도구입니다.",
        json_schema_extra={"default": _tool_default("read"), **x_ui(tier="advanced")},
    )
    write: MemoryToolText = Field(
        default_factory=lambda: MemoryToolText.model_validate(_tool_default("write")),
        title="쓰기 도구",
        description="기록을 남기거나 고치는 도구입니다.",
        json_schema_extra={"default": _tool_default("write"), **x_ui(tier="advanced")},
    )
    delete: MemoryToolText = Field(
        default_factory=lambda: MemoryToolText.model_validate(_tool_default("delete")),
        title="지우기 도구",
        description="기록을 지우는 도구입니다. 사람은 화면에서 되돌릴 수 있습니다.",
        json_schema_extra={"default": _tool_default("delete"), **x_ui(tier="advanced")},
    )


class MemoryAccessConfig(DefinitionModel):
    """에이전트에게 공유 메모리를 줍니다. 범위마다 읽기·검색·쓰기·지우기 권한을 정합니다."""

    # 리소스 종류 `memory`의 config(그 디스크립터의 설정 스키마가 이 모델의 JSON Schema).
    # 같은 범위 종류가 여러 첨부에 있으면 가까운 층이 이긴다(공급자가 판단, design §5.7R.1.3).

    model_config = ConfigDict(title="메모리 접근")

    scopes: list[MemoryScopeAccess] = Field(
        default_factory=list,
        title="범위별 권한",
        description="에이전트가 쓸 범위와 그 범위에서 허용할 일입니다. 없는 범위는 쓸 수 없습니다.",
        json_schema_extra={
            "default": [],
            **x_ui(tier="basic", when="에이전트가 볼 수 있는 기록의 범위를 정할 때 더하세요."),
        },
    )
    default_scope: Slug | None = Field(
        default=None,
        title="기본 범위",
        description="도구를 부를 때 범위를 적지 않으면 쓰는 범위입니다. 비우면 첫 범위입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="에이전트가 주로 쓰는 범위가 첫 범위가 아닐 때 고르세요.",
            example="notes",
            widget="memory-scope-kind",
        ),
    )
    result_header: str = Field(
        default=memory_access_defaults()["result_header"],
        title="결과 머리 줄",
        description=(
            "읽은 기록 앞에 붙는 줄입니다. {scope_label}, {key}, {version}, {author}, "
            "{updated_at}를 쓸 수 있습니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="에이전트가 기록을 지시로 오해할 때 문구를 바꾸세요.",
        ),
    )
    max_result_chars: int = Field(
        default=memory_access_defaults()["max_result_chars"],
        ge=1,
        title="결과 최대 글자 수",
        description="도구 결과 하나에 담을 최대 글자 수입니다. 넘으면 잘라서 줍니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="긴 기록이 잘리거나 토큰을 너무 많이 쓸 때 바꾸세요.",
            unit="자",
        ),
    )
    tools: MemoryTools = Field(
        default_factory=MemoryTools,
        title="도구 이름과 설명",
        description="에이전트에게 보이는 도구 이름과 설명입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


class MemoryRetentionRule(DefinitionModel):
    """조건에 맞는 오래된 기록을 보관하거나 지우는 규칙입니다. 고정한 기록은 건드리지 않습니다."""

    # 판단 대상(subject)은 design §5.7R.1.4: scope{kind,id}·key·tags·pinned·archived·bytes·
    # version·age_days·idle_days·last_read_days·author_kind·created_by·updated_by. 여러 규칙이
    # 맞으면 선언 순서의 첫 규칙. 적용 결과는 버전(쓴 주체 system, 표시 = 규칙 id)으로 남는다.

    model_config = ConfigDict(title="정리 규칙")

    id: Slug = Field(
        title="규칙 id",
        description="규칙을 가리키는 고유 이름입니다. 정리 기록에 남습니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="규칙을 새로 만들 때 알아보기 쉬운 이름을 적으세요.",
            example="stale-temp",
        ),
    )
    when: ConditionSpec = Field(
        title="정리할 기록 조건",
        description="이 조건에 맞는 기록을 정리합니다. 예: 태그가 임시이고 30일 넘게 안 쓴 기록.",
        # 필드 라벨이 참조 모델 제목과 같으면 생성기가 라벨을 빼므로 다른 문구로 둔다.
        json_schema_extra=x_ui(tier="basic", when="정리할 기록을 고르는 기준을 바꿀 때 고치세요."),
    )
    action: MemoryRetentionAction = Field(
        default="archive",
        title="동작",
        description="맞는 기록을 보관할지 지울지 고릅니다. 둘 다 화면에서 되돌릴 수 있습니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="보관 대신 지우고 싶을 때 바꾸세요.",
            enum_labels={"archive": "보관", "delete": "지우기"},
        ),
    )
    description: str = Field(
        default="",
        title="설명",
        description="규칙을 만든 까닭을 적습니다. 화면에만 보입니다.",
        json_schema_extra=x_ui(tier="advanced", example="한 달 지난 임시 기록 보관"),
    )


class MemoryRetentionSettings(DefinitionModel):
    """오래된 기록을 정리하는 규칙 묶음입니다. 비어 있으면 아무것도 자동으로 정리하지 않습니다."""

    model_config = ConfigDict(title="정리")

    rules: list[MemoryRetentionRule] = Field(
        default_factory=list,
        title="정리 규칙",
        description="위에서부터 처음 맞는 규칙 하나를 씁니다.",
        json_schema_extra={
            "default": [],
            **x_ui(tier="basic", when="쌓인 기록을 자동으로 정리하고 싶을 때 더하세요."),
        },
    )


class MemorySettings(DefinitionModel):
    """공유 메모리의 범위 종류, 비밀 처리, 버전 보관, 정리 규칙을 정합니다."""

    # 워크스페이스 설정의 memory 섹션(메모리 모듈이 소유, 공통 설정 모델에는 필드 없음).
    # 범위 종류 병합: 패키지 기본(include_default_scope_kinds일 때) → 플러그인 → 사용자. 같은 id면
    # 통째로 바꾸고 null이면 지운다. 저장·전송은 model_dump(exclude_unset=True)(생략 = 기본값).

    model_config = ConfigDict(title="메모리")

    include_default_scope_kinds: bool = Field(
        default=True,
        title="기본 범위 종류 사용",
        description=(
            "패키지가 주는 기본 범위 종류를 목록에 넣습니다. 꺼도 직접 만든 범위는 남습니다."
        ),
        json_schema_extra=x_ui(
            tier="basic", when="기본 범위 대신 내가 만든 범위만 쓰고 싶을 때 끄세요."
        ),
    )
    scope_kinds: dict[str, MemoryScopeKindSpec | None] = Field(
        default_factory=dict,
        title="범위 종류",
        description="범위 종류 id마다 이름과 나누는 값을 둡니다. 같은 id면 바꾸고, 비우면 끕니다.",
        json_schema_extra={
            "default": {},
            **x_ui(tier="basic", when="범위를 더하거나 기본 범위를 바꾸고 싶을 때 고치세요."),
        },
    )
    secrets: MemorySecretPolicy = Field(
        default="reject",
        title="비밀 값 처리",
        description="기록에 비밀로 보이는 값이 있을 때 쓰기를 거부할지, 가리고 저장할지 고릅니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="가린 채로라도 기록을 남기고 싶을 때 바꾸세요.",
            enum_labels={"reject": "거부", "redact": "가리고 저장"},
        ),
    )
    max_versions_per_entry: int = Field(
        default=50,
        ge=1,
        title="기록당 버전 보관 수",
        description="한 기록의 옛 버전을 몇 개까지 남길지 정합니다. 넘으면 오래된 것부터 지웁니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="저장 공간을 줄이거나 기록을 더 오래 남기고 싶을 때 바꾸세요."
        ),
    )
    retention: MemoryRetentionSettings = Field(
        default_factory=MemoryRetentionSettings,
        title="기록 정리",
        description="오래된 기록을 보관하거나 지우는 규칙입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="쌓인 기록을 자동으로 정리하고 싶을 때 고치세요."
        ),
    )
