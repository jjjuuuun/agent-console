"""Agent Console 위키 핵심 라이브러리(design §7R): 문법·페이지 파싱·링크 해석·색인·페이지 파일.

서버·실행·프로젝트를 모르고 페이지 원문(글·바이트)과 계약 모델(`agent_console_contracts.wiki`),
주입한 페이지 파일 접근(`WikiPages`)만 다룬다. 링크 문법·머리말 키·제목 출처·확장자·대소문자·링크
스킴·기본 점검 심각도는 모두 데이터다(패키지 기본 `data/default_syntax.yaml` → 사용자 설정 → 위키
규칙).

공개 API:
    문법: ``load_default_syntax()``·``merge_syntax(*layers)``·``effective_syntax(settings, rules)``·
        ``compile_syntax(effective) -> CompiledWikiSyntax``
    파싱: ``parse_page(path, text, syntax) -> ParsedPage``(머리말·제목·태그·별칭·제목들·링크 원문
        위치)
    색인: ``build_index(pages, syntax, home=) -> WikiIndex``(해석·백링크·끊긴 링크·고아·제목 겹침),
        ``neighborhood(index, center, depth, limit) -> WikiGraph``
    고치기: ``rewrite_links(text, links, page=, old=, new=, syntax=) -> RewriteResult``(링크 대상만)
    링크 넣기: ``render_link_text(syntax, from_page=, target=, label=, rule_id=) -> WikiLinkText``
    판단 대상: ``page_facts``·``write_subject``·``lint_subject``(쓰기·점검 규칙 조건이 읽는 값)
    검색 강조: ``search_marks(snippet, query) -> list[WikiTextRange]``(UTF-16)
    검색 색인(X48): 프로토콜 ``WikiSearchIndex``·``ScanSearchIndex``·``search_document``·
        ``sync_search_index``, 플러그인 ``load_search_plugins``·``builtin_search_factories``,
        하위 모듈 ``sqlite``(``SqliteFtsSearchIndex``, FTS5 trigram)
    규칙: ``merge_rules(rule_ids, documents) -> EffectiveWikiRules``(지침 이어 붙임·항목 출처),
        ``check_rules(document)``, ``load_wiki_rules(store, ids, kind=)``, ``definition_kinds(...)``
    쓰기 판단: ``check_write(rules, subject, content=)``·``compile_write_rules``, 비밀
        ``WikiSecretPolicy``, X50 ``WikiWriteCheck``
    점검: ``lint(index, rules, now=, times=, read=) -> WikiLintReport``
    틀: ``render_page_template(template, content, title=, values=, today=)``·``slugify``
    기록(X49): 프로토콜 ``WikiHistory``·``HistoryEntry``·``InMemoryWikiHistory``
    저장소: ``WikiRepository(pages, wiki_id=, syntax=, rules=, history=, search=, checks=, secrets=,
        limits=, clock=)``(읽기·쓰기·미리보기·옮기기·지우기·되돌리기·외부 변경 ``scan``·점검)
    도구 묶음: ``WikiToolkit(wikis, access=, author=, text=, on_event=, write_budget=).specs()``
        (런타임을 모름, 도구 7개·사유 코드·본문 없는 이벤트), 지침 ``WikiToolkit.instructions()``·
        ``wiki_instructions``, 접근 판단 ``wiki_allowed``·``wikis_for``·``default_wiki``, 문구
        ``load_tool_text``(``data/tool_text.yaml``)
    zip: ``export_zip(repository)``·``import_zip(repository, data, policy=, dry_run=)``
    페이지 파일: 프로토콜 ``WikiPages``·``LocalWikiPages(root, reserved=)``·``read_pages``,
        경로 ``check_page_path``·``page_path_for_file``·``file_for_page``
    예외: ``WikiError``(``code``)와 하위 ``WikiPathError``·``WikiPageNotFoundError``·
        ``WikiPageExistsError``·``WikiLinkInsertUnavailableError``·``WikiConflictError``·
        ``WikiTooLargeError``·``WikiRuleRejectedError``·``WikiSecretRejectedError``·
        ``WikiHistoryUnavailableError``·``WikiVersionNotFoundError``·``WikiTemplateNotFoundError``·
        ``WikiZipFormatError``
    시험: 하위 모듈 ``testing``(``MemoryWikiPages``·``WikiPagesContractTests``·
        ``WikiSearchContractTests``·``WikiHistoryContractTests``·``FakeClock``)
"""

from __future__ import annotations

