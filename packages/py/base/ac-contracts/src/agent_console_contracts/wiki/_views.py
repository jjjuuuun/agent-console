"""위키 보기(응답) 모델: 화면 정보·위키·페이지·링크·기록·검색·그래프·점검(design §7R.7).

링크 색인·백링크·그래프·점검은 저장하지 않는 계산 결과다(원본은 페이지 파일, K7R-2). 페이지 id는
위키 폴더 기준 POSIX 경로에서 확장자를 뺀 것이다(예 `decisions/api-version`).

링크 원문 범위(`WikiLink.start`·`end`)의 단위는 **UTF-16 코드 단위**다 — 웹이 받은 본문 문자열을
그대로 `slice`할 수 있게 서버가 바꿔서 준다(design §7R.1.3).
"""

from pydantic import Field

from agent_console_contracts._base import ContractModel, JsonObject, NonEmptyStr
from agent_console_contracts.common import LabelDisplayTarget, SpaceRef
from agent_console_contracts.definitions import Issue

from ._rules import WikiDefinition, WikiRulesDefinition, WikiSyntax, WikiTemplateVariable


class WikiIssue(Issue):
    """위키 이슈(파싱·쓰기 규칙·점검·규칙 검사). `Issue`에 페이지·줄·규칙 위치를 더한다.

    `Issue.path`는 그대로 JSON 포인터(규칙 문서·설정 기준 위치)이고, 페이지 경로는 `page`에 둔다.
    알려진 코드는 `KnownIssueCodes`의 `wiki.*`(열린 문자열). 값 원문(비밀 의심 값)은 담지 않는다.
    """

    # 설계 표의 `path?`를 `page`로 둔 까닭: 두 뜻(포인터·페이지 경로)이 한 필드에 섞이지 않게
    # (design §7R.7 `[7R.3 구현]`).

    page: str | None = Field(default=None, description="페이지 경로(페이지 하나에 걸린 이슈).")
    line: int | None = Field(default=None, ge=1, description="그 페이지의 줄 번호(1부터).")
    rule_id: str | None = Field(
        default=None, description="이슈를 낸 쓰기·점검 규칙 id(기본 점검이면 null)."
    )


# ---------------------------------------------------------------- 화면 정보


class WikiCapabilities(ContractModel):
    """켜진 연동에 따라 쓸 수 있는 기능(포트 유무로 계산)."""

    history: bool = Field(default=False, description="페이지 기록·되돌리기(기록 저장소 있음).")
    search: bool = Field(default=False, description="검색(검색 색인 있음, 저하 포함).")
    runs: bool = Field(default=False, description="에이전트 쓰기(실행 연동 있음).")
    rules_library: bool = Field(
        default=False, description="공용 구성의 위키 규칙 편집(라이브러리 공간 있음)."
    )
    import_export: bool = Field(default=False, description="zip 가져오기·내보내기.")


class WikiLimits(ContractModel):
    """위키 한도(설치자 옵션)."""

    max_page_bytes: int = Field(ge=1, description="페이지 하나의 본문 크기 상한(바이트).")
    max_pages: int = Field(ge=1, description="위키 하나의 페이지 수 상한.")
    graph_max_nodes: int = Field(ge=1, description="그래프 한 번에 보이는 칸 수 상한.")


class WikiInfo(ContractModel):
    """`GET /wiki/info?project=`: 위키 화면 정보(웹이 모듈 id를 몰라도 켜짐·한도를 안다)."""

    pages_root: str = Field(
        default="",
        description=(
            "페이지 폴더의 부모(프로젝트 폴더 기준 상대 경로, 예 `.agent-console/wiki-pages`)."
        ),
    )
    capabilities: WikiCapabilities = Field(default_factory=WikiCapabilities)
    limits: WikiLimits
    writable: bool | None = Field(
        default=None,
        description=(
            "(1.1.0) 이 공간에 쓸 수 있나(공간 `config_writable`). false면 웹은 읽기 전용으로 "
            "그린다(쓰기는 409 `project.config_readonly`·`wiki.config_readonly`). null = 옛 서버 "
            "또는 알 수 없음(쓸 수 있다고 본다)."
        ),
    )
    rules_kind: str | None = Field(
        default=None,
        description=(
            "(1.2.0) 위키 규칙 정의 종류 이름(설치자 데이터, 기본 `wiki-rules`). 웹이 복사·리소스 "
            "종류 목록에서 규칙 종류를 고를 때 쓴다(공용 규칙을 따로 읽지 않는다). null = 옛 서버."
        ),
    )
    issues: list[WikiIssue] = Field(
        default_factory=list,
        description="공간 수준 이슈(예: `wiki.spaces_unavailable`·`wiki.search_degraded`).",
    )


