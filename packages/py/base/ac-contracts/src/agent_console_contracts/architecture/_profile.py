"""구조도 프로필과 사용자 설정(사용자 데이터, 모르는 키 보존).

프로필 = 캔버스·영역·칸·연결·출처별 수집 범위 묶음. 칸·연결·영역·지표·출처 이름은 전부 데이터이고
계약은 아무 이름도 모른다. 조건은 `runs.ConditionSpec`(조건 연산자 확장 지점)을 그대로 쓴다.
값 검사(없는 칸을 가리키는 연결, 중복 id, 모르는 지표 이름 등)는 형식 검증이 아니라 투영
라이브러리의 프로필 검사가 이슈로 알린다. 그래서 id·지표·연결 종류는 열린 문자열이다.

모델 docstring은 설정 폼의 설명이라 사용자 말로 쓰고, 개발자용 설명은 `#` 주석에 둔다.
"""

from typing import Annotated

from pydantic import ConfigDict, Field

from agent_console_contracts._base import DefinitionModel, NonEmptyStr
from agent_console_contracts.common import JsonPointer, x_ui
from agent_console_contracts.runs import ConditionSpec

ArchitecturePoint = Annotated[list[float], Field(min_length=2, max_length=2)]
"""캔버스 좌표 한 점 `[x, y]`(px 단위 숫자)."""

DEFAULT_GROUP_LIMIT = 8
"""묶음을 따로 보일 기본 개수(나머지는 "그 밖 n")."""


class ArchitectureCanvas(DefinitionModel):
    """구조도를 그릴 바탕의 크기입니다. 칸과 연결의 좌표는 이 크기 안의 숫자입니다."""

    model_config = ConfigDict(title="캔버스")

    width: float = Field(
        gt=0,
        title="폭",
        description="바탕의 가로 크기입니다. 칸과 영역이 이 안에 들어가야 합니다.",
        json_schema_extra=x_ui(
            tier="basic", when="칸을 더 놓을 자리가 필요할 때 늘리세요.", example=1520, unit="px"
        ),
    )
    height: float = Field(
        gt=0,
        title="높이",
        description="바탕의 세로 크기입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="칸을 아래로 더 놓고 싶을 때 늘리세요.", example=812, unit="px"
        ),
    )


class ArchitectureZone(DefinitionModel):
    """칸 뒤에 깔리는 영역입니다. 그리기만 하고 누를 수 없습니다(예: 내 PC, 모델 서버)."""

    # x·y는 영역의 왼쪽 위 모서리다(칸은 중심 좌표). style은 그리기 이름(열린 문자열, 화면이 모르면
    # boundary 모양). description은 5.5R.2 화면 명세의 영역 설명 줄(정식 필드).

    model_config = ConfigDict(title="영역")

    id: NonEmptyStr = Field(
        title="영역 id",
        description="영역을 가리키는 고유 이름입니다. 칸의 영역 칸에 이 이름을 적습니다.",
        json_schema_extra=x_ui(
            tier="basic", when="새 영역을 만들 때 한 번 정하세요.", example="local"
        ),
    )
    label: str | None = Field(
        default=None,
        title="제목",
        description="영역 왼쪽 위에 보일 제목입니다. 비우면 제목이 없습니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="영역이 무엇을 뜻하는지 그림에서 바로 보이게 하고 싶을 때 적으세요.",
            example="LOCAL · 사용자 PC",
        ),
    )
    description: str | None = Field(
        default=None,
        title="설명",
        description="제목 아래 한 줄 설명입니다. 길면 말줄임으로 잘립니다.",
        json_schema_extra=x_ui(tier="advanced", example="네트워크로 모델 요청 / 응답"),
    )
    x: float = Field(
        title="왼쪽 위치",
        description="영역 왼쪽 위 모서리의 가로 좌표입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="영역을 옮기고 싶을 때 바꾸세요.", example=10, unit="px"
        ),
    )
    y: float = Field(
        title="위쪽 위치",
        description="영역 왼쪽 위 모서리의 세로 좌표입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="영역을 옮기고 싶을 때 바꾸세요.", example=16, unit="px"
        ),
    )
    w: float = Field(
        gt=0,
        title="폭",
        description="영역의 가로 크기입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="영역이 칸을 다 감싸지 못할 때 늘리세요.", example=1260, unit="px"
        ),
    )
    h: float = Field(
        gt=0,
        title="높이",
        description="영역의 세로 크기입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="영역이 칸을 다 감싸지 못할 때 늘리세요.", example=780, unit="px"
        ),
    )
    style: str | None = Field(
        default=None,
        title="모양",
        description=(
            "영역을 그리는 모양 이름입니다(예: boundary, service, runtime). 모르면 기본 모양."
        ),
        json_schema_extra=x_ui(tier="advanced", example="boundary"),
    )


