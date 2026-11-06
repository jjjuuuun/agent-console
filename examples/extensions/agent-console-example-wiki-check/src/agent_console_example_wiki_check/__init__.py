"""agent-console-example-wiki-check: 머리말 필수 키가 없으면 경고·거부하는 위키 쓰기 검사(X50).

위키 서버 모듈(`mod-wiki`)에는 entry point(`agent_console.wiki_write_checks`)로만 등록된다.
이 패키지는 공개 계약(`agent_console_contracts.wiki`)과 위키 라이브러리의 글롭
(`agent_console_wiki`)만 쓴다. 서버 모듈은 import하지 않는다.

공개 API:
    - 검사: ``FrontMatterKeysCheck(options, *, check_id=CHECK_ID)``, 상수 ``CHECK_ID``
    - 옵션: ``FrontMatterKeysOptions``·``parse_options``·``check_options``·``default_options``,
      오류 ``FrontMatterOptionsError``
    - 핵심 함수: ``missing_keys(front_matter, keys, *, allow_empty)``
"""

from agent_console_example_wiki_check._check import (
    CHECK_ID,
    FrontMatterKeysCheck,
    FrontMatterKeysOptions,
    FrontMatterOptionsError,
    check_options,
    default_options,
    missing_keys,
    parse_options,
)

__all__ = [
    "CHECK_ID",
    "FrontMatterKeysCheck",
    "FrontMatterKeysOptions",
    "FrontMatterOptionsError",
    "check_options",
    "default_options",
    "missing_keys",
    "parse_options",
]