# ---------------------------------------------------------------- 쓴 주체·기록


class WikiAuthor(ContractModel):
    """페이지를 쓴 쪽. `kind`는 열린 문자열(알려진 값 `KnownWikiAuthorKinds`)."""

    kind: NonEmptyStr = Field(description="user·agent·system·external(열린 문자열).")
    agent_id: str | None = None
    node_id: str | None = None
    node_path: list[str] = Field(
        default_factory=list, description="중첩 팀 안의 노드 경로(바깥 → 안)."
    )
    run_id: str | None = None
    root_run_id: str | None = None
    graph_id: str | None = None
    label: str | None = Field(
        default=None,
        description=(
            "기록 시점 이름(에이전트 정의 이름·노드 id·동작 이름 등). 기록할 때 채워 저장하므로 "
            "지운·바뀐 에이전트도 그때 이름이 남는다. null = 없음(웹은 agent_id → kind 라벨)."
        ),
    )


class WikiPageVersion(ContractModel):
    """페이지 기록 한 줄(`GET …/history`). 지우기도 버전이고 본문은 지우기 직전 해시를 가리킨다."""

    version: int = Field(ge=1)
    op: NonEmptyStr = Field(description="동작(열린 문자열, 알려진 값 `KnownWikiVersionOps`).")
    sha256: str = Field(description="본문 sha256(16진수).")
    bytes: int = Field(ge=0)
    author: WikiAuthor
    message: str | None = None
    at: float = Field(description="유닉스 초.")
    from_: str | None = Field(
        default=None, alias="from", description="옮겨 온 옛 경로(op `move_in`일 때)."
    )
    to: str | None = Field(default=None, description="옮겨 간 새 경로(op `move_out`일 때).")


class WikiChange(WikiPageVersion):
    """최근 변경 한 줄(`GET …/changes`·`GET /wiki/changes`): 기록에 위키 id·페이지 경로를 더한다."""

    wiki: NonEmptyStr = Field(description="위키 id(정의가 지워진 위키도 id로 나온다).")
    path: NonEmptyStr


class WikiHistoryPage(ContractModel):
    """`GET …/pages/{path}/history` 응답. 버전 번호는 다시 매기지 않아 빈 번호가 있을 수 있다."""

    items: list[WikiPageVersion] = Field(default_factory=list, description="최근 것부터.")
    pruned: bool = Field(
        default=False,
        description="보관 수를 넘어 지운 버전이 있다(그 버전은 `wiki.version_not_found`).",
    )


class WikiChangePage(ContractModel):
    """`GET /wiki/wikis/{wiki}/changes?limit=&cursor=&author_run=` 응답(최근 것부터)."""

    items: list[WikiChange] = Field(default_factory=list)
    next_cursor: str | None = Field(default=None, description="다음 쪽 커서(없으면 끝).")


# ---------------------------------------------------------------- 링크·페이지


class WikiLink(ContractModel):
    """페이지 안 링크 하나(원문 범위 + 해석 결과)."""

    start: int = Field(ge=0, description="원문 시작(UTF-16 코드 단위, 본문 문자열 기준).")
    end: int = Field(ge=0, description="원문 끝(UTF-16 코드 단위, 제외).")
    raw: str = Field(description="링크 원문 그대로.")
    kind: NonEmptyStr = Field(description="링크 규칙 종류(열린 문자열, `KnownWikiLinkKinds`).")
    rule_id: NonEmptyStr = Field(description="이 링크를 찾은 링크 규칙 id.")
    target: str | None = Field(default=None, description="링크가 적은 대상 문자열.")
    label: str = Field(
        default="",
        description=(
            "링크 글자. 서버가 늘 채운다(패턴의 label 묶음 → 없으면 target, 마크다운 링크는 링크 "
            "글자 → 비면 href)."
        ),
    )
    anchor: str | None = Field(default=None, description="절 이름(`#` 뒤).")
    resolved: str | None = Field(default=None, description="찾은 페이지 경로(못 찾으면 null).")
    broken: bool = Field(default=False, description="대상 페이지가 없다(스킴 링크는 false).")
    outside: bool = Field(
        default=False,
        description="위키 폴더 밖을 가리키는 상대 링크(`resolved` null, `broken` false).",
    )
    suggested_path: str | None = Field(
        default=None,
        description=(
            "끊긴 링크에서 만들 페이지 경로 제안(위키 폴더 기준, 확장자 없음, 경로 규칙에 맞을 "
            "때만). 해석 순서에 path·relative_path가 없으면 null."
        ),
    )
    status: NonEmptyStr = Field(
        default="ok",
        description=(
            "링크 상태(열린 문자열, `KnownWikiLinkStatuses`, 서버가 늘 채움). 우선순위 scheme > "
            "outside > broken > ok. 웹은 이 값만 본다."
        ),
    )
    scheme_target: LabelDisplayTarget | None = Field(
        default=None,
        description="링크 스킴이면 열 화면(역할 + id, 웹 경로 없음). `id_from`은 풀린 id 값이다.",
    )


