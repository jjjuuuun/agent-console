"""agent-console-example-sdd-junit: JUnit XML 테스트 결과를 스펙 추적 표에 넣는 검증 결과 출처(X42).

스펙 서버 모듈(`mod-sdd`)에는 entry point(`agent_console.sdd_verification_sources`)로만 등록된다.
이 패키지는 공개 계약(`agent_console_contracts.sdd`)·스펙 라이브러리 프로토콜(`agent_console_sdd`)·
안전 정규식(`agent_console_safe_regex`)만 쓴다. 파일은 주입받은 `SpecFiles`로만 읽는다.

공개 API:
    - 출처: ``JUnitVerificationSource``(id 기본 ``example.junit``), 상수 ``SOURCE_ID``
    - 핵심 함수: ``collect_results``(서버 없이) → ``CollectReport``, ``find_requirement_ids``
    - 옵션: ``JUnitOptions``·``parse_options``·``check_options``·``default_options``·
      ``check_file_pattern``, 오류 ``JUnitOptionsError``
    - 읽기·찾기: ``parse_junit`` → ``TestCase``(오류 ``JUnitError``),
      ``find_files`` → ``FoundFiles``
"""

from agent_console_example_sdd_junit._glob import FoundFiles, find_files
from agent_console_example_sdd_junit._junit import JUnitError, TestCase, parse_junit
from agent_console_example_sdd_junit._options import (
    JUnitOptions,
    JUnitOptionsError,
    check_file_pattern,
    check_options,
    default_options,
    parse_options,
)
from agent_console_example_sdd_junit._source import (
    SOURCE_ID,
    CollectReport,
    JUnitVerificationSource,
    collect_results,
    find_requirement_ids,
)

__all__ = [
    "SOURCE_ID",
    "CollectReport",
    "FoundFiles",
    "JUnitError",
    "JUnitOptions",
    "JUnitOptionsError",
    "JUnitVerificationSource",
    "TestCase",
    "check_file_pattern",
    "check_options",
    "collect_results",
    "default_options",
    "find_files",
    "find_requirement_ids",
    "parse_junit",
    "parse_options",
]
