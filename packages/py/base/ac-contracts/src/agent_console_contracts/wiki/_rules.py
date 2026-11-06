"""위키 사용자 데이터: 위키 `WikiDefinition`·위키 규칙 `WikiRulesDefinition`·문법 `WikiSyntax`·
설정 섹션 `wiki`(`WikiSettings`)·리소스 `wiki`의 접근 설정(`WikiAccessConfig`). 모두 모르는 키를
보존한다.

모델 docstring과 필드 설명은 폼의 문구라 사용자 말로 쓰고, 개발자용 설명은 `#` 주석에 둔다
(설정 폼 도움말 린트 `schema-help-lint`가 이 스키마를 검사한다).

위키 이름·페이지 경로·링크 패턴·머리말 키·태그·규칙 id·도구 이름·폴더 이름은 전부 데이터다. 계약은
아무 이름도 모른다. 코드 개념은 머리말 역할 셋(`KnownWikiFrontMatterRoles`)·기본 점검 셋
(`KnownWikiLintCodes`)·링크 대상 찾기 넷(`KnownWikiResolvers`)뿐이다(design §7R.1).

문법 키를 생략하면(None) 위키 규칙 → 사용자 설정 `wiki.syntax` → 패키지 기본 문법 순으로 따른다
(design §7R.1.3). 그래서 문법 모델의 키 기본값은 모두 None이다(빈 목록 = "이 층에서는 없음").
"""

import json
from functools import cache
from importlib.resources import files
from typing import Any, Final, Literal

from pydantic import ConfigDict, Field

from agent_console_contracts._base import DefinitionModel, JsonObject, NonEmptyStr, Slug
from agent_console_contracts.common import JsonPointer, KnownUiWidgets, x_ui
from agent_console_contracts.definitions import IssueSeverity
from agent_console_contracts.runs import ConditionItem, ConditionSpec

_DEFAULTS_FILE = "wiki_access_defaults.json"
_ID_DESCRIPTION = "가리킬 때 쓰는 고유 이름입니다. 영문·숫자·-·_만 씁니다."
_SEVERITY_LABELS = {"error": "오류", "warning": "경고", "info": "정보"}

type WikiSecretScanMode = Literal["off", "warn", "reject"]
"""페이지 본문 비밀 의심 검사(고정 어휘): off = 검사 안 함, warn = 저장하고 알림, reject = 거부."""

WikiAccessOp = Literal["read", "search", "list", "links", "write", "move", "delete"]
"""위키별 허용 동작(고정 어휘 — 도구 처리 코드가 아는 동작). 도구 하나가 동작 하나다."""

_ACCESS_LABELS = {
    "read": "읽기",
    "search": "검색",
    "list": "목록",
    "links": "링크 보기",
    "write": "쓰기",
    "move": "옮기기",
    "delete": "지우기",
}
_ACCESS_TONES = {"delete": "danger", "move": "warning"}
_SECRET_LABELS = {"off": "검사 안 함", "warn": "알리고 저장", "reject": "저장 거부"}
_ACTION_LABELS = {"reject": "거부", "warn": "경고만"}
_ACTION_TONES = {"reject": "danger", "warn": "warning"}

WIKI_LINK_INSERT_VARIABLES: Final[tuple[str, ...]] = ("target", "label", "relative_path")
"""링크 삽입 틀(`WikiLinkRule.insert`)이 쓸 수 있는 변수 이름. 서버가 채운다(`POST …/link-text`)."""

WIKI_TEMPLATE_BUILTIN_VARIABLES: Final[tuple[str, ...]] = ("title", "slug", "date")
"""페이지 틀(경로 틀·본문)에서 서버가 채우는 변수 이름. 그 밖의 이름은 틀의 `variables` 선언."""

WIKI_PATH_HINT_VARIABLES: Final[tuple[str, ...]] = ("pages_dir", "wiki", "wiki_name")
"""접근 설정 `path_hint`가 쓸 수 있는 변수 이름."""

WIKI_RESULT_HEADER_VARIABLES: Final[tuple[str, ...]] = ("wiki", "path", "updated_at", "author")
"""접근 설정 `result_header`가 쓸 수 있는 변수 이름."""

_VARIABLE_HELP = {
    "target": "링크 대상(페이지 경로)",
    "label": "링크 글자(비우면 대상 페이지 제목)",
    "relative_path": "지금 페이지에서 대상 파일까지의 상대 경로",
    "title": "새 페이지 제목",
    "slug": "제목에서 만든 경로 이름",
    "date": "오늘 날짜(YYYY-MM-DD)",
    "pages_dir": "위키 페이지 폴더",
    "wiki": "위키 id",
    "wiki_name": "위키 이름",
    "path": "페이지 경로",
    "updated_at": "마지막으로 고친 때",
    "author": "마지막으로 쓴 쪽",
}


def _variables(names: tuple[str, ...]) -> list[dict[str, str]]:
    return [{"name": n, "description": _VARIABLE_HELP[n]} for n in names]


WIKI_WRITE_SUBJECT_PATHS: Final[tuple[str, ...]] = (
    "/change/op",
    "/change/from",
    "/change/to",
    "/author/kind",
    "/author/agent_id",
    "/author/graph_id",
    "/author/run_id",
    "/author/node_id",
    "/page/path",
    "/page/title",
    "/page/tags",
    "/page/aliases",
    "/page/front_matter",
    "/page/bytes",
    "/page/links_out",
    "/page/broken_links",
    "/before",
    "/before/title",
    "/before/tags",
)
"""쓰기 규칙 조건(`when`·`require`)이 볼 수 있는 판단 대상 경로 제안(스키마 `examples`,
화면 콤보박스).

판단 대상 모양(design §7R.1.1): `{change: {op, from?, to?}, author: {kind, agent_id?, graph_id?,
run_id?, node_id?}, page: {path, title, tags, aliases, front_matter, bytes, links_out,
broken_links}, before: 같은 모양 | null}`. 머리말 값은 `/page/front_matter/<키>`로 본다. 제안일 뿐
다른 경로도 쓸 수 있다(`ac-wiki` 테스트가 최상위 키마다 경로가 있는지 본다)."""