class WikiBacklink(ContractModel):
    """이 페이지를 가리키는 페이지 하나."""

    path: NonEmptyStr
    title: str = ""
    count: int = Field(default=1, ge=1, description="그 페이지 안 링크 수.")


class WikiHeading(ContractModel):
    """페이지 안 제목 하나(절 읽기·목차용)."""

    level: int = Field(ge=1, le=6)
    text: str
    line: int = Field(ge=1, description="줄 번호(1부터).")


class WikiPageSummary(ContractModel):
    """페이지 목록 한 줄(본문 없음)."""

    path: NonEmptyStr = Field(description="페이지 경로(위키 폴더 기준, 확장자 없음).")
    title: str = Field(default="", description="문법의 제목 출처 순서로 정한 제목.")
    tags: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    bytes: int = Field(default=0, ge=0)
    updated_at: float | None = Field(
        default=None, description="마지막 변경(유닉스 초, 모르면 null)."
    )
    updated_by: WikiAuthor | None = Field(
        default=None, description="마지막으로 쓴 쪽(기록 없으면 null)."
    )
    links_out: int = Field(default=0, ge=0)
    backlinks: int = Field(default=0, ge=0)
    broken_links: int = Field(default=0, ge=0)
    orphan: bool = Field(
        default=False, description="들어오는 링크가 없다(고아 점검 제외 경로 반영)."
    )
    home: bool = Field(default=False, description="위키의 첫 페이지다.")
    issues: list[WikiIssue] = Field(default_factory=list)


class WikiPageList(ContractModel):
    """`GET /wiki/wikis/{wiki}/pages?prefix=&tag=` 응답. 트리는 웹이 경로로 만든다."""

    items: list[WikiPageSummary] = Field(default_factory=list)
    truncated: bool = Field(default=False, description="상한을 넘어 일부만 실었다.")
    total: int | None = Field(
        default=None, ge=0, description="실제 페이지 파일 수(잘렸을 때, 아니면 null)."
    )


class WikiPageView(ContractModel):
    """`GET /wiki/wikis/{wiki}/pages/{path}`: 페이지 하나(본문·링크·백링크).

    `ETag` = `content_hash`.
    """

    page: WikiPageSummary
    content: str = Field(description="본문 원문(머리말 포함).")
    content_hash: str = Field(description="본문 sha256(16진수). 쓰기 `If-Match`에 쓴다.")
    front_matter: JsonObject = Field(
        default_factory=dict, description="읽은 머리말(깨졌으면 빈 객체)."
    )
    headings: list[WikiHeading] = Field(default_factory=list)
    links: list[WikiLink] = Field(default_factory=list)
    backlinks: list[WikiBacklink] = Field(default_factory=list)
    issues: list[WikiIssue] = Field(default_factory=list)


# ---------------------------------------------------------------- 위키·규칙 요약


class WikiRuleRef(ContractModel):
    """위키가 쓰는 위키 규칙 하나(순서대로)."""

    id: NonEmptyStr
    name: str = ""
    missing: bool = Field(default=False, description="그 공간에 없는 규칙(`wiki.rules_missing`).")


