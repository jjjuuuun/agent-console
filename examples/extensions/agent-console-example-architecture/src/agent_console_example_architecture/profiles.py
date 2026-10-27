"""구조도 프로필 플러그인(X23 예제): 패키지 데이터 파일의 프로필을 entry point로 낸다.

X23 entry point 하나 = 인자 없는 함수 → ``{프로필 id: 프로필 데이터}``. 프로필 내용은 코드가 아니라
데이터 파일(``data/example_architecture.yaml``)이다. 로더(``mod-architecture``)가 출처 이름
``plugin:<배포 이름>``을 붙인다.
"""

from __future__ import annotations

from importlib import resources
from typing import Final

from agent_console_architecture import parse_profiles_document
from agent_console_contracts.architecture import ArchitectureProfile

PROFILES_RESOURCE: Final = "data/example_architecture.yaml"
"""패키지 안 프로필 데이터 파일 경로."""

PROFILE_ID: Final = "example-minimal"
"""데이터 파일이 내는 프로필 id(테스트·README용 상수, 로더는 쓰지 않는다)."""


def profiles() -> dict[str, ArchitectureProfile]:
    """entry point 대상: 패키지 데이터 파일을 읽어 ``{id: 프로필}``을 돌려준다.

    부를 때마다 새로 읽는다(전역 캐시 없음).

    Raises:
        agent_console_architecture.ProfileDocumentError: 데이터 파일 형식이 틀렸을 때
            (로더가 그 항목만 ``failed``로 보고한다).
    """
    text = (
        resources.files(__package__ or "agent_console_example_architecture")
        .joinpath(PROFILES_RESOURCE)
        .read_text(encoding="utf-8")
    )
    return parse_profiles_document(text)
