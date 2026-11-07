# agent-console-wiki

Agent Console 위키 핵심 라이브러리. 서버·실행·프로젝트를 모르고, **페이지 원문(마크다운 파일)**과
계약 모델(`agent_console_contracts.wiki`), 주입한 페이지 파일 접근(`WikiPages`)만 다룬다.

- **링크 문법은 데이터다.** 패키지 기본(`data/default_syntax.yaml` — `[[대상|라벨]]` 패턴, 상대 경로 마크다운
  링크, 머리말 역할, 제목 출처 순서, 확장자, 대소문자, 기본 점검 심각도) → 사용자 설정 `wiki.syntax` → 위키
  규칙 `syntax`(위키의 규칙 순서) 차례로 덮는다. None은 "상속", 빈 목록은 "이 층에서는 없음". 첫 단계 객체
  값(`front_matter`·`lint`)은 그 안의 키 단위로, 나머지는 통째로 바꾼다. 값마다 출처(`default`·`settings`·
  `rules:<id>`)가 `EffectiveWikiSyntax.sources`에 남는다. 기본 문법은 `WikiSettings.include_default_syntax:
  false`로 끈다(링크 0개 + `wiki.syntax_missing`).
- **코드가 뜻을 아는 것은 셋뿐이다**: 머리말 역할(`title`·`tags`·`aliases` — 어느 머리말 키인지는 데이터), 기본
  점검(`broken_link`·`orphan`·`duplicate_title` — 켜기·심각도는 데이터), 링크 대상 찾기(`path`·`title`·
  `alias`·`relative_path` — 순서·사용 여부는 데이터). 링크 패턴·머리말 키·폴더 이름·위키 이름은 코드에 없다.
- **원본은 파일이다.** `parse_page`가 머리말·제목·태그·별칭·제목들·링크 원문 위치를, `build_index`가 해석·
  백링크·끊긴 링크(만들 경로 제안)·바깥 링크·고아·제목 겹침을 읽을 때마다 계산한다(저장 안 함).
- **코드 블록·인라인 코드 안의 링크는 링크가 아니다.** 블록 구조는 markdown-it-py가, 인라인 영역 안의 코드
  조각·마크다운 링크 위치는 이 패키지가 원문에서 바로 읽는다(아래 "의존성").
- **위치 단위**: 라이브러리 안은 코드 포인트, 계약 보기(`WikiLink.start`·`end`, 검색 강조)는 UTF-16 코드
  단위(웹이 받은 문자열을 그대로 `slice`).
- **이름 바꾸기는 링크 대상 글자만 고친다**(`rewrite_links`). 렌더러로 다시 쓰지 않아 줄바꿈 종류·탭·서식이
  그대로다. 제목·별칭으로 이어진 링크는 고치지 않는다(옮겨도 그대로 이어짐).
- **경로 지킴**(`LocalWikiPages`): `..`·절대·드라이브·역슬래시·제어 문자·Windows 금지 문자·예약 이름·숨김
  (`.`로 시작) 거부, 심볼릭 링크·정션은 읽지도 쓰지도 않고 실제 경로가 폴더 안인지 한 번 더 본다. 쓰기는 같은
  폴더 임시 파일 + 원자적 바꾸기.

## 의존성: 무엇을 / 왜 / 대안

- **markdown-it-py**(MIT, 활발, 이미 `ac-sdd`가 씀): CommonMark 블록 파서(코드 블록·HTML 블록·문단 경계·제목).
  인라인 파싱은 끈다 — 인라인 토큰은 원문 위치를 주지 않고, 켜면 페이지 2,000개(20MB)에 약 10초가 걸려
  목표인 2초를 넘는다. 인라인 영역 안의 코드 조각·자동 링크·인라인 링크는 CommonMark 규칙 중 링크
  위치에 필요한 것만 원문에서 읽는다(참조 링크 `[글][이름]`은 읽지 않는다). 대안: mistune(원문 위치 약함),
  정규식만(코드 블록 오판), `mdit-py-plugins` 위키 링크 플러그인(패턴이 고정이라 사용자가 바꿀 수 없음).