WIKI_LINT_SUBJECT_PATHS: Final[tuple[str, ...]] = (
    "/path",
    "/title",
    "/tags",
    "/front_matter",
    "/bytes",
    "/age_days",
    "/idle_days",
    "/backlinks",
    "/links_out",
    "/broken_links",
    "/updated_by_kind",
)
"""점검 규칙 조건이 볼 수 있는 판단 대상 경로 제안(design §7R.1.1 점검 판단 대상)."""


@cache
def wiki_access_defaults() -> dict[str, Any]:
    """접근 설정 기본값 데이터 원본(`data/wiki_access_defaults.json`).

    반환: `{version, tools: {<동작>: {name, description}}, result_header, path_hint,
    max_result_chars}`. 같은 객체를 돌려주므로 고치지 말고 복사해 쓴다.
    """
    raw = files("agent_console_contracts").joinpath("data", _DEFAULTS_FILE).read_text("utf-8")
    data: dict[str, Any] = json.loads(raw)
    return data


def _tool_default(op: str) -> dict[str, Any]:
    return dict(wiki_access_defaults()["tools"][op])


def _default_access() -> list[WikiAccessOp]:
    return ["read", "search", "list", "links"]


def _default_secret_scan() -> dict[str, WikiSecretScanMode]:
    # 0.14.1: system(wiki-update 노드 등 앱이 대신 쓰는 쪽)도 reject — 에이전트 출력을 노드로 옮겨
    # 쓸 때 에이전트가 직접 쓸 때보다 느슨해지지 않게 한다.
    return {"user": "warn", "agent": "reject", "system": "reject"}


# ---------------------------------------------------------------- 문법(syntax)


class WikiSchemeTarget(DefinitionModel):
    """링크 스킴이 가리킬 화면입니다. 화면 역할과 항목 id로 정합니다."""

    # 공통 `LabelDisplayTarget`과 같은 모양(웹이 같은 함수로 푼다). 폼 도움말 린트를 받는 정의
    # 데이터라 DefinitionModel로 따로 둔다(design §7R.1.3 `[7R.3 구현]`).

    model_config = ConfigDict(title="열 화면")

    role: NonEmptyStr = Field(
        title="화면 역할",
        description="열 화면의 역할 이름입니다. 앱 화면 목록이 이 이름으로 화면을 찾습니다.",
        json_schema_extra=x_ui(
            tier="basic", when="링크가 다른 화면을 열게 하고 싶을 때 적으세요.", example="runs"
        ),
    )
    id_from: NonEmptyStr = Field(
        default="value",
        title="항목 id",
        description="화면의 항목 id로 쓸 값입니다. value는 링크에서 접두를 뺀 나머지입니다.",
        json_schema_extra=x_ui(tier="advanced", example="value"),
    )
    query: str | None = Field(
        default=None,
        title="추가 질의",
        description="화면에 넘길 추가 값 틀입니다. 중괄호 value를 링크 값으로 바꿉니다.",
        json_schema_extra=x_ui(tier="advanced", example="tab=events"),
    )


class WikiScheme(DefinitionModel):
    """페이지가 아니라 다른 화면으로 가는 링크 하나입니다(예: 실행 링크)."""

    model_config = ConfigDict(title="링크 스킴")

    prefix: NonEmptyStr = Field(
        title="접두",
        description="링크 대상이 이 글자로 시작하면 페이지가 아니라 다른 화면으로 갑니다.",
        json_schema_extra=x_ui(
            tier="basic", when="링크로 다른 화면을 열고 싶을 때 적으세요.", example="run:"
        ),
    )
    target: WikiSchemeTarget = Field(
        title="열 화면 정하기",
        description="그 링크를 누르면 열 화면입니다.",
        json_schema_extra=x_ui(tier="basic", when="열 화면을 바꾸고 싶을 때 고치세요."),
    )


class WikiLinkRule(DefinitionModel):
    """링크를 찾는 규칙 하나입니다. 패턴으로 찾거나 마크다운 링크를 읽습니다."""

    # kind는 열린 문자열(알려진 값 KnownWikiLinkKinds: pattern·markdown). 모르는 값은 ac-wiki가
    # 이슈를 내고 건너뛴다. resolve 값은 KnownWikiResolvers 중에서(모르는 값은 이슈).

    model_config = ConfigDict(title="링크 규칙")

    id: Slug = Field(
        title="id",
        description=_ID_DESCRIPTION,
        json_schema_extra=x_ui(
            tier="basic", when="규칙을 새로 더할 때 한 번 정하세요.", example="wikilink", order=1
        ),
    )
    kind: NonEmptyStr = Field(
        title="찾는 방법",
        description=(
            "pattern은 정규식으로 찾고, markdown은 마크다운 링크 중 페이지 파일을 읽습니다."
        ),
        json_schema_extra=x_ui(
            tier="basic", when="다른 방식으로 링크를 찾고 싶을 때 바꾸세요.", example="pattern"
        ),
    )
    pattern: str | None = Field(
        default=None,
        title="패턴",
        description="링크를 찾는 정규식입니다. target 묶음이 대상, label·anchor 묶음은 선택입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="링크 모양을 바꾸고 싶을 때 고치세요(예: 겹괄호 대신 다른 괄호).",
            example=r"\(\((?P<target>[^)]+)\)\)",
            widget=KnownUiWidgets.REGEX,
        ),
    )
    insert: str | None = Field(
        default=None,
        title="링크 넣기 틀",
        description=(
            "편집기의 링크 넣기가 만드는 글자 틀입니다. 비우면 이 규칙으로는 넣지 않습니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="링크 넣기 버튼이 만드는 모양을 바꾸고 싶을 때 고치세요.",
            example="[[{target}|{label}]]",
            widget=KnownUiWidgets.TEMPLATE_TEXT,
            variables=_variables(WIKI_LINK_INSERT_VARIABLES),
        ),
    )
    resolve: list[str] = Field(
        default_factory=list,
        title="대상 찾는 순서",
        description=(
            "링크 대상을 무엇으로 찾을지 순서입니다(path 경로, title 제목, alias 별칭, "
            "relative_path 상대 경로). 비우면 찾지 않습니다."
        ),
        json_schema_extra={
            "default": [],
            **x_ui(
                tier="basic",
                when="제목이나 별칭으로도 링크가 이어지게 하고 싶을 때 고치세요.",
                example=["path", "title", "alias"],
            ),
        },
    )