class ArchitectureDrill(DefinitionModel):
    """칸을 눌러 하위 구조도로 들어갈 때 더할 걸러내기입니다. "
    "묶음 값으로 같은 그림을 다시 그립니다."""

    # filter = 로그 질의 필터 이름(예: thread, scope). value의 {group}은 묶음 값으로 바꾼다.
    # 모르는 필터 이름은 프로필 검사가 이슈로 알린다.

    model_config = ConfigDict(title="하위 구조도")

    filter: NonEmptyStr = Field(
        title="걸러낼 항목",
        description="하위 구조도에서 더할 걸러내기 이름입니다(예: thread, scope).",
        json_schema_extra=x_ui(
            tier="basic",
            when="서브에이전트 말고 다른 단위로 들어가 보고 싶을 때 바꾸세요.",
            example="thread",
        ),
    )
    value: str = Field(
        default="{group}",
        title="값",
        description="걸러낼 값입니다. {group}은 누른 묶음의 값으로 바뀝니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="묶음 값 앞뒤에 글자를 붙여야 할 때 바꾸세요(예: run:{group}).",
        ),
    )


class ArchitectureUnavailable(DefinitionModel):
    """로그에 남지 않아 볼 수 없는 항목입니다. 칸에 늘 '수집 안 됨: 항목 — 이유'로 보입니다."""

    model_config = ConfigDict(title="수집 안 되는 항목")

    item: NonEmptyStr = Field(
        title="항목",
        description="볼 수 없는 내용의 이름입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="이 칸에서 볼 수 없는 내용을 미리 알리고 싶을 때 적으세요.",
            example="시스템 프롬프트 본문",
        ),
    )
    reason: str = Field(
        default="",
        title="이유",
        description="왜 볼 수 없는지 짧게 적습니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="볼 수 없는 이유를 함께 알리고 싶을 때 적으세요.",
            example="로그에 남지 않음",
        ),
    )