- **ruamel.yaml**: 패키지 기본 문법 데이터와 페이지 머리말(safe 로드). 흔한 머리말(`키: 값`, `키: [값, 값]`)은
  YAML 읽기와 결과가 같은 빠른 길로 읽는다(평이한 글자만, 숫자·참거짓·날짜처럼 읽힐 수 있는 값은 YAML로).
- 사내: `agent-console-contracts`(모델·이슈 코드), `agent-console-safe-regex`(사용자 링크 패턴 — 시간·길이
  상한), `agent-console-text-template`(링크 넣기 틀·스킴 질의 틀 — 같은 안전 치환을 두 곳에 두지 않는다),
  `agent-console-secret-rules`(색인에 넣기 전 비밀 가리기), `agent-console-registry`(검색 색인 플러그인 로더),
  `agent-console-store`(경로 검사 `check_content_path`·원자적 쓰기 — 정의 본문과 같은 이름 규칙),
  `agent-console-conditions`(쓰기·점검 규칙 조건), `agent-console-secret-rules`(본문 비밀 검사),
  `agent-console-safe-zip`(zip 가져오기 안전 규칙 — 메모리와 한 벌).

## 설치

```bash
pip install agent-console-wiki
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-wiki
```

## 최소 사용 (서버 없이 폴더 → 백링크)

