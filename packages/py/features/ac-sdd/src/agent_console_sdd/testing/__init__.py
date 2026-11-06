"""ac-sdd 테스트 도우미: 표본 문서(`sample_spec`·`sample_files`·`render_tasks`), 이름을 모두 바꾼
문법(`RENAMED_SYNTAX`·`RENAMED_NAMES`), 가짜 파일 접근(`MemorySpecFiles`)·검증 출처
(`FakeVerificationSource`)·작업 연동(`FakeTaskIntegration`), 메모리 저장소
조립(`memory_repository`).
다른 패키지 테스트(모듈·연동)도 쓴다. 기본 데이터·프리셋이 아니다."""

from __future__ import annotations

from ._fakes import (
    TEST_SPEC_KIND,
    TEST_TEMPLATE_KIND,
    FakeTaskIntegration,
    FakeVerificationSource,
    MemorySpecFiles,
    memory_repository,
)
from ._samples import (
    DEFAULT_NAMES,
    RENAMED_NAMES,
    RENAMED_SYNTAX,
    REQUIREMENTS,
    TASKS_TEMPLATE,
    render_tasks,
    sample_files,
    sample_spec,
)

__all__ = [
    "DEFAULT_NAMES",
    "RENAMED_NAMES",
    "RENAMED_SYNTAX",
    "REQUIREMENTS",
    "TASKS_TEMPLATE",
    "TEST_SPEC_KIND",
    "TEST_TEMPLATE_KIND",
    "FakeTaskIntegration",
    "FakeVerificationSource",
    "MemorySpecFiles",
    "memory_repository",
    "render_tasks",
    "sample_files",
    "sample_spec",
]
