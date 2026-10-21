"""계약 모델의 공통 베이스와 타입 별칭(내부 모듈)."""

from typing import Annotated, Any, ClassVar

from pydantic import (
    BaseModel,
    ConfigDict,
    SerializerFunctionWrapHandler,
    StringConstraints,
    model_serializer,
)

JsonObject = dict[str, Any]
"""임의 키-값 객체. 내용은 계약이 해석하지 않는다(디스크립터의 JSON Schema가 정의)."""

Slug = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")]
"""정의 id(파일 이름으로도 쓰인다). 영숫자로 시작, 영숫자·`_`·`-`, 최대 128자."""

NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]


class ContractModel(BaseModel):
    """모든 계약 모델의 베이스. 모르는 필드는 무시한다(전방 호환)."""

    model_config = ConfigDict(
        extra="ignore",
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )


class DefinitionModel(ContractModel):
    """사용자 정의 데이터(YAML 파일) 모델. 모르는 최상위 필드는 보존한다(손으로 고친 파일 왕복)."""

    model_config = ConfigDict(extra="allow")


def drop_unset(model: BaseModel, data: dict[str, Any], path: tuple[str, ...]) -> None:
    """직렬화 결과 `data`에서 `path`(필드 이름 경로)의 마지막 필드가 지정되지 않았으면 뺀다."""
    obj: Any = model
    node: Any = data
    for key in path[:-1]:
        obj = getattr(obj, key, None)
        node = node.get(key) if isinstance(node, dict) else None
        if not isinstance(obj, BaseModel) or not isinstance(node, dict):
            return
    if path[-1] not in obj.model_fields_set:
        node.pop(path[-1], None)


class OmitWhenUnsetContract(ContractModel):
    """지정하지 않은 일부 필드를 전체 직렬화에서도 빼는 계약 모델(내부 베이스).

    정의 해시(그래프 버전 해시 등)는 기본값까지 넣은 전체 직렬화로 계산하는 곳이 있고, 오류 본문처럼
    전송 형식을 그대로 비교하는 소비자도 있다. 나중 계약에서 더한 선택 필드가 지정되지 않았는데도
    null·기본값으로 나타나면 옛 해시·형식이 모두 바뀐다. 그래서 `_OMIT_WHEN_UNSET`의 경로는
    **지정했을 때만** 직렬화한다(값은 모델 기본값 그대로 읽힌다).
    """

    _OMIT_WHEN_UNSET: ClassVar[tuple[tuple[str, ...], ...]] = ()

    @model_serializer(mode="wrap")
    def _omit_new_unset_fields(  # type: ignore[no-untyped-def]
        self, handler: SerializerFunctionWrapHandler
    ):
        # 반환 형식을 적지 않는다: 적으면 직렬화 JSON Schema(OpenAPI)가 일반 객체로 바뀐다.
        data = handler(self)
        if isinstance(data, dict):
            for path in self._OMIT_WHEN_UNSET:
                drop_unset(self, data, path)
        return data


class OmitWhenUnsetModel(OmitWhenUnsetContract, DefinitionModel):
    """`OmitWhenUnsetContract`의 정의 데이터(YAML) 판. 모르는 최상위 필드를 보존한다."""