class WikiRuleEntry(ContractModel):
    """합친 규칙의 항목 하나(쓰기 규칙·점검 규칙·페이지 틀). 같은 id로 빠진 항목은 넣지 않는다."""

    kind: NonEmptyStr = Field(
        description="write·lint·template(열린 문자열, `KnownWikiRuleEntryKinds`)."
    )
    id: NonEmptyStr = Field(description="항목 id.")
    rule_id: NonEmptyStr = Field(description="이 항목을 준 위키 규칙 id.")
    label: str = Field(default="", description="쓰기·점검 규칙의 안내 문장 또는 틀의 표시 이름.")
    action: str | None = Field(default=None, description="쓰기 규칙의 동작(그 밖은 null).")
    severity: str | None = Field(default=None, description="점검 규칙의 심각도(그 밖은 null).")
    applies_to: list[str] | None = Field(
        default=None,
        description=(
            "(1.2.0) 쓰기 규칙의 적용 경로 글롭(빈 목록 = 모든 페이지). 그 밖의 항목·옛 서버는 "
            "null."
        ),
    )
    path: str | None = Field(
        default=None,
        description="(1.2.0) 페이지 틀의 경로 틀(예 `decisions/{slug}`). 없거나 그 밖은 null.",
    )
    title: str | None = Field(
        default=None,
        description=(
            "(1.2.0) 페이지 틀의 표시 이름 원문(비었으면 null — `label`은 id로 대신 채운다). "
            "그 밖의 항목은 null."
        ),
    )


class WikiRulesSummary(ContractModel):
    """위키가 쓰는 규칙을 합친 결과 요약(규칙 탭)."""

    rules: list[WikiRuleRef] = Field(default_factory=list, description="위키의 규칙 순서 그대로.")
    instructions: str = Field(default="", description="합친 지침 본문(규칙 이름 머리 줄 포함).")
    write_rules: int = Field(default=0, ge=0, description="합친 쓰기 규칙 수.")
    lint_rules: int = Field(default=0, ge=0, description="합친 점검 규칙 수.")
    page_templates: int = Field(default=0, ge=0, description="합친 페이지 틀 수.")
    entries: list[WikiRuleEntry] = Field(
        default_factory=list, description="합친 항목(쓰기 → 점검 → 틀, 규칙 순서대로)."
    )


class WikiRuleCounts(ContractModel):
    """위키 규칙 하나의 항목 수."""

    write: int = Field(default=0, ge=0)
    lint: int = Field(default=0, ge=0)
    templates: int = Field(default=0, ge=0)


class WikiRef(ContractModel):
    """위키 하나를 가리키는 짧은 표지."""

    id: NonEmptyStr
    name: str = ""


class WikiRulesListItem(ContractModel):
    """`GET /wiki/rules` 항목: 위키 규칙 하나(본문 없음)."""

    id: NonEmptyStr
    name: str = ""
    description: str = ""
    counts: WikiRuleCounts = Field(default_factory=WikiRuleCounts)
    has_instructions: bool = Field(default=False, description="지침 본문이 있다.")
    used_by: list[WikiRef] = Field(
        default_factory=list,
        description="이 규칙을 쓰는 위키(프로젝트 공간에서만 채움, 공용은 늘 빈 목록).",
    )
    issues: list[WikiIssue] = Field(default_factory=list)


class WikiRulesView(ContractModel):
    """`GET /wiki/rules/{id}`: 위키 규칙 하나 + 쓰는 위키 + 검사 이슈."""

    rules: WikiRulesDefinition
    version_hash: str = Field(description="정의 버전(저장 `If-Match`에 쓴다).")
    used_by: list[WikiRef] = Field(
        default_factory=list, description="이 규칙을 쓰는 위키(공용은 늘 빈 목록)."
    )
    issues: list[WikiIssue] = Field(default_factory=list)


class WikiSummary(ContractModel):
    """`GET /wiki/wikis` 항목: 이 공간의 위키 하나."""

    id: NonEmptyStr
    name: str = ""
    description: str = ""
    home: str | None = None
    rules: list[WikiRuleRef] = Field(default_factory=list, description="쓰는 규칙(순서대로).")
    pages: int = Field(default=0, ge=0, description="페이지 수.")
    broken_links: int = Field(default=0, ge=0, description="끊긴 링크 수.")
    orphans: int = Field(default=0, ge=0, description="고아 페이지 수.")
    lint_counts: dict[str, int] = Field(
        default_factory=dict,
        description="점검 이슈 수(심각도 → 수, 기본 점검·점검 규칙·쓰기 규칙 다시 보기 포함).",
    )
    updated_at: float | None = Field(default=None, description="최근 페이지 변경(유닉스 초).")
    updated_by: WikiAuthor | None = Field(default=None, description="최근 변경을 쓴 쪽.")
    directory: str = Field(default="", description="페이지 폴더(프로젝트 폴더 기준 상대 경로).")
    issues: list[WikiIssue] = Field(default_factory=list)