```python
>>> import tempfile
>>> from agent_console_wiki import (
...     LocalWikiPages, build_index, compile_syntax, effective_syntax, neighborhood, read_pages,
... )

>>> folder = tempfile.mkdtemp()
>>> pages = LocalWikiPages(folder)
>>> pages.write("start.md", "# 시작\n\n[[guide|안내]]와 [메모](notes/one.md)를 보세요.\n".encode())
>>> pages.write("guide.md", "---\ntitle: 안내서\n---\n처음으로: [[start]]. 코드 안 `[[가짜]]`는 링크가 아니다.\n".encode())
>>> pages.write("notes/one.md", "[[없는 페이지]]\n".encode())

>>> syntax = compile_syntax(effective_syntax())     # 패키지 기본 문법(끌 수 있음)
>>> parsed, issues = read_pages(pages, syntax)
>>> index = build_index(parsed, syntax, home="start")
>>> [(b.path, b.title) for b in index.backlinks("start")]
[('guide', '안내서')]
>>> [(link.raw, link.status, link.resolved) for link in index.page_links("start")]
[('[[guide|안내]]', 'ok', 'guide'), ('[메모](notes/one.md)', 'ok', 'notes/one')]
>>> [(link.status, link.suggested_path) for link in index.page_links("notes/one")]
[('broken', '없는 페이지')]
>>> sorted(index.orphans)
[]
>>> [(n.path, n.depth) for n in neighborhood(index, "start", 1).nodes]
[('start', 0), ('guide', 1), ('notes/one', 1)]

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

문법 바꾸기: `effective_syntax(settings, rules=[(규칙 id, 문법)])`에 사용자 설정(`WikiSettings`)과 위키 규칙
문법을 주거나, `merge_syntax(("default", ...), ("settings", {...}))`로 층을 직접 준다. 예를 들어
`{"links": [{"id": "paren", "kind": "pattern", "pattern": "\\(\\((?P<target>[^)]+)\\)\\)", "resolve": ["path"]}]}`
이면 `((대상))`이 링크다. 패턴에는 `target` 묶음이 있어야 하고 `label`·`anchor` 묶음은 선택이다.

이름 바꾸기: `rewrite_links(text, index.links[page], page=page, old="guide", new="docs/guide", syntax=syntax)`
가 그 페이지 본문의 링크 대상만 고친다(`page == old`면 옮기는 페이지 자신의 상대 링크를 새 위치 기준으로).
링크 넣기: `render_link_text(syntax, from_page=..., target=..., label=...)`(규칙 `insert` 틀, 없으면
`WikiLinkInsertUnavailableError`). 검색 강조: `search_marks(snippet, query)`(UTF-16 범위).
판단 대상(쓰기·점검 규칙 조건이 읽는 값): `index.facts(path)`·`write_subject`·`lint_subject` — 모양은 계약
`WIKI_WRITE_SUBJECT_PATHS`·`WIKI_LINT_SUBJECT_PATHS`와 같다.

이슈는 `WikiIssue`(페이지 `page`·줄 `line`·규칙 `rule_id`, 값 원문 없음): `wiki.front_matter_invalid`·
`parse_timeout`·`link_pattern_invalid`·`unknown_link_kind`·`syntax_missing`·`duplicate_rule_id`·
`invalid_glob`·`home_missing`·`too_many_pages`·`too_large`. 오류는 `WikiError.code`(`wiki.invalid_path`·
`page_not_found`·`page_exists`·`link_insert_unavailable`).

시험 도구 `agent_console_wiki.testing`: `MemoryWikiPages`(메모리 페이지 파일), `WikiPagesContractTests`
(자기 `WikiPages` 구현을 같은 의미로 시험하는 계약 묶음 — pytest 필요).

## 검색 색인

색인은 **다시 만들 수 있는 캐시**다(페이지 파일이 진실). 프로토콜 `WikiSearchIndex`(`update`·`remove`·
`rebuild`·`search`·`hashes`)와 두 구현: `ScanSearchIndex`(메모리에서 훑기, `scan`)와 하위 모듈
`agent_console_wiki.sqlite`의 `SqliteFtsSearchIndex(path, tokenizer="trigram")`(`sqlite-fts`, 표준 `sqlite3`
FTS5). 색인 파일 위치는 호출자가 준다(이 패키지는 고정하지 않는다). 질의의 모든 낱말이 경로·제목·태그·
별칭·본문에 부분 문자열로 있어야 한다(한국어 부분 일치). 조각은 **비밀을 가린 본문**에서 자르고(`redact`
생략 = `ac-secret-rules` 기본 규칙), `marks`는 조각 기준 UTF-16 범위다. FTS5·trigram이 없는 SQLite는
`unicode61`(앞부분 일치) → `scan` 순으로 내려가며 `degraded=True`(서버가 `wiki.search_degraded` 이슈로 알린다).
열 때 파일이 깨졌거나 설정이 다르면 버리고 다시 짓는다. 플러그인은 entry point
`agent_console.wiki_search_indexes`(`load_search_plugins`).

```python
>>> from agent_console_wiki import (
...     LocalWikiPages, ScanSearchIndex, compile_syntax, effective_syntax, parse_page,
...     search_document, sync_search_index,
... )
>>> import tempfile
>>> pages = LocalWikiPages(tempfile.mkdtemp())
>>> pages.write("a.md", "---\ntitle: 소개\n---\n이 위키는 팀의 약속을 적는다.\n".encode())
>>> syntax = compile_syntax(effective_syntax())
>>> text = pages.read("a.md").decode()
>>> doc = search_document(parse_page("a", text, syntax), text)
>>> index = ScanSearchIndex()            # 파일 없이. 파일 색인: SqliteFtsSearchIndex(경로)
>>> sync_search_index(index, [doc]).updated   # 바뀐 것만 쓴다(해시)
1
>>> hit = index.search("위키").items[0]
>>> (hit.path, hit.snippet, [(m.start, m.end) for m in hit.marks])
('a', '이 위키는 팀의 약속을 적는다.', [(2, 4)])

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

시험: `WikiSearchContractTests`(`make_index`만 채우면 자기 색인을 같은 의미로 시험), `make_search_document`.

## 저장소·규칙·점검·기록