class ArchitectureCell(DefinitionModel):
    """구조도의 칸 하나입니다. 조건에 맞는 로그 이벤트를 모아 횟수·오류·토큰을 보입니다."""

    # 칸 id는 프로필 cells의 키다(선언 순서 = 그리기·Tab 순서). x·y는 칸 **중심** 좌표, w·h를
    # 비우면 기본 180 x 68. 좌표가 없는 칸은 화면이 선언 순서대로 격자에 놓는다.
    # when이 없으면 아무 이벤트도 모으지 않는다(그리기만 하는 칸).
    # metrics는 보일 지표 이름(열린 문자열, 알려진 값은 KnownArchitectureMetrics). 비우면 횟수·오류.
    # tone·view는 그리기 이름(열린 문자열, 화면 확장 지점 X24가 해석).

    model_config = ConfigDict(title="칸")

    label: str | None = Field(
        default=None,
        title="이름",
        description="칸에 보일 이름입니다. 비우면 칸 id를 씁니다.",
        json_schema_extra=x_ui(
            tier="basic", when="칸 id가 알아보기 어려울 때 쉬운 이름을 붙이세요.", example="LLM"
        ),
    )
    description: str | None = Field(
        default=None,
        title="설명",
        description="이름 아래 한 줄 설명입니다. 길면 말줄임으로 잘리고 전체는 툴팁에 보입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="이 칸이 무엇인지 그림에서 바로 알리고 싶을 때 적으세요.",
            example="원격 모델 API",
        ),
    )
    x: float | None = Field(
        default=None,
        title="가로 위치",
        description="칸 가운데의 가로 좌표입니다. 비우면 화면이 순서대로 자리를 잡습니다.",
        json_schema_extra=x_ui(
            tier="basic", when="칸을 옮기고 싶을 때 바꾸세요.", example=1400, unit="px"
        ),
    )
    y: float | None = Field(
        default=None,
        title="세로 위치",
        description="칸 가운데의 세로 좌표입니다. 비우면 화면이 순서대로 자리를 잡습니다.",
        json_schema_extra=x_ui(
            tier="basic", when="칸을 옮기고 싶을 때 바꾸세요.", example=280, unit="px"
        ),
    )
    w: float | None = Field(
        default=None,
        gt=0,
        title="폭",
        description="칸의 가로 크기입니다. 비우면 180입니다.",
        json_schema_extra=x_ui(tier="advanced", example=180, unit="px"),
    )
    h: float | None = Field(
        default=None,
        gt=0,
        title="높이",
        description="칸의 세로 크기입니다. 비우면 68입니다.",
        json_schema_extra=x_ui(tier="advanced", example=68, unit="px"),
    )
    zone: str | None = Field(
        default=None,
        title="영역",
        description="이 칸이 들어가는 가장 안쪽 영역의 id입니다.",
        json_schema_extra=x_ui(tier="advanced", example="runtime"),
    )
    tone: str | None = Field(
        default=None,
        title="색",
        description=(
            "칸 왼쪽 띠의 색 이름입니다(예: blue, teal, gold). 모르는 이름은 중립 색입니다."
        ),
        json_schema_extra=x_ui(
            tier="basic",
            when="비슷한 칸끼리 같은 색으로 묶어 보이고 싶을 때 바꾸세요.",
            example="purple",
        ),
    )
    view: str | None = Field(
        default=None,
        title="그리는 방식",
        description="칸을 그리는 방식 이름입니다(예: grouped). 비우면 기본 칸입니다.",
        json_schema_extra=x_ui(tier="advanced", example="grouped"),
    )
    when: ConditionSpec | None = Field(
        default=None,
        title="모을 이벤트",
        description="이 칸에 셀 로그 이벤트의 조건입니다. 비우면 이벤트를 모으지 않습니다.",
        json_schema_extra=x_ui(tier="basic", when="이 칸에 세는 이벤트를 바꾸고 싶을 때 고치세요."),
    )
    group_by: JsonPointer | None = Field(
        default=None,
        title="묶을 값",
        description="모은 이벤트를 이 값별로 나눠 보입니다(예: /thread, /correlation/mcp_server).",
        json_schema_extra=x_ui(
            tier="advanced",
            when="서버별·도구별처럼 칸 안을 나눠 보고 싶을 때 정하세요.",
            example="/thread",
        ),
    )
    drill: ArchitectureDrill | None = Field(
        default=None,
        title="하위 구조도",
        description="묶음을 눌렀을 때 그 묶음만 다시 그리는 방법입니다. 비우면 들어갈 수 없습니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="서브에이전트처럼 안쪽 흐름을 따로 보고 싶을 때 정하세요."
        ),
    )
    metrics: list[str] | None = Field(
        default=None,
        title="보일 지표",
        description=(
            "칸에 보일 숫자입니다(count, errors, tokens, duration). 비우면 횟수와 오류입니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced", when="토큰이나 소요 시간도 칸에서 보고 싶을 때 더하세요."
        ),
    )
    unavailable: list[ArchitectureUnavailable] = Field(
        default_factory=list,
        title="수집 안 되는 항목",
        description="이 칸에서 로그로 볼 수 없는 내용과 그 이유입니다.",
        json_schema_extra={
            "default": [],
            **x_ui(
                tier="advanced", when="로그에 남지 않는 내용이 있다는 것을 알리고 싶을 때 더하세요."
            ),
        },
    )


