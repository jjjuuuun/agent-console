"""계약 0.14.7(요청 11/07 후속, 더하기만): `chat` 1.4.0·`common` 1.13.0.

- `ConversationLocation{project_id}` — `GET /conversations/{id}/locate` 응답.
- `ErrorCodes.CONVERSATION_AMBIGUOUS`(409).
"""

from agent_console_contracts import (
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    HTTP_STATUS_BY_ERROR_CODE,
    ConversationLocation,
    ErrorCodes,
)
from agent_console_contracts.schema import build_schema


def _ver(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_contracts_version_is_at_least_0_14_7() -> None:
    """0.14.7에서 정한 버전 이상이다(정확한 지금 값은 0.14.8 테스트가 고정한다)."""
    assert _ver(CONTRACTS_VERSION) >= (0, 14, 7)
    assert build_schema()["x-constants"]["CONTRACTS_VERSION"] == CONTRACTS_VERSION
    v0147 = {
        "common": "1.13.0",
        "resources": "1.1.0",
        "logs": "1.2.0",
        "definitions": "1.7.0",
        "runs": "1.8.0",
        "usage": "1.1.0",
        "projects": "3.6.0",
        "chat": "1.4.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "architecture": "1.0.0",
        "memory": "1.1.0",
        "sdd": "1.2.0",
        "wiki": "1.2.0",
        "modules": "1.6.0",
    }
    assert set(CONTRACT_VERSIONS) == set(v0147)
    for sub, version in v0147.items():
        assert _ver(CONTRACT_VERSIONS[sub]) >= _ver(version), sub


def test_location_defaults_to_app_records() -> None:
    assert ConversationLocation.model_validate({}).project_id is None
    found = ConversationLocation(project_id="pa")
    assert ConversationLocation.model_validate(found.model_dump(mode="json")).project_id == "pa"


def test_location_is_in_schema() -> None:
    defs = build_schema()["$defs"]
    assert "ConversationLocation" in defs


def test_ambiguous_code_is_409() -> None:
    assert ErrorCodes.CONVERSATION_AMBIGUOUS == "conversation.ambiguous"
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.CONVERSATION_AMBIGUOUS] == 409