class WikiFrontMatter(DefinitionModel):
    """페이지 머리말(맨 위 YAML)을 읽는 규칙입니다."""

    model_config = ConfigDict(title="머리말")

    delimiter: str | None = Field(
        default=None,
        title="구분 줄",
        description="머리말 앞뒤에 두는 줄입니다. 비우면 앱 설정이나 기본값을 따릅니다.",
        json_schema_extra=x_ui(tier="advanced", example="---"),
    )
    roles: dict[str, str] | None = Field(
        default=None,
        title="키 역할",
        description="역할(title 제목, tags 태그, aliases 별칭) → 머리말 키 이름입니다.",
        json_schema_extra=x_ui(
            tier="advanced", example={"title": "제목", "tags": "분류", "aliases": "별칭"}
        ),
    )


class WikiLintDefaults(DefinitionModel):
    """기본 점검(끊긴 링크·고아 페이지·제목 겹침)을 켜고 끄는 규칙입니다."""

    model_config = ConfigDict(title="기본 점검")

    builtin: dict[str, IssueSeverity | None] | None = Field(
        default=None,
        title="점검 심각도",
        description=(
            "점검 이름(broken_link, orphan, duplicate_title) → 심각도입니다. 비운 값은 끕니다."
        ),
        json_schema_extra=x_ui(tier="advanced", example={"broken_link": "warning", "orphan": None}),
    )
    write_rules: bool | None = Field(
        default=None,
        title="쓰기 규칙 다시 보기",
        description="켜면 점검할 때 기존 페이지에도 쓰기 규칙을 돌려 어긋난 곳을 보입니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="직접 고친 파일의 규칙 위반을 보고 싶지 않으면 끄세요."
        ),
    )
    orphan_ignore: list[str] | None = Field(
        default=None,
        title="고아 점검 제외",
        description=(
            "고아 페이지 점검에서 뺄 경로 모양입니다(예: archive/**). 첫 페이지는 늘 뺍니다."
        ),
        json_schema_extra=x_ui(tier="advanced", example=["archive/**"], widget=KnownUiWidgets.GLOB),
    )


