"""저장 전 정의 검사(``definitions.checks``): 위키 리소스의 모르는 위키 id 경고.

위키 리소스(종류 = 리소스 종류 데이터의 ``id``)의 ``config.wikis[i].wiki``·``default_wiki``가 아는
위키 id에 없으면 warning ``wiki.unknown_wiki``(path = 리소스 문서 기준, details ``wiki``). 저장은
막지 않는다(에이전트가 그 위키를 부르면 ``wiki.wiki_unavailable``). 형식 검사는 리소스 종류
(``WikiResourceType``)가 따로 한다.

검사는 어느 공간에 저장하는지 모른다(``definitions.checks`` 모양에 공간이 없다). 그래서 아는 위키 =
단독 공간 위키 + (``projects.lookup``이 있으면) 모든 프로젝트 공간의 위키다. 어느 공간에도 없는
id만 경고한다. 실행 때 그 실행 공간에 없는 위키는 공급자가 따로 경고한다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from agent_console_contracts import Issue, KnownIssueCodes
from agent_console_store import RESOURCE_KIND

from .ports import ProjectLookupLike, WikiServiceLike

__all__ = ["WikiResourceCheck", "known_wiki_ids"]

_log = logging.getLogger(__name__)


def _document(document: Mapping[str, Any] | BaseModel) -> Mapping[str, Any]:
    if isinstance(document, BaseModel):
        return document.model_dump(mode="json")
    return document


def _spaces(projects: ProjectLookupLike | None) -> list[str | None]:
    found: list[str | None] = [None]
    if projects is None:
        return found
    try:
        listed = list(projects.list_projects())
    except Exception:
        _log.info("프로젝트 목록을 읽지 못해 단독 공간 위키만 봅니다", exc_info=True)
        return found
    for project in listed:
        project_id = getattr(project, "id", None)
        if isinstance(project_id, str) and project_id:
            found.append(project_id)
    return found


def known_wiki_ids(service: WikiServiceLike, projects: ProjectLookupLike | None = None) -> set[str]:
    """아는 위키 id(단독 공간 + 프로젝트 공간들). 열 수 없는 공간은 건너뛴다."""
    known: set[str] = set()
    for space in _spaces(projects):
        try:
            known.update(service.wiki_ids(space))
        except Exception:  # 폴더 없음·연동 꺼짐 등 — 그 공간만 모른다
            continue
    return known


class WikiResourceCheck:
    """``definitions.checks`` 하나.

    Args:
        service: 지금 위키 서비스를 돌려주는 함수(None이면 검사하지 않는다).
        resource_type: 위키 리소스 종류 id(리소스 종류 데이터).
        projects: 지금 프로젝트 목록을 돌려주는 함수(선택, None이면 단독 공간만).
        resource_kind: 정의 종류 이름(기본 ``agent_console_store.RESOURCE_KIND``).
    """

    def __init__(
        self,
        service: Callable[[], WikiServiceLike | None],
        *,
        resource_type: str,
        projects: Callable[[], ProjectLookupLike | None] = lambda: None,
        resource_kind: str = RESOURCE_KIND.name,
    ) -> None:
        self._service = service
        self._projects = projects
        self.resource_type = resource_type
        self.resource_kind = resource_kind

    def issues(self, kind: str, document: Mapping[str, Any] | BaseModel) -> Sequence[Issue]:
        """모르는 위키 id마다 경고(메시지에 설정 값 외의 내용은 없다)."""
        if kind != self.resource_kind:
            return []
        doc = _document(document)
        if doc.get("type") != self.resource_type:
            return []
        config = doc.get("config")
        if not isinstance(config, Mapping):
            return []
        wanted: list[tuple[str, str]] = []
        wikis = config.get("wikis")
        if isinstance(wikis, Sequence) and not isinstance(wikis, str | bytes):
            for index, item in enumerate(wikis):
                value = item.get("wiki") if isinstance(item, Mapping) else None
                if isinstance(value, str) and value:
                    wanted.append((value, f"/config/wikis/{index}/wiki"))
        default = config.get("default_wiki")
        if isinstance(default, str) and default:
            wanted.append((default, "/config/default_wiki"))
        if not wanted:
            return []
        service = self._service()
        if service is None:
            return []
        known = known_wiki_ids(service, self._projects())
        return [self._issue(wiki, path) for wiki, path in wanted if wiki not in known]

    @staticmethod
    def _issue(wiki: str, path: str) -> Issue:
        return Issue(
            severity="warning",
            code=KnownIssueCodes.WIKI_UNKNOWN_WIKI,
            message=f"위키 {wiki!r}가 없습니다. 에이전트는 이 위키를 쓸 수 없습니다",
            path=path,
            details={"wiki": wiki},
        )