class WikiView(ContractModel):
    """`GET /wiki/wikis/{wiki}`: 위키 정의 + 합친 규칙 요약 + 이슈."""

    wiki: WikiDefinition
    version_hash: str = Field(description="정의 버전(저장 `If-Match`에 쓴다).")
    directory: str = Field(default="", description="페이지 폴더(프로젝트 폴더 기준 상대 경로).")
    rules: WikiRulesSummary = Field(default_factory=WikiRulesSummary)
    issues: list[WikiIssue] = Field(default_factory=list)


class EffectiveWikiSyntax(ContractModel):
    """`GET …/syntax`: 병합한 위키 문법과 값마다 출처.

    `sources` 키 = 문법 문서 기준 위치(예: `/links`), 값 = 출처(열린 문자열: `default`·`settings`·
    `rules:<규칙 id>`). 기본 문법이 꺼졌으면 `default`는 나오지 않는다.
    """

    syntax: WikiSyntax = Field(default_factory=WikiSyntax)
    sources: dict[str, str] = Field(default_factory=dict)
    empty: bool = Field(
        default=False, description="링크 규칙이 비었다(그래프·백링크 탭은 '링크 문법 없음')."
    )
    issues: list[WikiIssue] = Field(default_factory=list, description="문법 컴파일 이슈.")


class WikiPageTemplateInfo(ContractModel):
    """`GET …/templates` 항목: 합친 페이지 틀 하나(어느 규칙에서 왔는지 + 틀 본문).

    틀 필드(`id`·`title`·`file`·`path`)는 규칙의 `WikiPageTemplate`과 같다(보기라 폼 모델이 아니다).
    """

    id: NonEmptyStr
    title: str | None = None
    file: NonEmptyStr
    path: str | None = Field(default=None, description="새 페이지 경로 틀.")
    variables: list[WikiTemplateVariable] = Field(
        default_factory=list,
        description="선언 변수 + 틀 본문·경로 틀이 쓰는 이름의 합집합(앱이 채우는 것은 builtin).",
    )
    rule_id: NonEmptyStr = Field(description="이 틀을 준 위키 규칙 id.")
    content: str = Field(default="", description="틀 본문(치환 전).")


# ---------------------------------------------------------------- 검색·그래프·점검


class WikiTextRange(ContractModel):
    """문자열 안 범위(UTF-16 코드 단위, 끝 제외)."""

    start: int = Field(ge=0)
    end: int = Field(ge=0)


class WikiSearchHit(ContractModel):
    """검색 결과 하나."""

    path: NonEmptyStr
    title: str = ""
    snippet: str = Field(default="", description="맞은 곳 주변 조각(비밀 가림 뒤 자름).")
    score: float | None = Field(default=None, description="점수(색인마다 다름, 큰 것이 앞).")
    marks: list[WikiTextRange] = Field(
        default_factory=list, description="조각 안 강조 범위(조각 문자열 기준 UTF-16)."
    )


class WikiSearchResult(ContractModel):
    """`GET …/search?q=&prefix=&tag=&limit=` 응답."""

    items: list[WikiSearchHit] = Field(default_factory=list)
    backend: str = Field(default="", description="쓴 검색 방식 id(열린 문자열).")
    degraded: bool = Field(
        default=False, description="느린 대체 방식으로 찾았다(`wiki.search_degraded`)."
    )
    truncated: bool = False


class WikiGraphNode(ContractModel):
    """그래프 칸 하나(페이지, 끊긴 대상, 또는 스킴 링크 대상)."""

    path: NonEmptyStr = Field(description="페이지 경로(끊긴 대상이면 링크가 적은 대상).")
    title: str = ""
    broken: bool = Field(default=False, description="없는 페이지(끊긴 링크의 대상).")
    orphan: bool = Field(default=False, description="들어오는 링크가 없는 페이지.")
    scheme: str | None = Field(default=None, description="스킴 링크 대상이면 그 접두.")
    scheme_target: LabelDisplayTarget | None = Field(
        default=None,
        description=(
            "(1.2.0) 스킴 링크 대상이면 열 화면(`WikiLink.scheme_target`과 같은 모양, `id_from` = "
            "풀린 id 값). 접두 뒤가 비었거나 페이지·끊긴 대상·옛 서버는 null."
        ),
    )
    home: bool = Field(default=False, description="위키의 첫 페이지.")
    depth: int | None = Field(default=None, ge=0, description="중심에서의 거리(전체 보기는 null).")