class WikiSyntax(DefinitionModel):
    """링크·머리말·제목을 페이지에서 읽는 규칙입니다.

    비운 항목은 앱 설정이나 기본 규칙을 따릅니다.
    """

    # 병합: 패키지 기본(include_default_syntax) → 사용자 설정 wiki.syntax → 위키 규칙 syntax(규칙
    # 순서). 첫 단계 키 단위 덮어쓰기, 그 아래는 통째로 바꾼다. 빈 목록 = "이 층에서는 없음".

    model_config = ConfigDict(title="위키 문법")

    links: list[WikiLinkRule] | None = Field(
        default=None,
        title="링크 규칙",
        description="페이지 사이 링크를 찾는 규칙입니다. 비운 목록이면 링크를 찾지 않습니다.",
        json_schema_extra=x_ui(tier="advanced", item_title="/id", order=1),
    )
    front_matter: WikiFrontMatter | None = Field(
        default=None,
        title="머리말 읽기",
        description="페이지 맨 위 머리말을 읽는 규칙입니다.",
        json_schema_extra=x_ui(tier="advanced", order=2),
    )
    title_sources: list[str] | None = Field(
        default=None,
        title="제목 출처 순서",
        description=(
            "제목을 어디서 읽을지 순서입니다(front_matter 머리말, first_heading 첫 제목, "
            "file_name 파일 이름)."
        ),
        json_schema_extra=x_ui(
            tier="advanced", example=["front_matter", "first_heading", "file_name"]
        ),
    )
    page_extensions: list[str] | None = Field(
        default=None,
        title="페이지 확장자",
        description="이 확장자의 파일을 페이지로 봅니다.",
        json_schema_extra=x_ui(tier="advanced", example=[".md"]),
    )
    case_insensitive: bool | None = Field(
        default=None,
        title="대소문자 무시",
        description="켜면 경로·제목·별칭을 비교할 때 대소문자를 가리지 않습니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    schemes: list[WikiScheme] | None = Field(
        default=None,
        title="링크 스킴",
        description="페이지가 아니라 다른 화면으로 가는 링크 규칙입니다(예: run: 으로 시작).",
        json_schema_extra=x_ui(tier="advanced", item_title="/prefix"),
    )
    lint: WikiLintDefaults | None = Field(
        default=None,
        title="기본 점검 설정",
        description="끊긴 링크·고아 페이지·제목 겹침 점검을 켜고 끄며 심각도를 정합니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


# ---------------------------------------------------------------- 쓰기·점검 규칙 조건


class WikiWriteConditionItem(ConditionItem):
    """조건 하나입니다. 쓰기의 '볼 값'을 '비교 방법'으로 '비교할 값'과 견줍니다."""

    # 연결 조건 항목과 같은 모양이고 path의 설명·제안 경로만 쓰기 판단 대상으로 바꾼다.

    model_config = ConfigDict(title="쓰기 조건 하나")

    path: JsonPointer = Field(
        title="볼 값",
        description=(
            "쓰기에서 비교할 값의 위치입니다(예: /change/op 동작, /author/kind 쓴 쪽, "
            "/page/tags 태그)."
        ),
        json_schema_extra={
            "examples": list(WIKI_WRITE_SUBJECT_PATHS),
            **x_ui(
                tier="basic",
                when="쓴 쪽·동작·태그 같은 다른 값을 보고 판단하고 싶을 때 바꾸세요.",
                example="/author/kind",
            ),
        },
    )


class WikiWriteCondition(ConditionSpec):
    """쓰기 규칙을 걸 쓰기를 고르는 조건입니다. 비우면 모든 쓰기에 겁니다."""

    model_config = ConfigDict(title="쓰기 조건")

    all: list[WikiWriteConditionItem] | None = Field(  # type: ignore[assignment]
        default=None,
        title="모두 참",
        description="여기 적은 조건이 모두 맞는 쓰기에만 겁니다.",
        json_schema_extra=x_ui(
            tier="basic", when="여러 조건이 모두 맞을 때만 걸고 싶을 때 더하세요."
        ),
    )
    any: list[WikiWriteConditionItem] | None = Field(  # type: ignore[assignment]
        default=None,
        title="하나라도 참",
        description="여기 적은 조건 중 하나만 맞아도 겁니다.",
        json_schema_extra=x_ui(tier="basic", when="조건 중 하나만 맞아도 걸고 싶을 때 더하세요."),
    )


class WikiLintConditionItem(ConditionItem):
    """조건 하나입니다. 페이지의 '볼 값'을 '비교 방법'으로 '비교할 값'과 견줍니다."""

    model_config = ConfigDict(title="점검 조건 하나")

    path: JsonPointer = Field(
        title="볼 값",
        description=(
            "페이지에서 비교할 값의 위치입니다(예: /idle_days 마지막 수정 뒤 지난 날, "
            "/backlinks 들어오는 링크 수)."
        ),
        json_schema_extra={
            "examples": list(WIKI_LINT_SUBJECT_PATHS),
            **x_ui(
                tier="basic",
                when="지난 날 수·링크 수 같은 다른 값을 보고 점검하고 싶을 때 바꾸세요.",
                example="/idle_days",
            ),
        },
    )


class WikiLintCondition(ConditionSpec):
    """점검에 걸릴 페이지를 고르는 조건입니다."""

    model_config = ConfigDict(title="점검 조건")

    all: list[WikiLintConditionItem] | None = Field(  # type: ignore[assignment]
        default=None,
        title="모두 참",
        description="여기 적은 조건이 모두 맞는 페이지를 이슈로 보입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="여러 조건이 모두 맞는 페이지만 고르고 싶을 때 더하세요."
        ),
    )
    any: list[WikiLintConditionItem] | None = Field(  # type: ignore[assignment]
        default=None,
        title="하나라도 참",
        description="여기 적은 조건 중 하나만 맞아도 이슈로 보입니다.",
        json_schema_extra=x_ui(tier="basic", when="조건 중 하나만 맞아도 고르고 싶을 때 더하세요."),
    )


# ---------------------------------------------------------------- 위키 규칙 wiki-rules


class WikiContentRef(DefinitionModel):
    """정의 파일 옆 본문 폴더의 파일 하나입니다."""

    model_config = ConfigDict(title="본문 파일")

    file: NonEmptyStr = Field(
        title="파일",
        description="본문 폴더 안의 상대 경로입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="다른 본문 파일을 쓰고 싶을 때 바꾸세요.", example="instructions.md"
        ),
    )


class WikiTemplateVariable(DefinitionModel):
    """페이지 틀에서 쓰는 변수 하나입니다. 새 페이지 대화상자가 이 칸을 보입니다."""

    model_config = ConfigDict(title="틀 변수")

    name: NonEmptyStr = Field(
        title="이름",
        description="틀에서 중괄호로 감싸 쓰는 이름입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="틀에 새 빈칸을 더할 때 정하세요.", example="owner", order=1
        ),
    )
    title: str | None = Field(
        default=None,
        title="표시 이름",
        description="대화상자의 칸 이름입니다. 비우면 이름을 보입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="칸 이름을 알아보기 쉽게 하고 싶을 때 적으세요.", example="담당"
        ),
    )
    description: str | None = Field(
        default=None,
        title="설명",
        description="칸 아래 보일 도움말입니다.",
        json_schema_extra=x_ui(tier="advanced", example="결정을 맡은 사람"),
    )
    example: str | None = Field(
        default=None,
        title="예시",
        description="빈칸에 흐리게 보일 예시 값입니다.",
        json_schema_extra=x_ui(tier="advanced", example="홍길동"),
    )
    builtin: bool = Field(
        default=False,
        title="앱이 채움",
        description="앱이 채우는 변수인지입니다. 앱이 보기에서만 켭니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


class WikiPageTemplate(DefinitionModel):
    """페이지 틀 하나입니다. 새 페이지를 만들 때 본문 뼈대로 씁니다."""

    model_config = ConfigDict(title="페이지 틀")

    id: Slug = Field(
        title="id",
        description=_ID_DESCRIPTION,
        json_schema_extra=x_ui(
            tier="basic", when="틀을 새로 더할 때 한 번 정하세요.", example="decision", order=1
        ),
    )
    title: str | None = Field(
        default=None,
        title="표시 이름",
        description="새 페이지 대화상자에 보일 틀 이름입니다. 비우면 id를 보입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="틀 이름을 알아보기 쉽게 바꾸고 싶을 때 적으세요.", example="결정"
        ),
    )
    file: NonEmptyStr = Field(
        title="틀 파일",
        description="본문 폴더 안의 틀 파일입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="다른 틀 파일을 쓰고 싶을 때 바꾸세요.",
            example="templates/decision.md",
        ),
    )
    path: str | None = Field(
        default=None,
        title="경로 틀",
        description="새 페이지 경로 틀입니다. 중괄호 slug는 제목에서 만든 이름입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="이 틀로 만든 페이지를 정한 폴더에 두고 싶을 때 적으세요.",
            example="decisions/{slug}",
            widget=KnownUiWidgets.TEMPLATE_TEXT,
            variables=[
                *_variables(WIKI_TEMPLATE_BUILTIN_VARIABLES),
                {"name": "…", "description": "같은 틀의 변수에 선언한 이름"},
            ],
        ),
    )
    variables: list[WikiTemplateVariable] = Field(
        default_factory=list,
        title="변수",
        description="틀에 쓰는 빈칸입니다. 제목·경로 이름·날짜는 앱이 채우므로 적지 않아도 됩니다.",
        json_schema_extra={
            "default": [],
            **x_ui(
                tier="advanced",
                when="새 페이지를 만들 때 사람이 채울 칸을 더하고 싶을 때 적으세요.",
                item_title="/name",
            ),
        },
    )


