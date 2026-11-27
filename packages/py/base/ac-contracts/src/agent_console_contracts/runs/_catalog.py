"""실행 백엔드 모델 목록과 계정 조회 상태(0.16.1, design §1.1-MB MD-8).

``GET /backends/{id}/model-catalog`` 응답이다. ``models``는 설치자 설정 목록과 백엔드 계정 조회
결과(선택 능력 ``model_discovery``)를 합친 목록이고, ``discovery``는 조회가 어떤 상태인지 알린다.
조회가 실패해도 오류 응답이 아니다(설정 목록 + ``state = failed`` + 경고 이슈).

조회한 모델 이름·설명은 바깥 데이터다(번역하지 않는다). 글자 필드는 서버가 비밀 가림을 거쳐
길이를 자른 뒤 낸다.
"""

from typing import Literal

from pydantic import Field

from agent_console_contracts._base import ContractModel, NonEmptyStr
from agent_console_contracts.definitions import Issue

from ._descriptors import ModelInfo

type ModelDiscoveryState = Literal["ok", "stale", "failed", "disabled", "unsupported"]
"""모델 조회 상태(고정 어휘).

- ok: 조회 성공(캐시 시간 안).
- stale: 직전 성공 목록을 준다(새 조회가 실패했거나 진행 중).
- failed: 성공한 적이 없다(설정 목록만, 이슈에 사유).
- disabled: 설치자가 조회를 껐다.
- unsupported: 백엔드에 조회 능력이 없거나 이 인증으로는 조회할 수 없다.
"""


class ModelDiscoveryInfo(ContractModel):
    """백엔드 계정 모델 조회 상태."""

    state: ModelDiscoveryState = Field(description="조회 상태. 화면은 이 값으로 안내를 고른다.")
    fetched_at: float | None = Field(
        default=None,
        description="목록에 쓴 조회가 끝난 시각(epoch 초). null = 조회한 적 없음.",
    )
    expires_at: float | None = Field(
        default=None,
        description="이 결과를 다시 조회하지 않고 쓰는 마지막 시각(epoch 초). null = 정하지 않음.",
    )
    issues: list[Issue] = Field(
        default_factory=list,
        description=(
            "조회 문제(예: `backend.model_discovery_failed` 경고, `details.backend_id`·`reason`). "
            "비면 문제 없음."
        ),
    )


class BackendModelCatalog(ContractModel):
    """실행 백엔드 하나의 모델 목록(설정 + 계정 조회)과 조회 상태."""

    backend_id: NonEmptyStr
    models: list[ModelInfo] = Field(
        default_factory=list,
        description=(
            "합친 모델 목록. 설치자 설정 목록이 앞(그 순서), 조회에만 있는 모델은 뒤(백엔드가 준 "
            "순서). 같은 id는 한 항목이고 `sources`에 둘 다 적힌다."
        ),
    )
    discovery: ModelDiscoveryInfo = Field(description="계정 조회 상태.")


__all__ = ["BackendModelCatalog", "ModelDiscoveryInfo", "ModelDiscoveryState"]
