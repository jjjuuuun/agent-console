"""위키 검색 색인 계약 묶음(`WikiSearchContractTests`)을 이 예제 색인으로 통과시킨다."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_console_example_wiki_search import make_index
from agent_console_wiki import WikiSearchIndex
from agent_console_wiki.testing import WikiSearchContractTests


class TestInvertedIndexContract(WikiSearchContractTests):
    def make_index(self, tmp_path: Path, **options: Any) -> WikiSearchIndex:
        limits = options.pop("limits", None)
        extra = (
            {
                k: getattr(limits, k)
                for k in ("max_results", "snippet_chars", "max_terms")
                if limits is not None
            }
            if limits is not None
            else {}
        )
        return make_index({**options, **extra})