class WikiGraphEdge(ContractModel):
    """그래프 연결 하나(같은 두 페이지 사이 링크는 하나로 묶고 수를 센다)."""

    from_: NonEmptyStr = Field(alias="from")
    to: NonEmptyStr
    count: int = Field(default=1, ge=1)


class WikiGraph(ContractModel):
    """`GET …/graph?center=&depth=&limit=` 응답(center 없음 = 전체, 상한 `graph_max_nodes`)."""

    nodes: list[WikiGraphNode] = Field(default_factory=list)
    edges: list[WikiGraphEdge] = Field(default_factory=list)
    truncated: bool = Field(default=False, description="상한을 넘어 일부 칸만 실었다.")
    total: int | None = Field(default=None, ge=0, description="자르기 전 칸 수(모르면 null).")


class WikiLintReport(ContractModel):
    """`GET …/lint` 응답: 기본 점검 + 점검 규칙 이슈."""

    issues: list[WikiIssue] = Field(default_factory=list)
    pages: int = Field(default=0, ge=0, description="점검한 페이지 수.")
    generated_at: float = Field(default=0.0, description="점검한 시각(유닉스 초).")
    counts: dict[str, int] = Field(default_factory=dict, description="심각도 → 이슈 수.")
    partial: bool = Field(
        default=False,
        description=(
            "(1.2.0) 일부 페이지를 점검하지 못했다(그 페이지는 `skipped`, 나머지 결과는 그대로). "
            "페이지마다 `wiki.lint_failed` 이슈도 하나씩 있다."
        ),
    )
    skipped: list[str] = Field(
        default_factory=list,
        description="(1.2.0) 점검하지 못한 페이지 경로(경로 순). `pages`에는 들어 있다.",
    )
    enabled_checks: list[str] | None = Field(
        default=None,
        description=(
            "(1.2.0) 이번 점검에서 켜진 점검 이름: 켜진 기본 점검(`KnownWikiLintCodes`, 문법 "
            "`lint.builtin`) → 점검 규칙이 있으면 `lint_rules` → 쓰기 규칙 다시 보기가 켜졌으면 "
            "`write_rules`(열린 문자열, `KnownWikiLintChecks`). null = 옛 서버."
        ),
    )


# ---------------------------------------------------------------- WS


class WikiChanged(ContractModel):
    """WS `wiki.changed` payload: 위키 페이지가 바뀜(본문 없음).

    화면은 그 페이지를 다시 불러온다.
    """

    space: SpaceRef = Field(default_factory=SpaceRef, description="그 위키의 공간.")
    wiki_id: NonEmptyStr
    paths: list[str] = Field(
        default_factory=list, description="바뀐 페이지 경로(빈 목록 = 정의만)."
    )
    deleted: bool = Field(default=False, description="페이지(또는 위키 정의)를 지웠다.")
    external: bool = Field(default=False, description="앱 밖에서 고친 것을 감지했다.")


__all__ = [
    "EffectiveWikiSyntax",
    "WikiAuthor",
    "WikiBacklink",
    "WikiCapabilities",
    "WikiChange",
    "WikiChangePage",
    "WikiChanged",
    "WikiGraph",
    "WikiGraphEdge",
    "WikiGraphNode",
    "WikiHeading",
    "WikiHistoryPage",
    "WikiInfo",
    "WikiIssue",
    "WikiLimits",
    "WikiLink",
    "WikiLintReport",
    "WikiPageList",
    "WikiPageSummary",
    "WikiPageTemplateInfo",
    "WikiPageVersion",
    "WikiPageView",
    "WikiRef",
    "WikiRuleCounts",
    "WikiRuleEntry",
    "WikiRuleRef",
    "WikiRulesListItem",
    "WikiRulesSummary",
    "WikiRulesView",
    "WikiSearchHit",
    "WikiSearchResult",
    "WikiSummary",
    "WikiTextRange",
    "WikiView",
]