- **규칙 합치기** `merge_rules(위키의 rules, 문서들)`: 지침 본문은 순서대로 이어 붙이고(규칙 이름 머리 줄 틀 =
  패키지 데이터 `data/rules_text.yaml`), 쓰기·점검 규칙·페이지 틀은 이어 붙인다(같은 id는 앞의 것 +
  `wiki.duplicate_rule_id`, 없는 규칙은 `wiki.rules_missing`). 항목마다 출처 규칙 id(`entries`). 정의 저장소에서
  읽기는 `load_wiki_rules(store, ids, kind=)`, 정의 종류는 `definition_kinds(wiki_kind=, wiki_dir=, ...)`(이름·
  폴더는 호출자 데이터). 저장 전 검사 `check_rules`(정규식·글롭·조건·모르는 동작·늘 거부·틀 파일·틀 변수).
- **쓰기 판단** `check_write`: `applies_to` 글롭 → `when` → `require`·`deny_patterns`(맞은 줄 번호) → `reject`
  /`warn`(모르는 값 = warn + `wiki.unknown_action`). 비밀 검사 `WikiSecretPolicy`(쓴 주체 종류별 off·warn·
  reject, 기본값 = 계약 `WikiSettings`), 보탬 검사 `WikiWriteCheck`.
- **점검** `lint`: 기본 점검 셋(심각도·끄기는 문법 데이터) + 점검 규칙 + 쓰기 규칙 다시 보기(`wiki.rule_violation`,
  `lint.write_rules: false`로 끔).
- **기록** `WikiHistory`(`record`·`list`·`get`·`read`·`latest`·`summaries`·`changes`·`prune`),
  `InMemoryWikiHistory`, 계약 묶음 `testing.WikiHistoryContractTests`(SQLite 구현 `sqlite.SqliteWikiHistory`는 아래).
- **저장소** `WikiRepository`: 쓰기(`if_hash`·새 페이지만·크기·개수 한도)·미리보기(파일·기록·색인 불변)·
  옮기기(백링크 링크 문자열만 고침, 그사이 바뀐 페이지는 `conflicts`)·지우기·되돌리기·외부 변경 `scan`
  (`external`·`import`, 같은 해시는 다시 안 남김)·점검·그래프·링크 넣기·틀 렌더.
- **zip** `export_zip`·`import_zip`(디스크에 풀지 않음, 경로 공격 항목만 거부, 묶음 상한은 아무것도 쓰지 않음 —
  `ac-safe-zip`, 메모리 가져오기와 같은 규칙).

```python
>>> from agent_console_contracts.wiki import WikiAuthor, WikiRulesDefinition
>>> from agent_console_wiki import (
...     InMemoryWikiHistory, RulesDocument, WikiRepository, WikiRuleRejectedError, merge_rules,
... )
>>> from agent_console_wiki.testing import FakeClock, MemoryWikiPages

>>> rules = merge_rules(["r"], [RulesDocument("r", WikiRulesDefinition.model_validate({
...     "kind": "wiki-rules", "id": "r", "name": "메모 금지",
...     "write_rules": [{"id": "no-temp", "deny_patterns": ["TODO"], "message": "임시 메모 금지"}],
... }))])
>>> repo = WikiRepository(
...     MemoryWikiPages(), wiki_id="notes", syntax=compile_syntax(effective_syntax()),
...     rules=rules, history=InMemoryWikiHistory(), clock=FakeClock(),
... )
>>> _ = repo.write("start", "# 시작\n[[guide]]\n")
>>> _ = repo.write("guide", "# 안내\n", author=WikiAuthor(kind="agent", agent_id="w", label="정리꾼"))
>>> try:
...     repo.write("draft", "첫 줄\nTODO 나중에\n")
... except WikiRuleRejectedError as exc:
...     print(exc.details["rule_id"], exc.details["lines"])
no-temp [2]
>>> result = repo.move("guide", "docs/guide")
>>> [(r.path, r.count) for r in result.rewritten], repo.read("start").text
([('start', 1)], '# 시작\n[[docs/guide]]\n')
>>> [(v.op, v.author.label) for v in repo.page_history("docs/guide").items]
[('move_in', None)]

```