class WikiWriteRule(DefinitionModel):
    """쓰기 규칙 하나입니다. 맞는 쓰기를 거부하거나 경고합니다."""

    # 위에서부터 모두 평가한다. reject가 하나라도 있으면 쓰기를 거부한다. action은 열린 문자열
    # (알려진 값 KnownWikiWriteActions: reject·warn) — 모르는 값은 warn으로 읽고 이슈.
    # 판단: applies_to(경로 모양) → when(참이어야 건다) → require(거짓이면 action) ·
    # deny_patterns(본문에 맞는 줄이 있으면 action).

    model_config = ConfigDict(title="쓰기 규칙")

    id: Slug = Field(
        title="id",
        description=_ID_DESCRIPTION,
        json_schema_extra=x_ui(
            tier="basic",
            when="규칙을 새로 더할 때 한 번 정하세요.",
            example="no-temp-notes",
            order=1,
        ),
    )
    applies_to: list[str] = Field(
        default_factory=list,
        title="걸 페이지",
        description="이 경로 모양의 페이지에만 겁니다(예: decisions/**). 비우면 모든 페이지입니다.",
        json_schema_extra={
            "default": [],
            **x_ui(
                tier="basic",
                when="일부 폴더의 페이지에만 규칙을 걸고 싶을 때 적으세요.",
                example=["decisions/**"],
                widget=KnownUiWidgets.GLOB,
            ),
        },
    )
    when: WikiWriteCondition | None = Field(
        default=None,
        title="걸 쓰기",
        description="이 조건이 맞는 쓰기에만 겁니다. 비우면 모든 쓰기입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="에이전트의 쓰기나 지우기에만 걸고 싶을 때 적으세요.",
            widget=KnownUiWidgets.CONDITION,
        ),
    )
    require: WikiWriteCondition | None = Field(
        default=None,
        title="지켜야 할 조건",
        description="이 조건이 맞지 않으면 거부하거나 경고합니다. 예: 머리말에 근거가 있음.",
        json_schema_extra=x_ui(
            tier="basic",
            when="페이지에 꼭 있어야 할 값이 있을 때 적으세요.",
            widget=KnownUiWidgets.CONDITION,
        ),
    )
    deny_patterns: list[str] = Field(
        default_factory=list,
        title="금지 패턴",
        description="본문에 이 정규식에 맞는 줄이 있으면 거부하거나 경고합니다.",
        json_schema_extra={
            "default": [],
            **x_ui(
                tier="basic",
                when="위키에 남기면 안 되는 글(예: 임시 메모)이 있을 때 더하세요.",
                example=[r"(?i)\bTODO\b"],
                widget=KnownUiWidgets.REGEX,
            ),
        },
    )
    action: NonEmptyStr = Field(
        default="reject",
        title="동작",
        description="reject는 쓰기를 거부하고, warn은 쓰고 경고만 보입니다.",
        json_schema_extra={
            "examples": list(_ACTION_LABELS),
            **x_ui(
                tier="basic",
                when="막지 않고 알리기만 하려면 warn으로 바꾸세요.",
                enum_labels=_ACTION_LABELS,
                enum_tones=_ACTION_TONES,
            ),
        },
    )
    message: str = Field(
        default="",
        title="안내 문장",
        description="거부·경고할 때 보일 문장입니다. 에이전트에게도 그대로 전합니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="왜 막혔는지 알기 쉽게 적고 싶을 때 고치세요.",
            example="임시 메모는 위키에 쓰지 않습니다",
        ),
    )


class WikiLintRule(DefinitionModel):
    """점검 규칙 하나입니다. 조건에 맞는 페이지를 점검 탭에 이슈로 보입니다."""

    model_config = ConfigDict(title="점검 규칙")

    id: Slug = Field(
        title="id",
        description=_ID_DESCRIPTION,
        json_schema_extra=x_ui(
            tier="basic", when="규칙을 새로 더할 때 한 번 정하세요.", example="stale", order=1
        ),
    )
    when: WikiLintCondition = Field(
        title="걸릴 페이지",
        description="이 조건에 맞는 페이지를 이슈로 보입니다. 예: 90일 넘게 고치지 않음.",
        json_schema_extra=x_ui(
            tier="basic",
            when="점검할 페이지를 고르는 기준을 바꿀 때 고치세요.",
            widget=KnownUiWidgets.CONDITION,
        ),
    )
    severity: IssueSeverity = Field(
        default="info",
        title="심각도",
        description="이슈의 심각도입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="더 눈에 띄게 하려면 경고나 오류로 바꾸세요.",
            enum_labels=_SEVERITY_LABELS,
        ),
    )
    message: str = Field(
        default="",
        title="안내 문장",
        description="이슈에 보일 문장입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="무엇을 고치면 되는지 알기 쉽게 적고 싶을 때 고치세요.",
            example="90일 넘게 고치지 않은 페이지",
        ),
    )