class ArchitectureEdge(DefinitionModel):
    """칸과 칸을 잇는 연결입니다. 기록된 전달만 세고, 순서로만 아는 연결은 점선으로 그립니다."""

    # kind: observed = 그 전달을 기록한 이벤트를 센다(시간상 이웃은 잇지 않음),
    # structural = 순서로만 아는 연결(지표 없음). 열린 문자열이고 모르는 값은 프로필 검사가 알린다.
    # points는 시작·끝 포함 꺾은선 꼭짓점(칸 경계에서 6px 바깥으로 계산된 값).
    # 없으면 두 칸 사이 직선.
    # label_at은 라벨 칩 중심, label_max_w는 칩 폭 상한 힌트(5.5R.2 화면 명세의 정식 필드).

    model_config = ConfigDict(title="연결")

    id: NonEmptyStr = Field(
        title="연결 id",
        description="연결을 가리키는 고유 이름입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="새 연결을 만들 때 한 번 정하세요.", example="tool_call"
        ),
    )
    from_: NonEmptyStr = Field(
        alias="from",
        title="출발 칸",
        description="연결이 시작하는 칸의 id입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="연결을 다른 칸에서 시작하게 하고 싶을 때 바꾸세요.",
            example="dispatch",
        ),
    )
    to: NonEmptyStr = Field(
        title="도착 칸",
        description="연결이 끝나는 칸의 id입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="연결을 다른 칸으로 가게 하고 싶을 때 바꾸세요.", example="tools"
        ),
    )
    label: str | None = Field(
        default=None,
        title="라벨",
        description="연결 위 칩에 보일 글자입니다. 비우면 라벨 없이 숫자만 보입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="연결이 무엇을 전달하는지 알리고 싶을 때 적으세요.",
            example="도구 호출",
        ),
    )
    kind: str = Field(
        default="observed",
        title="연결 종류",
        description=(
            "observed는 기록된 전달을 세고, structural은 순서로만 아는 연결이라 세지 않습니다."
        ),
        json_schema_extra=x_ui(
            tier="basic",
            when="로그로 셀 수 없는 순서 연결이면 structural로 바꾸세요.",
            example="structural",
        ),
    )
    style: str | None = Field(
        default=None,
        title="선 모양",
        description=(
            "선을 그리는 모양 이름입니다(예: request, return, inferred). 모르면 점선입니다."
        ),
        json_schema_extra=x_ui(tier="advanced", example="request"),
    )
    when: ConditionSpec | None = Field(
        default=None,
        title="셀 이벤트",
        description="이 연결에 셀 로그 이벤트의 조건입니다. 순서로만 아는 연결은 비워 둡니다.",
        json_schema_extra=x_ui(
            tier="basic", when="이 연결에 세는 이벤트를 바꾸고 싶을 때 고치세요."
        ),
    )
    points: list[ArchitecturePoint] | None = Field(
        default=None,
        title="꺾는 점",
        description=(
            "시작부터 끝까지 선이 지나는 점입니다(예: [[10, 20], [10, 80]]). 비우면 직선입니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced", when="선이 다른 칸을 지나가서 돌아가게 하고 싶을 때 정하세요."
        ),
    )
    label_at: ArchitecturePoint | None = Field(
        default=None,
        title="라벨 위치",
        description="라벨 칩 가운데의 좌표입니다. 비우면 선의 가운데입니다.",
        json_schema_extra=x_ui(tier="advanced", when="라벨이 다른 라벨과 겹칠 때 옮기세요."),
    )
    label_max_w: float | None = Field(
        default=None,
        gt=0,
        title="라벨 최대 폭",
        description="라벨 칩이 넓어질 수 있는 한도입니다. 비우면 화면 규칙을 따릅니다.",
        json_schema_extra=x_ui(tier="advanced", example=92, unit="px"),
    )
    metrics: list[str] | None = Field(
        default=None,
        title="보일 지표",
        description="연결에 보일 숫자입니다(count, errors, duration). 비우면 횟수와 오류입니다.",
        json_schema_extra=x_ui(tier="advanced", when="소요 시간도 연결에서 보고 싶을 때 더하세요."),
    )