from ._compiled import (
    KNOWN_LINK_KINDS,
    KNOWN_RESOLVERS,
    KNOWN_TITLE_SOURCES,
    CompiledLinkRule,
    CompiledWikiSyntax,
    compile_syntax,
)
from ._errors import (
    WikiConflictError,
    WikiError,
    WikiHistoryUnavailableError,
    WikiLinkInsertUnavailableError,
    WikiPageExistsError,
    WikiPageNotFoundError,
    WikiPathError,
    WikiRuleRejectedError,
    WikiSecretRejectedError,
    WikiTemplateNotFoundError,
    WikiTooLargeError,
    WikiVersionNotFoundError,
    WikiZipFormatError,
)
from ._glob import check_glob, glob_match
from ._history import HistoryEntry, HistorySummary, InMemoryWikiHistory, WikiHistory
from ._index import IndexedLink, WikiIndex, build_index, neighborhood, page_facts
from ._kinds import RULES_CONTENT_FIELD, definition_kinds
from ._linktext import render_link_text
from ._lint import PageTimes, lint
from ._marks import query_terms, search_marks
from ._pages import LocalWikiPages, PageFile, ParseCache, WikiPages, read_pages
from ._parse import PageText, ParsedLink, ParsedPage, decode_page, parse_page
from ._paths import check_page_path, file_for_page, page_path_for_file, split_extension
from ._repository import PageContent, WikiRepository, WikiRepositoryLimits, WriteOutcome
from ._rewrite import RewriteResult, rewrite_links
from ._ruleset import (
    EffectiveWikiRules,
    RulesDocument,
    Sourced,
    check_rules,
    default_operator_map,
    load_wiki_rules,
    merge_rules,
    rules_text,
)
from ._search import (
    ScanSearchIndex,
    SearchLimits,
    SearchSyncResult,
    WikiSearchDocument,
    WikiSearchIndex,
    search_document,
    sync_search_index,
)
from ._search_plugins import (
    SEARCH_INDEX_GROUP,
    SearchIndexFactory,
    builtin_search_factories,
    load_search_plugins,
    new_search_registry,
    register_builtin_search,
)
from ._subjects import lint_subject, write_subject
from ._syntax import (
    DEFAULT_SYNTAX_RESOURCE,
    SyntaxLayer,
    effective_syntax,
    load_default_syntax,
    merge_syntax,
    rules_source,
)
from ._template import render_page_template, slugify
from ._text import Utf16Map, to_utf16
from ._toolkit import (
    TOOL_TEXT_RESOURCE,
    WikiToolkit,
    WikiToolOutcome,
    WikiToolSpec,
    WikiToolTarget,
    WikiToolText,
    WikiWriteBudget,
    WriteBudget,
    access_wikis,
    default_wiki,
    format_author,
    format_time,
    load_tool_text,
    replace_section,
    section_span,
    wiki_allowed,
    wiki_instructions,
    wiki_ops,
    wikis_for,
)
from ._transfer import export_zip, import_zip
from ._writecheck import (
    CompiledWriteRules,
    SecretRulesScanner,
    SecretScan,
    WikiSecretPolicy,
    WikiSecretScanner,
    WikiWriteCheck,
    WriteDecision,
    check_write,
    compile_write_rules,
    run_write_checks,
)

__all__ = [
    "DEFAULT_SYNTAX_RESOURCE",
    "KNOWN_LINK_KINDS",
    "KNOWN_RESOLVERS",
    "KNOWN_TITLE_SOURCES",
    "RULES_CONTENT_FIELD",
    "SEARCH_INDEX_GROUP",
    "TOOL_TEXT_RESOURCE",
    "CompiledLinkRule",
    "CompiledWikiSyntax",
    "CompiledWriteRules",
    "EffectiveWikiRules",
    "HistoryEntry",
    "HistorySummary",
    "InMemoryWikiHistory",
    "IndexedLink",
    "LocalWikiPages",
    "PageContent",
    "PageFile",
    "PageText",
    "PageTimes",
    "ParseCache",
    "ParsedLink",
    "ParsedPage",
    "RewriteResult",
    "RulesDocument",
    "ScanSearchIndex",
    "SearchIndexFactory",
    "SearchLimits",
    "SearchSyncResult",
    "SecretRulesScanner",
    "SecretScan",
    "Sourced",
    "SyntaxLayer",
    "Utf16Map",
    "WikiConflictError",
    "WikiError",
    "WikiHistory",
    "WikiHistoryUnavailableError",
    "WikiIndex",
    "WikiLinkInsertUnavailableError",
    "WikiPageExistsError",
    "WikiPageNotFoundError",
    "WikiPages",
    "WikiPathError",
    "WikiRepository",
    "WikiRepositoryLimits",
    "WikiRuleRejectedError",
    "WikiSearchDocument",
    "WikiSearchIndex",
    "WikiSecretPolicy",
    "WikiSecretRejectedError",
    "WikiSecretScanner",
    "WikiTemplateNotFoundError",
    "WikiTooLargeError",
    "WikiToolOutcome",
    "WikiToolSpec",
    "WikiToolTarget",
    "WikiToolText",
    "WikiToolkit",
    "WikiVersionNotFoundError",
    "WikiWriteBudget",
    "WikiWriteCheck",
    "WikiZipFormatError",
    "WriteBudget",
    "WriteDecision",
    "WriteOutcome",
    "access_wikis",
    "build_index",
    "builtin_search_factories",
    "check_glob",
    "check_page_path",
    "check_rules",
    "check_write",
    "compile_syntax",
    "compile_write_rules",
    "decode_page",
    "default_operator_map",
    "default_wiki",
    "definition_kinds",
    "effective_syntax",
    "export_zip",
    "file_for_page",
    "format_author",
    "format_time",
    "glob_match",
    "import_zip",
    "lint",
    "lint_subject",
    "load_default_syntax",
    "load_search_plugins",
    "load_tool_text",
    "load_wiki_rules",
    "merge_rules",
    "merge_syntax",
    "neighborhood",
    "new_search_registry",
    "page_facts",
    "page_path_for_file",
    "parse_page",
    "query_terms",
    "read_pages",
    "register_builtin_search",
    "render_link_text",
    "render_page_template",
    "replace_section",
    "rewrite_links",
    "rules_source",
    "rules_text",
    "run_write_checks",
    "search_document",
    "search_marks",
    "section_span",
    "slugify",
    "split_extension",
    "sync_search_index",
    "to_utf16",
    "wiki_allowed",
    "wiki_instructions",
    "wiki_ops",
    "wikis_for",
    "write_subject",
]