## SQLite 기록 저장소

`agent_console_wiki.sqlite.SqliteWikiHistory(path)`는 `WikiHistory`의 SQLite 구현이다(SQLAlchemy Core, 같은
계약 묶음 통과). 표는 `wiki_page_versions`(버전 한 줄 — 본문 없음)와 `wiki_blobs`(해시마다 본문 한 행)이고,
열 때 `create_all`로 만든다(단독 사용). 서버는 같은 모양을 마이그레이션 계보로 올린다 — 폴더
`sqlite.MIGRATIONS_DIR`·이름 `sqlite.BRANCH_NAME`(`wiki`, 버전 테이블 `alembic_version_wiki`)을 서버 모듈이 감싼다.

```python
>>> from agent_console_contracts.wiki import WikiAuthor
>>> from agent_console_wiki import HistoryEntry
>>> from agent_console_wiki.sqlite import BRANCH_NAME, SqliteWikiHistory
>>> history = SqliteWikiHistory(":memory:")     # 파일이면 경로
>>> me = WikiAuthor(kind="user")
>>> _ = history.record([HistoryEntry.of("notes", "a", "create", b"v1", author=me, at=1.0)])
>>> _ = history.record([HistoryEntry.of("notes", "a", "update", b"v2", author=me, at=2.0)])
>>> [c.op for c in history.changes("notes").items], BRANCH_NAME
(['update', 'create'], 'wiki')
>>> history.close()

```

## 에이전트 도구 묶음

`WikiToolkit(wikis, access=, author=, text=, on_event=, write_budget=)`은 런타임을 모르는 도구 묶음이다(메모리
`MemoryToolkit`과 같은 모양). `specs()`가 접근 설정이 허용한 동작의 도구만 낸다.

- **도구 7개**: `search(query, wiki?, prefix?, tags?, limit?)`·`read(path, wiki?, section?)`·`list(prefix?, wiki?,
  limit?)`·`links(path, wiki?)`·`write(path, content?, wiki?, mode: replace|append|section, section?, template?,
  title?, if_hash?, message?)`·`move(path, to, wiki?, rewrite_links?, if_hash?, message?)`·`delete(path, wiki?,
  if_hash?, message?)`. 매개변수 이름은 계약 어휘, 모델에게 보이는 이름·설명·결과 머리 줄·최대 글자는 접근
  설정(`WikiAccessConfig`, 기본값 = 계약 스키마 기본값), 매개변수 설명·결과 줄·실패 문구는 `data/tool_text.yaml`
  (`text=WikiToolText.from_mapping(...)`로 바꿈).
- **위키 고르기**: `wikis`는 이 실행 공간의 위키(매핑 또는 함수). 접근 설정에 없거나 그 동작을 허용하지 않으면
  `wiki.denied`, 설정에는 있는데 `wikis`에 없으면 `wiki.wiki_unavailable`(`unavailable()`이 목록을 준다).
- **쓰기**: append·section·template은 툴킷이 지금 본문으로 새 본문을 만든 뒤 `write(if_hash=지금 해시)`로 쓴다
  (그사이 바뀌면 `wiki.conflict`). template은 새 페이지만이고 `content`를 주면 틀 본문 끝에 붙인다. section은
  제목 줄을 두고 그 절 본문만 바꾼다.
- **실패**는 예외가 아니라 `is_error` + 사유 코드: `wiki.denied`·`wiki_unavailable`·`page_not_found`·`not_found`
  (절)·`template_missing`·`conflict`·`page_exists`·`too_large`·`secret_rejected`·`rule_rejected`(규칙 id·메시지·
  줄)·`rate_limited`·`invalid_path`·`validation_failed`(입력 형식).
- **결과**는 `repository.secrets.redact`로 가린 뒤 `max_result_chars`로 자른다. **이벤트**(`on_event(type,
  WikiEventPayload)`, type `wiki.<op>`)에는 본문·검색어 원문이 없다(크기·해시만).
