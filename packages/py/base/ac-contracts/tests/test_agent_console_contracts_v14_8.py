"""계약 0.14.8(요청 11/08 후속, 더하기만): `runs` 1.9.0·`common` 1.14.0.

- `RunLocation{project_id}` — `GET /runs/{id}/locate` 응답.
- `ErrorCodes.RUN_AMBIGUOUS`(409).
"""

from agent_console_contracts import (
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    HTTP_STATUS_BY_ERROR_CODE,
    ErrorCodes,
    RunLocation,
)
from agent_console_contracts.runs import RunLocation as SubpathRunLocation
from agent_console_contracts.schema import build_schema


def test_contracts_version_is_0_14_8() -> None:
    assert CONTRACTS_VERSION == "0.14.8"
    assert build_schema()["x-constants"]["CONTRACTS_VERSION"] == "0.14.8"
    assert CONTRACT_VERSIONS == {
        "common": "1.14.0",
        "resources": "1.1.0",
        "logs": "1.2.0",
        "definitions": "1.7.0",
        "runs": "1.9.0",
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


def test_run_location_defaults_to_app_records() -> None:
    assert SubpathRunLocation is RunLocation
    assert RunLocation.model_validate({}).project_id is None
    found = RunLocation(project_id="pa")
    assert RunLocation.model_validate(found.model_dump(mode="json")).project_id == "pa"


def test_run_location_is_in_schema() -> None:
    assert "RunLocation" in build_schema()["$defs"]


def test_run_ambiguous_code_is_409() -> None:
    assert ErrorCodes.RUN_AMBIGUOUS == "run.ambiguous"
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.RUN_AMBIGUOUS] == 409