class _WikiCommon(DefinitionModel):
    """위키와 위키 규칙의 공통 필드(내부 베이스, 스키마에 따로 나오지 않는다)."""

    kind: NonEmptyStr = Field(
        title="종류",
        description="정의 종류 이름입니다. 직접 바꾸지 않습니다.",
        json_schema_extra=x_ui(tier="advanced", example="wiki"),
    )
    id: Slug = Field(
        title="id", description=_ID_DESCRIPTION, json_schema_extra=x_ui(tier="advanced")
    )
    schema_version: int = Field(
        default=1,
        title="형식 버전",
        description="파일 형식 번호입니다. 직접 바꾸지 않습니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    name: NonEmptyStr = Field(
        title="이름",
        description="목록에 보일 이름입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="목록에서 알아보기 쉬운 이름으로 바꾸고 싶을 때 바꾸세요.",
            example="프로젝트 노트",
        ),
    )
    description: str = Field(
        default="",
        title="설명",
        description="무엇을 위한 것인지 적습니다. 목록에 함께 보입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="목록에서 쓰임새를 알리고 싶을 때 적으세요.", example="결정과 배경"
        ),
    )
    attributes: JsonObject = Field(
        default_factory=dict,
        title="기타 속성",
        description="다른 도구가 읽는 자유 속성입니다. 보통은 비워 둡니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


class WikiRulesDefinition(_WikiCommon):
    """위키 규칙입니다. 에이전트 지침, 쓰기·점검 규칙, 페이지 틀, 문법을 담습니다."""

    # 정의 종류 이름(kind)은 mod-wiki 설치자 데이터(기본 wiki-rules). 라이브러리·프로젝트 공간,
    # 옮길 수 있음, 본문 여러 파일(지침·페이지 틀).

    model_config = ConfigDict(title="위키 규칙")

    instructions: WikiContentRef | None = Field(
        default=None,
        title="지침 본문",
        description="위키 도구를 받는 에이전트에게 지침으로 주는 본문 파일입니다. 비우면 없습니다.",
        json_schema_extra=x_ui(
            tier="basic", when="에이전트에게 무엇을 기록하고 뺄지 알려 주고 싶을 때 정하세요."
        ),
    )
    page_templates: list[WikiPageTemplate] = Field(
        default_factory=list,
        title="페이지 틀",
        description="새 페이지를 만들 때 고를 수 있는 본문 뼈대입니다.",
        json_schema_extra={
            "default": [],
            **x_ui(
                tier="basic",
                when="같은 모양의 페이지를 자주 만들 때 더하세요.",
                item_title="/id",
            ),
        },
    )
    write_rules: list[WikiWriteRule] = Field(
        default_factory=list,
        title="쓰기 규칙",
        description="위에서부터 모두 봅니다. 거부하는 규칙이 하나라도 맞으면 쓰지 않습니다.",
        json_schema_extra={
            "default": [],
            **x_ui(
                tier="basic",
                when="위키에 남기면 안 되는 것을 막고 싶을 때 더하세요.",
                item_title="/id",
            ),
        },
    )
    lint_rules: list[WikiLintRule] = Field(
        default_factory=list,
        title="점검 규칙",
        description="조건에 맞는 페이지를 점검 탭에 보입니다.",
        json_schema_extra={
            "default": [],
            **x_ui(
                tier="basic",
                when="오래된 페이지 같은 것을 찾고 싶을 때 더하세요.",
                item_title="/id",
            ),
        },
    )
    syntax: WikiSyntax | None = Field(
        default=None,
        title="문법",
        description="이 규칙을 쓰는 위키의 링크·머리말 문법입니다. 비우면 앱 설정을 따릅니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    content: WikiContentRef | None = Field(
        default=None,
        title="본문",
        description="본문 폴더의 대표 파일입니다. 앱이 채웁니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


class WikiDefinition(_WikiCommon):
    """위키입니다. 이름, 첫 페이지, 쓰는 위키 규칙을 담습니다. 페이지는 폴더의 파일입니다."""

    # 정의 종류 이름(kind)은 mod-wiki 설치자 데이터(기본 wiki). 프로젝트·단독 공간에만
    # (library=False), 옮길 수 있음. 참조 추출: rules → ("wiki-rules" 종류, id).

    model_config = ConfigDict(title="위키")

    home: str | None = Field(
        default=None,
        title="첫 페이지",
        description="위키를 열면 먼저 보일 페이지 경로입니다(확장자 없이). 비우면 목록을 엽니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="위키를 열 때 보일 페이지를 정하고 싶을 때 적으세요.",
            example="index",
        ),
    )
    rules: list[Slug] = Field(
        default_factory=list,
        title="쓰는 위키 규칙",
        description="이 위키에 쓸 위키 규칙입니다. 순서대로 합칩니다. 비우면 규칙이 없습니다.",
        json_schema_extra={
            "default": [],
            **x_ui(
                tier="basic",
                when="기록할 것·뺄 것을 정한 규칙을 붙이고 싶을 때 더하세요.",
                example=["decisions-only"],
                widget=KnownUiWidgets.WIKI_RULE_REFS,
            ),
        },
    )


# ---------------------------------------------------------------- 사용자 설정 섹션 wiki


class WikiWriteCheckSetting(DefinitionModel):
    """설치된 쓰기 검사 하나를 켜고 옵션을 줍니다."""

    model_config = ConfigDict(title="쓰기 검사")

    id: NonEmptyStr = Field(
        title="검사",
        description="설치된 쓰기 검사의 이름입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="다른 쓰기 검사를 쓰고 싶을 때 고르세요.",
            example="front-matter-keys",
        ),
    )
    enabled: bool = Field(
        default=True,
        title="켜기",
        description="끄면 이 검사를 쓰지 않습니다.",
        json_schema_extra=x_ui(tier="basic", when="잠시 이 검사를 쓰지 않으려면 끄세요."),
    )
    options: JsonObject = Field(
        default_factory=dict,
        title="옵션",
        description="검사가 정한 설정입니다(예: 꼭 있어야 할 머리말 키).",
        json_schema_extra=x_ui(tier="advanced", example={"keys": ["source"]}),
    )