- **쓰기 한도**: `write_budget`(`take() -> bool`, 기본 구현 `WriteBudget(limit)`)을 write·move·delete가 하나씩
  쓴다. 실행 하나에 하나를 만들어 여러 묶음이 함께 쓴다.
- **지침**: `instructions()`(= `wiki_instructions(access, targets)`)가 `ToolProvision.instructions`에 넣을 글을
  만든다 — 위키마다 합친 규칙 지침(`include_rules_instructions`)과 경로 안내(`path_hint`, `WikiToolTarget.name`·
  `pages_dir`로 채움, `pages_dir`가 없는데 틀이 쓰면 안내 없음). 같은 글은 한 번.

```python
>>> import asyncio
>>> from agent_console_contracts.wiki import WikiAccessConfig, WikiAuthor
>>> from agent_console_wiki import WikiToolkit, WikiToolTarget, WriteBudget

>>> access = WikiAccessConfig.model_validate(
...     {"wikis": [{"wiki": "notes", "access": ["read", "search", "write"]}]}
... )
>>> kit = WikiToolkit(
...     {"notes": WikiToolTarget(repo, name="노트", pages_dir="wiki/notes")},
...     access=access,
...     author=WikiAuthor(kind="agent", agent_id="keeper", label="위키 관리"),
...     write_budget=WriteBudget(10),
... )
>>> [spec.op for spec in kit.specs()]
['read', 'search', 'write']
>>> out = asyncio.run(kit.call("write", {"path": "log", "content": "첫 기록", "mode": "append"}))
>>> out.is_error, out.event.op, out.event.bytes
(False, 'write', 10)
>>> bad = asyncio.run(kit.call("write", {"path": "log", "content": "TODO", "mode": "append"}))
>>> bad.code, bad.event.rule_ids
('wiki.rule_rejected', ['no-temp'])
>>> asyncio.run(kit.call("delete", {"path": "log"})).code
'wiki.denied'
>>> kit.instructions()[-1].startswith("위키 페이지 파일은 wiki/notes/")
True

```

같은 쓰기 방식을 도구 밖에서도 쓴다(예: LLM 없이 페이지를 고치는 노드). `compose_write(repo, path, content=,
mode=, section=, template=, title=, if_hash=)`는 새 본문과 `write` 조건(`PageComposition{content, create_only,
if_hash}`)만 만들고 쓰지 않는다(절이 없으면 `WikiSectionNotFoundError` — 코드 `wiki.not_found`, `details.reason =
section_not_found`). `wiki_failure(exc)`는 저장소 예외를 도구와 같은 이벤트 상태·사유 코드(`WikiFailure{status,
code, reason, rule_ids}`)로 바꾼다.

```python
>>> from agent_console_wiki import WikiPageExistsError, compose_write, wiki_failure
>>> plan = compose_write(repo, "log", content="둘째 기록", mode="append")
>>> plan.content, plan.create_only, plan.if_hash == repo.current("log").content_hash
('첫 기록\n둘째 기록', False, True)
>>> wiki_failure(WikiPageExistsError("log")).status
'conflict'

```

Claude Agent SDK에서는 스펙마다 `@tool`로 감싸 in-process MCP 서버에 넣는다(이 패키지는 SDK를 모른다):

```text
from claude_agent_sdk import create_sdk_mcp_server, tool

def sdk_tools(kit):
    out = []
    for spec in kit.specs():
        @tool(spec.name, spec.description, dict(spec.input_schema))
        async def handler(args, _spec=spec):
            result = await _spec.call(args, None)
            return {"content": [{"type": "text", "text": result.text}], "is_error": result.is_error}
        out.append(handler)
    return create_sdk_mcp_server(name="wiki", tools=out)
```

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
AGENT_CONSOLE_PERF=strict uv run pytest tests/test_agent_console_wiki_perf.py tests/test_agent_console_wiki_search_perf.py   # 벽시계 기준까지
```