class ArchitectureCoverage(DefinitionModel):
    """로그 출처 한 종류가 채울 수 있는 칸입니다. 여기 없는 칸은 '수집 안 됨'으로 보입니다."""

    # 키(출처 종류)는 로그 출처 확장 지점의 등록 이름이다. partial = 칸 id → 부분인 이유.

    model_config = ConfigDict(title="출처별 수집 범위")

    cells: list[str] = Field(
        default_factory=list,
        title="채우는 칸",
        description="이 출처의 로그로 셀 수 있는 칸의 id입니다.",
        json_schema_extra={
            "default": [],
            **x_ui(
                tier="basic",
                when="새 로그 출처가 어떤 칸을 채우는지 알릴 때 더하세요.",
            ),
        },
    )
    partial: dict[str, str] = Field(
        default_factory=dict,
        title="일부만 보이는 칸",
        description="칸 id마다 일부만 보이는 이유입니다. 칸에 '부분' 표시와 이유가 붙습니다.",
        json_schema_extra={
            "default": {},
            **x_ui(
                tier="advanced",
                when="이 출처가 칸의 일부만 기록할 때 이유를 적으세요.",
            ),
        },
    )


class ArchitectureOptions(DefinitionModel):
    """구조도의 추가 선택입니다."""

    model_config = ConfigDict(title="추가 선택")

    inferred_llm_duration: bool = Field(
        default=False,
        title="모델 소요 추정",
        description="켜면 앞 이벤트부터 응답까지의 간격을 모델 소요로 '추정' 표시와 함께 보입니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="모델 응답이 얼마나 걸렸는지 대략이라도 보고 싶을 때 켜세요."
        ),
    )