class WikiSettings(DefinitionModel):
    """위키의 문법, 비밀 검사, 기록 보관, 검색 방식을 정합니다."""

    # 워크스페이스 설정의 wiki 섹션(mod-wiki가 소유, 공통 설정 모델에는 필드 없음 — 메모리·SDD와
    # 같은 방식). 깨진 부분만 빼고 경고(wiki.settings_invalid), 모르는 키 보존.
    # secret_scan 키 = 쓴 주체 종류(열린 키, 알려진 값 KnownWikiAuthorKinds), 없는 종류는 user 값.

    model_config = ConfigDict(title="위키")

    include_default_syntax: bool = Field(
        default=True,
        title="기본 위키 문법 사용",
        description="앱이 주는 기본 문법(겹대괄호 링크, 상대 경로 링크, 머리말)을 씁니다.",
        json_schema_extra=x_ui(
            tier="basic", when="기본 문법 대신 내가 만든 문법만 쓰고 싶을 때 끄세요."
        ),
    )
    syntax: WikiSyntax | None = Field(
        default=None,
        title="위키 문법",
        description="모든 위키에 쓸 문법입니다. 위키 규칙의 문법이 있으면 그쪽이 먼저입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    secret_scan: dict[str, WikiSecretScanMode] = Field(
        default_factory=_default_secret_scan,
        title="비밀 값 검사",
        description=(
            "쓴 쪽(user 사람, agent 에이전트, system 앱이 대신 씀 등)마다 비밀로 보이는 값을 "
            "어떻게 할지입니다. 없는 쪽은 사람 값을 씁니다."
        ),
        json_schema_extra={
            "default": {"user": "warn", "agent": "reject", "system": "reject"},
            "examples": [
                {"user": "warn", "agent": "reject", "system": "reject", "external": "off"}
            ],
            **x_ui(
                tier="basic",
                when="오탐이 많으면 끄고, 비밀이 섞이면 안 되면 거부로 바꾸세요.",
                enum_labels=_SECRET_LABELS,
            ),
        },
    )
    max_versions_per_page: int = Field(
        default=50,
        ge=1,
        title="페이지당 기록 보관 수",
        description="한 페이지의 옛 버전을 몇 개까지 남길지입니다. 첫 버전은 늘 남깁니다.",
        json_schema_extra=x_ui(
            tier="basic", when="저장 공간을 줄이거나 기록을 더 오래 남기고 싶을 때 바꾸세요."
        ),
    )
    search_backend: str | None = Field(
        default=None,
        title="검색 방식",
        description="설치된 검색 방식의 이름입니다. 비우면 설치할 때 정한 기본값을 씁니다.",
        json_schema_extra=x_ui(tier="advanced", example="scan"),
    )
    write_checks: list[WikiWriteCheckSetting] = Field(
        default_factory=list,
        title="쓰기 검사",
        description="설치된 쓰기 검사 중 켤 것입니다. 위키 규칙과 함께 봅니다.",
        json_schema_extra={"default": [], **x_ui(tier="advanced", item_title="/id")},
    )


# ---------------------------------------------------------------- 리소스 wiki 접근 설정


class WikiToolText(DefinitionModel):
    """에이전트에게 보이는 도구 이름과 설명입니다."""

    model_config = ConfigDict(title="도구 표시")

    name: str = Field(
        pattern=r"^[A-Za-z0-9_-]{1,64}$",
        title="도구 이름",
        description="에이전트가 부르는 이름입니다. 영문·숫자·밑줄·빼기만 씁니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="다른 도구와 이름이 겹치거나 팀 규칙에 맞추고 싶을 때 바꾸세요.",
            example="notes_search",
        ),
    )
    description: str = Field(
        title="도구 설명",
        description="에이전트가 언제 이 도구를 쓸지 판단하는 설명입니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="에이전트가 도구를 너무 자주 쓰거나 안 쓸 때 고치세요.",
            example="프로젝트 위키에서 페이지를 찾습니다.",
        ),
    )


def _tool_field(op: str, title: str, description: str) -> Any:
    return Field(
        default_factory=lambda: WikiToolText.model_validate(_tool_default(op)),
        title=title,
        description=description,
        json_schema_extra={"default": _tool_default(op), **x_ui(tier="advanced")},
    )


class WikiToolNames(DefinitionModel):
    """동작마다 에이전트에게 보이는 도구 이름과 설명입니다. 비우면 기본값을 씁니다."""

    # 동작 이름(WikiAccessOp)은 계약 어휘다. 모델에게 보이는 이름·설명만 데이터이고 기본값은
    # 패키지 데이터(data/wiki_access_defaults.json)에서 온다 — 코드 분기 없음.

    model_config = ConfigDict(title="도구")

    search: WikiToolText = _tool_field("search", "검색 도구", "페이지를 찾는 도구입니다.")
    read: WikiToolText = _tool_field("read", "읽기 도구", "페이지 하나를 읽는 도구입니다.")
    list: WikiToolText = _tool_field("list", "목록 도구", "페이지 목록을 보는 도구입니다.")
    links: WikiToolText = _tool_field(
        "links", "링크 도구", "페이지의 링크와 백링크를 보는 도구입니다."
    )
    write: WikiToolText = _tool_field("write", "쓰기 도구", "페이지를 쓰거나 고치는 도구입니다.")
    move: WikiToolText = _tool_field("move", "옮기기 도구", "페이지 경로를 바꾸는 도구입니다.")
    delete: WikiToolText = _tool_field(
        "delete", "지우기 도구", "페이지를 지우는 도구입니다. 사람은 기록에서 되돌릴 수 있습니다."
    )


