"""agent-console-example-wiki-search: 메모리 안 낱말 역색인 위키 검색 방식(X48).

위키 서버 모듈(`mod-wiki`)에는 entry point(`agent_console.wiki_search_indexes`)로만 등록된다.
이 패키지는 위키 라이브러리(`agent_console_wiki`)의 색인 프로토콜·강조 계산만 쓰고, 서버 모듈은
import하지 않는다.

공개 API:
    - 검색 방식 id: ``BACKEND_ID``
    - 색인: ``InvertedSearchIndex``, 만들기 ``make_index(options)``
    - 등록: ``index_factory()``(entry point 값 — 공장 ``(root, options)``를 돌려줌)
    - 옵션 기본값: ``default_options()``
"""

from agent_console_example_wiki_search._index import (
    BACKEND_ID,
    InvertedSearchIndex,
    default_options,
    index_factory,
    make_index,
)

__all__ = [
    "BACKEND_ID",
    "InvertedSearchIndex",
    "default_options",
    "index_factory",
    "make_index",
]
