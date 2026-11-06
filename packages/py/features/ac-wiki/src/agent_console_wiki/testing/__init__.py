"""시험 도구: 메모리 페이지 파일 `MemoryWikiPages`, 가짜 시계 `FakeClock`, 계약 묶음.

계약 묶음: `WikiPagesContractTests`(페이지 파일), `WikiHistoryContractTests`(X49 기록),
`WikiSearchContractTests`(X48 검색 색인).

다른 패키지(서버 모듈·프로젝트 연동의 공간 페이지 파일, SQLite 기록 저장소)가 자기 구현을 같은
의미로 시험할 수 있게 공개한다. 표본 위키 데이터는 두지 않는다(R0.2 — 테스트 안에서 임시로 만든다).

```python
class TestMyPages(WikiPagesContractTests):
    def make_pages(self, tmp_path) -> WikiPages:
        return MyPages(tmp_path)

class TestMyHistory(WikiHistoryContractTests):
    def make_history(self, tmp_path) -> WikiHistory:
        return MyHistory(tmp_path / "h.sqlite3")
```
"""

from __future__ import annotations

from ._contract import WikiPagesContractTests
from ._history_contract import FakeClock, WikiHistoryContractTests
from ._memory import MemoryWikiPages
from ._search_contract import WikiSearchContractTests, make_search_document

__all__ = [
    "FakeClock",
    "MemoryWikiPages",
    "WikiHistoryContractTests",
    "WikiPagesContractTests",
    "WikiSearchContractTests",
    "make_search_document",
]