class WikiAccessEntry(DefinitionModel):
    """에이전트가 이 위키에서 할 수 있는 일입니다."""

    model_config = ConfigDict(title="위키 권한")

    wiki: Slug = Field(
        title="위키",
        description="권한을 줄 위키입니다. 실행하는 프로젝트의 위키 중에서 고릅니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="에이전트가 쓸 위키를 바꾸고 싶을 때 고르세요.",
            example="project-notes",
            widget=KnownUiWidgets.WIKI_REF,
        ),
    )
    access: list[WikiAccessOp] = Field(
        default_factory=_default_access,
        title="허용할 일",
        description="읽기·검색·목록·링크 보기·쓰기·옮기기·지우기 중 허용할 것입니다.",
        json_schema_extra={
            "default": ["read", "search", "list", "links"],
            "examples": [["read", "search", "write"]],
            **x_ui(
                tier="basic",
                when="에이전트가 위키를 고치게 하려면 쓰기를 더하세요.",
                enum_labels=_ACCESS_LABELS,
                enum_tones=_ACCESS_TONES,
            ),
        },
    )


class WikiAccessConfig(DefinitionModel):
    """에이전트에게 위키를 줍니다. 위키마다 허용할 일과 지침·경로 안내를 정합니다."""

    # 리소스 종류 `wiki`의 config(그 디스크립터의 설정 스키마가 이 모델의 JSON Schema).
    # 같은 위키가 여러 첨부에 있으면 가까운 층의 access가 이긴다(메모리 리소스와 같은 규칙).

    model_config = ConfigDict(title="위키 접근")

    wikis: list[WikiAccessEntry] = Field(
        default_factory=list,
        title="위키별 권한",
        description="에이전트가 쓸 위키와 허용할 일입니다. 없는 위키는 쓸 수 없습니다.",
        json_schema_extra={
            "default": [],
            **x_ui(tier="basic", when="에이전트가 볼 위키를 정할 때 더하세요.", item_title="/wiki"),
        },
    )
    default_wiki: Slug | None = Field(
        default=None,
        title="기본 위키",
        description="도구를 부를 때 위키를 적지 않으면 쓰는 위키입니다. 비우면 첫 위키입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="에이전트가 주로 쓰는 위키가 첫 위키가 아닐 때 고르세요.",
            example="project-notes",
            widget=KnownUiWidgets.WIKI_REF,
        ),
    )
    include_rules_instructions: bool = Field(
        default=True,
        title="규칙 지침 전달",
        description="켜면 위키 규칙의 지침 본문을 에이전트 지침으로 함께 줍니다.",
        json_schema_extra=x_ui(tier="basic", when="지침을 따로 주고 있어 겹친다면 끄세요."),
    )
    path_hint: str = Field(
        default=wiki_access_defaults()["path_hint"],
        title="경로 안내",
        description=(
            "에이전트 지침에 붙는 안내 문장입니다. 중괄호 pages_dir, wiki, wiki_name을 쓸 수 "
            "있습니다. 비우면 없습니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="에이전트가 파일을 직접 고치려 할 때 문구를 바꾸세요.",
            widget=KnownUiWidgets.TEMPLATE_TEXT,
            variables=_variables(WIKI_PATH_HINT_VARIABLES),
        ),
    )
    result_header: str = Field(
        default=wiki_access_defaults()["result_header"],
        title="결과 머리 줄",
        description=(
            "읽은 페이지 앞에 붙는 줄입니다. 중괄호 wiki, path, updated_at, author를 쓸 수 "
            "있습니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="에이전트가 페이지를 지시로 오해할 때 문구를 바꾸세요.",
            widget=KnownUiWidgets.TEMPLATE_TEXT,
            variables=_variables(WIKI_RESULT_HEADER_VARIABLES),
        ),
    )
    max_result_chars: int = Field(
        default=wiki_access_defaults()["max_result_chars"],
        ge=1,
        title="결과 최대 글자 수",
        description="도구 결과 하나에 담을 최대 글자 수입니다. 넘으면 잘라서 줍니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="긴 페이지가 잘리거나 토큰을 너무 많이 쓸 때 바꾸세요.", unit="자"
        ),
    )
    tools: WikiToolNames = Field(
        default_factory=WikiToolNames,
        title="도구 이름과 설명",
        description="에이전트에게 보이는 도구 이름과 설명입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


__all__ = [
    "WIKI_LINK_INSERT_VARIABLES",
    "WIKI_LINT_SUBJECT_PATHS",
    "WIKI_PATH_HINT_VARIABLES",
    "WIKI_RESULT_HEADER_VARIABLES",
    "WIKI_TEMPLATE_BUILTIN_VARIABLES",
    "WIKI_WRITE_SUBJECT_PATHS",
    "WikiAccessConfig",
    "WikiAccessEntry",
    "WikiAccessOp",
    "WikiContentRef",
    "WikiDefinition",
    "WikiFrontMatter",
    "WikiLinkRule",
    "WikiLintCondition",
    "WikiLintConditionItem",
    "WikiLintDefaults",
    "WikiLintRule",
    "WikiPageTemplate",
    "WikiRulesDefinition",
    "WikiScheme",
    "WikiSchemeTarget",
    "WikiSecretScanMode",
    "WikiSettings",
    "WikiSyntax",
    "WikiTemplateVariable",
    "WikiToolNames",
    "WikiToolText",
    "WikiWriteCheckSetting",
    "WikiWriteCondition",
    "WikiWriteConditionItem",
    "WikiWriteRule",
    "wiki_access_defaults",
]