class ArchitectureProfile(DefinitionModel):
    """구조도 규칙(프로필)입니다. 어떤 칸과 연결을 어디에 그리고 무엇을 셀지 정합니다."""

    # source_priority: 한 칸·연결을 여러 출처 종류가 채우면 목록 앞의 종류만 센다(이중 집계 방지).
    # 목록에 없는 종류는 맨 뒤다. error_when에 맞거나 분류 체계에서 오류로 표시한 범주의 이벤트를
    # 오류로 센다. unassigned = 어느 칸에도 맞지 않은 이벤트를 "분류 안 됨"으로 센다.

    model_config = ConfigDict(title="구조도 프로필")

    title: str | None = Field(
        default=None,
        title="제목",
        description="목록과 고르기에 보일 이름입니다. 비우면 프로필 id를 씁니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="프로필 목록에서 알아보기 쉬운 이름으로 바꾸고 싶을 때 바꾸세요.",
            example="에이전트 아키텍처",
        ),
    )
    description: str | None = Field(
        default=None,
        title="설명",
        description="이 프로필이 무엇을 그리는지 적습니다.",
        json_schema_extra=x_ui(tier="advanced", example="사용자 입력부터 모델과 도구까지의 흐름"),
    )
    canvas: ArchitectureCanvas | None = Field(
        default=None,
        title="캔버스",
        description="그림 바탕의 크기입니다. 비우면 칸 위치에 맞춰 정합니다.",
        json_schema_extra=x_ui(
            tier="basic", when="칸이 바탕 밖으로 나가거나 여백이 너무 클 때 바꾸세요."
        ),
    )
    zones: list[ArchitectureZone] = Field(
        default_factory=list,
        title="영역",
        description="칸 뒤에 깔 영역입니다. 앞에 적은 영역이 먼저(아래에) 그려집니다.",
        json_schema_extra={
            "default": [],
            **x_ui(
                tier="advanced",
                when="칸을 내 PC, 모델 서버처럼 구역으로 나눠 보이고 싶을 때 더하세요.",
            ),
        },
    )
    cells: dict[str, ArchitectureCell] = Field(
        default_factory=dict,
        title="칸",
        description="칸 id마다 이름·위치·모을 이벤트를 정합니다. 적은 순서가 Tab 이동 순서입니다.",
        json_schema_extra={
            "default": {},
            **x_ui(tier="basic", when="칸을 더하거나 빼거나 옮기고 싶을 때 고치세요."),
        },
    )
    edges: list[ArchitectureEdge] = Field(
        default_factory=list,
        title="연결",
        description="칸과 칸을 잇는 선입니다. 적은 순서가 Tab 이동 순서입니다.",
        json_schema_extra={
            "default": [],
            **x_ui(tier="basic", when="연결을 더하거나 빼거나 경로를 바꾸고 싶을 때 고치세요."),
        },
    )
    coverage: dict[str, ArchitectureCoverage] = Field(
        default_factory=dict,
        title="출처별 수집 범위",
        description=(
            "로그 출처 종류마다 채울 수 있는 칸입니다. 어느 "
            "출처도 채우지 못하는 칸은 '수집 안 됨'입니다."
        ),
        json_schema_extra={
            "default": {},
            **x_ui(
                tier="advanced",
                when="새 로그 출처를 쓰거나 칸이 잘못 '수집 안 됨'으로 보일 때 고치세요.",
            ),
        },
    )
    source_priority: list[str] = Field(
        default_factory=list,
        title="출처 우선순위",
        description="같은 호출을 두 출처가 함께 기록할 때 앞에 적은 출처만 셉니다.",
        json_schema_extra={
            "default": [],
            **x_ui(
                tier="advanced", when="실행 구조도에서 같은 도구 호출이 두 번 세일 때 정하세요."
            ),
        },
    )
    error_when: ConditionSpec | None = Field(
        default=None,
        title="오류로 볼 이벤트",
        description=(
            "이 조건에 맞는 이벤트를 오류로 셉니다. 로그 범주에서 오류로 표시한 범주도 셉니다."
        ),
        json_schema_extra=x_ui(tier="advanced", when="실패로 볼 상태 값이 다를 때 고치세요."),
    )
    group_limit: int = Field(
        default=DEFAULT_GROUP_LIMIT,
        ge=0,
        title="묶음 표시 개수",
        description="칸 안 묶음을 몇 개까지 따로 보일지입니다. 나머지는 '그 밖'으로 합칩니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="서버나 서브에이전트가 많아 묶음이 잘릴 때 늘리세요.", unit="개"
        ),
    )
    unassigned: bool = Field(
        default=True,
        title="분류 안 됨 세기",
        description="어느 칸에도 맞지 않은 이벤트를 '분류 안 됨'으로 따로 셉니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="칸에 넣지 않은 이벤트 수가 필요 없을 때 끄세요."
        ),
    )
    options: ArchitectureOptions | None = Field(
        default=None,
        title="추가 선택",
        description="모델 소요 추정 같은 추가 선택입니다. 비우면 모두 꺼짐입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


class ArchitectureSettings(DefinitionModel):
    """구조도 규칙(프로필)을 고르고 고칩니다. 기본 프로필을 끄거나 내 프로필을 더할 수 있습니다."""

    # 워크스페이스 설정의 architecture 섹션(구조도 모듈이 소유). 공통 설정 모델에는 필드를
    # 두지 않는다(계약 층: definitions가 이 모듈을 모른다). 공통 설정은 모르는 키를 보존하므로
    # 그대로 왕복된다.
    # 병합: 패키지 기본(include_defaults일 때) → 플러그인 → 사용자. 같은 id면 통째로 바꾸고,
    # 값이 null이면 그 id를 지운다. 저장·전송은 model_dump(exclude_unset=True)로 한다
    # (생략 = 기본값).

    model_config = ConfigDict(title="구조도")

    include_defaults: bool = Field(
        default=True,
        title="기본 프로필 사용",
        description=(
            "패키지가 주는 기본 프로필을 목록에 넣습니다. 꺼도 직접 만든 프로필은 남습니다."
        ),
        json_schema_extra=x_ui(
            tier="basic", when="기본 구조도 대신 내 프로필만 쓰고 싶을 때 끄세요."
        ),
    )
    default_profile: str | None = Field(
        default=None,
        title="기본으로 보여 줄 프로필",
        description=(
            "구조도를 열 때 먼저 보일 프로필입니다. 비우거나 "
            "없는 프로필이면 목록의 첫 프로필입니다."
        ),
        json_schema_extra=x_ui(
            tier="basic",
            when="여러 프로필 중 자주 보는 것을 먼저 열고 싶을 때 고르세요.",
            example="agent-architecture",
        ),
    )
    profiles: dict[str, ArchitectureProfile | None] = Field(
        default_factory=dict,
        title="프로필",
        description=(
            "프로필 id마다 규칙을 둡니다. 같은 id면 기본 "
            "프로필을 바꾸고, 비우면 그 프로필을 끕니다."
        ),
        json_schema_extra={
            "default": {},
            **x_ui(
                tier="basic",
                when="구조도 칸·연결을 내 방식대로 바꾸고 싶을 때 고치세요.",
                widget="architecture-profiles",
            ),
        },
    )
