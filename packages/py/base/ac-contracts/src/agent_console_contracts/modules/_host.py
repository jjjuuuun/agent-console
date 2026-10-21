"""호스트·모듈 조립 계약: 모듈 목록, 준비 신호, 서버 정보, 기능 꺼짐 오류 상세.

호스트(`ac-modkit`의 host)가 기능 이름을 모르고 내는 응답이다. 모듈 id·포트 이름·상태는 열린
문자열이다(알려진 상태 값은 문서 상수 `KnownModuleStatus`, design §3R.1.8).
"""

from typing import Literal

from pydantic import Field

from agent_console_contracts._base import ContractModel, JsonObject, NonEmptyStr
from agent_console_contracts.common import ErrorInfo
from agent_console_contracts.definitions import Issue

type ModuleStatus = NonEmptyStr
"""모듈 상태(열린 문자열). 알려진 값은 문서 상수 `KnownModuleStatus`
(active·disabled·unsatisfied·failed·conflict). 화면은 모르는 값을 그대로 보인다."""


class ModuleInfo(ContractModel):
    """`GET /modules` 항목: 설치된 모듈(기능·연동) 하나와 그 상태.

    웹은 이 목록과 라우트 `requires`(데이터)로 화면을 조립한다.
    목록·종류·역할 이름은 고정하지 않는다.
    """

    id: NonEmptyStr = Field(description="모듈 id(entry point 이름).")
    kind: NonEmptyStr = Field(
        description="모듈 종류(열린 문자열, 예: feature, link). 화면은 모르는 값을 그대로 보인다."
    )
    version: str = Field(description="모듈 패키지 버전.")
    contracts: dict[str, str] = Field(
        default_factory=dict,
        description="이 모듈이 쓰는 계약 하위 모듈 → 버전(`CONTRACT_VERSIONS` 값).",
    )
    status: ModuleStatus
    reason: str | None = Field(
        default=None,
        description="active가 아닌 이유(빠진 포트, 충돌 등). 비밀·예외 원문은 담지 않는다.",
    )
    web_roles: list[str] = Field(
        default_factory=list,
        description="웹 라우트 `requires`가 가리키는 역할 이름(예: conversations, usage).",
    )
    provides: list[str] = Field(default_factory=list, description="제공하는 포트 이름.")
    requires: list[str] = Field(
        default_factory=list, description="필요한 포트 이름(필수·선택 모두, 상태 판단 근거)."
    )


class FeatureUnavailableDetails(ContractModel):
    """`feature_unavailable`(HTTP 409) 오류의 `error.details`.

    켜진 모듈 안에서 선택 포트를 줄 모듈이 없어 그 동작만 꺼졌을 때 쓴다.
    """

    module: NonEmptyStr = Field(description="요청을 받은 모듈 id.")
    port: NonEmptyStr = Field(description="빠진 포트 이름.")


class ModuleOptionsView(ContractModel):
    """`GET /modules/{id}/options` 응답: 모듈 옵션의 읽기 전용 보기(0.8.0).

    모듈 옵션은 설치자 설정 파일(`modules.options.<id>`)에서만 바꾼다. 쓰기 API는 없다.
    """

    module_id: NonEmptyStr
    schema_: JsonObject | None = Field(
        default=None,
        alias="schema",
        description="옵션 JSON Schema(모듈이 선언). null = 모듈이 스키마를 내지 않음.",
    )
    values: JsonObject = Field(
        default_factory=dict, description="지금 값. 비밀로 보이는 값은 가려져 있다."
    )
    yaml_snippet: str = Field(
        default="", description="설정 파일에 붙일 YAML 조각(가린 값 그대로, 들여쓰기 포함)."
    )


class BootstrapResponse(ContractModel):
    """`GET /bootstrap`."""

    token: NonEmptyStr
    server_version: str
    contracts_version: str


class HealthResponse(ContractModel):
    """`GET /health`: 준비 신호(서버가 요청을 받을 수 있으면 200). 토큰 없이 읽는다, 비밀 없음.

    셸·스크립트가 서버 기동을 기다릴 때 폴링한다.
    """

    status: Literal["ok"] = "ok"
    server_version: str
    contracts_version: str


class PluginInfo(ContractModel):
    """서버가 읽은 플러그인 하나(설정 화면 서버 정보, 읽기 전용)."""

    name: NonEmptyStr
    group: str | None = Field(default=None, description="확장 지점(entry point 그룹) 이름.")
    loaded: bool = True
    status: NonEmptyStr = Field(
        default="loaded",
        description=(
            "로딩 상태(열린 문자열). 알려진 값: loaded, failed(error 있음), skipped(설정 "
            "`plugins.enabled`에 없어 읽지 않음), disabled(읽었지만 `plugins.enabled`에 없는 "
            "항목이라 등록 해제). 화면은 모르는 값을 그대로 보인다."
        ),
    )
    error: ErrorInfo | None = None


class ServerInfo(ContractModel):
    """`GET /server-info` 응답(읽기 전용). 설치자 설정 값 중 비밀이 아닌 것만."""

    server_version: str
    contracts_version: str
    plugins: list[PluginInfo] = Field(default_factory=list)
    attributes: JsonObject = Field(default_factory=dict)
    warnings: list[Issue] = Field(
        default_factory=list,
        description="워크스페이스 점검 경고(예: 평문 비밀 의심). 값은 담지 않는다.",
    )
