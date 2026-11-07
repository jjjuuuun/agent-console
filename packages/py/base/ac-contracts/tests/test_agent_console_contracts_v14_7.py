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


def test_contracts_version_is_0_14_7() -> None:
    assert CONTRACTS_VERSION == "0.14.7"
    assert build_schema()["x-constants"]["CONTRACTS_VERSION"] == "0.14.7"
    assert CONTRACT_VERSIONS == {
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
