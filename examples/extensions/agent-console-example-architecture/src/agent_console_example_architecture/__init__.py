"""agent-console-example-architecture: 예제 구조도 프로필 플러그인(X23).

엔진·서버에는 entry point(``agent_console.architecture_profiles``)로만 등록된다. 공개 계약
(``agent_console_contracts``)과 구조도 라이브러리(``agent_console_architecture``)만 사용한다.

공개 API:
    - entry point 대상: ``profiles()`` → ``{id: ArchitectureProfile}``
    - 상수: ``PROFILE_ID``, ``PROFILES_RESOURCE``
"""

from agent_console_example_architecture.profiles import PROFILE_ID, PROFILES_RESOURCE, profiles

__all__ = ["PROFILES_RESOURCE", "PROFILE_ID", "profiles"]
