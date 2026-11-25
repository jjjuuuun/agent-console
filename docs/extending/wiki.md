# 위키

위키의 원본은 마크다운 파일이다. 링크·머리말을 읽는 규칙([wiki-syntax](#wiki-syntax))과 에이전트 지침·쓰기·점검 규칙([wiki-rules](#wiki-rules))은 데이터이고, 검색 색인([wiki-search-index](#wiki-search-index))과 쓰기 검사([wiki-write-check](#wiki-write-check))는 플러그인으로, 페이지 기록 저장소([wiki-history](#wiki-history))는 주입으로 바꾼다.

## wiki-history

**언제 쓰나**: 페이지 기록(버전·쓴 주체·되돌리기 원본)을 다른 저장소에 둔다. 위키 라이브러리를 서버 없이 쓰면서 자기 DB에 기록을 남길 때다.

**최소 모양**: `WikiHistory` 프로토콜(`record`·`list`·`get`·`read`·`latest`·`summaries`·`changes`·`prune`)을 구현해 `WikiRepository(..., history=...)`에 넘긴다. 메모리 구현 `InMemoryWikiHistory`와 SQLite 구현(`agent_console_wiki.sqlite.SqliteWikiHistory`)이 본보기다.

```python
from agent_console_wiki.testing import WikiHistoryContractTests


class TestMyHistory(WikiHistoryContractTests):
    def make_history(self, tmp_path):
        return MyHistory(tmp_path / "history.db")
```

**규칙**
- 메서드는 동기이고 스레드에서 불러도 안전해야 한다.
- 버전은 페이지마다 1부터 오른다. 무엇을 언제 남길지는 위키 저장소가 정하고, 기록 저장소는 받은 것을 그대로 남긴다.
- 보관 수 한도(`max_versions_per_page`)는 저장소가 `prune`을 불러 지킨다.
- 같은 의미인지는 계약 테스트 묶음 `WikiHistoryContractTests`로 확인한다([테스트](testing.md#3-계약-테스트-묶음)).

**흔한 실수**: 본문을 해시만 남기고 버리기(되돌리기·비교가 `read`로 본문을 읽는다), 옮기기의 두 기록(`move_out`·`move_in`) 중 하나를 버리기.

**서버에서**: 위키 모듈은 단독 공간이면 호스트 DB, 프로젝트 공간이면 그 폴더의 기록 DB를 쓴다. 기록 DB를 열 수 없으면 기록 없이 동작하고 기록 화면은 `wiki.history_unavailable`이다.

<!-- extdocs:facts wiki-history -->
- 등록: 생성자·인자로 구현을 주입한다(인터페이스를 따르는 객체).
- 인터페이스:
  - `agent_console_wiki:WikiHistory` — 페이지 기록 저장소. 메서드는 동기이며 스레드 안전해야 한다.
- 기본 구현: —
- 예제:
  - contract-tests: `agent_console_wiki.testing:WikiHistoryContractTests`
- 끄기·제거: 주입하지 않으면 기본 구현을 쓴다.
<!-- /extdocs:facts -->

## wiki-rules

**언제 쓰나**: 위키를 쓰는 에이전트에게 줄 지침, 쓰면 안 되는 것(쓰기 규칙), 점검 탭에 보일 것(점검 규칙), 새 페이지의 뼈대(페이지 틀), 그 위키만의 문법을 묶는다. 위키 정의는 규칙 id 목록(`rules`)으로 여러 규칙을 순서대로 쓴다. 앱은 규칙을 하나도 갖고 오지 않는다.

**최소 모양**: 정의 종류 `wiki-rules`의 문서 하나다. 지침 본문과 페이지 틀 파일은 정의 옆 본문 폴더에 둔다.

```yaml extdocs:validate=agent_console_contracts.wiki:WikiRulesDefinition
kind: wiki-rules
id: decisions
name: 결정 기록
instructions: {file: instructions.md}
page_templates:
  - {id: decision, title: 결정, file: templates/decision.md, path: "decisions/{slug}"}
write_rules:
  - id: no-temp-notes
    applies_to: ["decisions/**"]
    deny_patterns: ['(?i)\bTODO\b']
    action: reject
    message: 결정 페이지에 임시 메모를 남기지 않습니다
  - id: agent-needs-source
    when: {all: [{path: /author/kind, op: eq, value: agent}]}
    require: {all: [{path: /page/front_matter/source, op: exists}]}
    action: warn
    message: 에이전트가 쓴 페이지에는 근거(source)를 적습니다
lint_rules:
  - id: stale
    when: {all: [{path: /idle_days, op: gte, value: 90}]}
    severity: info
    message: 90일 넘게 고치지 않은 페이지
```

**규칙**
- 여러 규칙을 쓰면 지침 본문은 순서대로 이어 붙이고, 쓰기·점검 규칙·페이지 틀도 이어 붙인다. 같은 id는 앞의 것이 이기고 `wiki.duplicate_rule_id`가 붙는다.
- 쓰기 규칙은 위에서부터 모두 본다: `applies_to`(경로 글롭) → `when`(참이어야 건다) → `require`(거짓이면 동작)·`deny_patterns`(맞는 줄이 있으면 동작). `reject`가 하나라도 맞으면 쓰지 않는다. 모르는 동작은 `warn`으로 읽고 `wiki.unknown_action`이 붙는다.
- 쓰기 규칙은 화면·REST·에이전트 도구로 쓰는 길에 걸린다. 파일을 직접 고친 것은 다음 읽기에서 외부 변경으로 기록되고 점검의 `wiki.rule_violation`으로 보인다.
- 저장 전 검사가 정규식·글롭·조건·틀 변수를 본다. 늘 거부하는 규칙은 `wiki.always_rejects`다.

**흔한 실수**: 조건 경로를 쓰기 판단 대상 밖으로 적기(늘 거짓이라 규칙이 걸리지 않는다, 대상 경로는 편집 화면의 제안 목록에 있다), 지침·틀 파일을 정의에 적고 본문 폴더에 만들지 않기(`wiki.template_missing`).

**끄기와 남는 데이터**: 위키 정의의 `rules`에서 빼면 그 규칙이 걸리지 않는다. 지운 규칙을 가리키는 위키는 `wiki.rules_missing`을 보이고 나머지 규칙으로 동작한다.

<!-- extdocs:facts wiki-rules -->
- 등록: 등록 종류 `definition`.
- 인터페이스:
  - `agent_console_contracts.wiki:WikiRulesDefinition` — 위키 규칙입니다. 에이전트 지침, 쓰기·점검 규칙, 페이지 틀, 문법을 담습니다.
- 기본 구현: —
- 예제:
  - snippet: 위키 규칙 정의 데이터
<!-- /extdocs:facts -->

## wiki-search-index

**언제 쓰나**: 위키 검색을 다른 색인으로 바꾼다(사내 검색 엔진, 형태소 분석, 다른 저장 방식). 색인은 페이지 파일에서 언제든 다시 만들 수 있는 캐시다.

**최소 모양 — 공장**: 등록하는 것은 색인이 아니라 **공장** `(root, options) -> WikiSearchIndex`다. entry point 값은 인자 없는 함수이고 이 공장을 돌려준다.

- `root`: 색인 파일 위치(`Path`) 또는 `None`. 위키 모듈은 프로젝트 공간이면 공간의 색인 폴더 아래, 단독이면 상태 폴더 아래 위키마다 하나를 준다. 기능 확인용으로 `None`을 주어 부르기도 한다. 파일을 쓰지 않는 색인은 무시한다.
- `options`: 설치자 설정에서 온 값. `tokenizer`와, 그 방식 이름 아래 적은 `search.index_options.<방식>`의 키(키 뜻은 색인이 정한다, 예: `token_pattern`) 위에 위키 모듈이 `case_insensitive`(위키 문법)·`max_results`(검색 결과 상한)·`redact`(지금 비밀 의심 규칙 — 사용자 규칙 포함 — 의 가리기 함수, 제목·본문을 색인에 넣기 전에 부른다)·`redact_signature`(그 규칙의 서명 글, 바뀌면 파일 색인을 다시 짓는다)를 덮어 넘긴다. `redact`가 없으면 기본 비밀 규칙으로 가린다. 모르는 값은 기본으로 돌린다.
- 공장은 위키(와 공간)마다, 설정이 바뀔 때마다 다시 불린다. 공장이 예외를 던지면 그 위키는 색인 없이 동작한다.

```python
>>> from agent_console_wiki import ScanSearchIndex, WikiSearchDocument
>>> def index_factory():                  # entry point 값
...     def make(root, options):          # 공장
...         return ScanSearchIndex(case_insensitive=bool(options.get("case_insensitive", True)),
...                                redact=options.get("redact"))
...     return make
>>> index = index_factory()(None, {"tokenizer": "trigram", "case_insensitive": True, "max_results": 50})
>>> index.update([WikiSearchDocument(path="guide/intro", title="소개", text="이 위키는 팀의 약속을 적는다.",
...                                  content_hash="h1")])
1
>>> [hit.path for hit in index.search("위키").items]
['guide/intro']

```

```toml
[project.entry-points."agent_console.wiki_search_indexes"]
"my-index" = "my_package:index_factory"
```

색인 자체는 `WikiSearchIndex` 프로토콜(`id`·`degraded`·`hashes`·`update`·`remove`·`rebuild`·`search`·`close`)이다. 낱말 나누기를 옵션 데이터로 받는 메모리 역색인이 [위키 검색 예제](../../examples/extensions/agent-console-example-wiki-search/README.md)에 있다.

**고르기**: 설치만으로는 쓰이지 않는다. 사용자 설정 `wiki.search_backend` → 설치자 `modules.options.mod-wiki.search.backend` → `search.fallback` 순서로 처음 설치된 이름을 쓴다.

```yaml extdocs:validate=agent_console_contracts.wiki:WikiSettings
search_backend: my-index
```

**규칙**
- 의미는 계약 묶음 `WikiSearchContractTests`가 정한다. 모든 낱말이 경로·제목·태그·별칭·본문 어딘가에 있어야 맞고, 점수 규칙과 순서가 기본 색인과 같아야 한다.
- 비밀은 색인에 넣기 전에 가린다. 조각(`snippet`)과 강조 범위(`marks`)는 가린 본문 기준이고, `marks`는 조각 기준 UTF-16 범위다.
- `update`는 `content_hash`가 같으면 건너뛰고 실제로 쓴 수를 돌려준다.
- 스레드에서 불러도 안전하고, `close`는 여러 번 불러도 된다.
- 원하던 방식을 못 써서 느린 방식으로 돌면 `degraded`를 참으로 둔다. 위키 정보에 `wiki.search_degraded`가 보인다.

**흔한 실수**: 공장 대신 색인 객체를 entry point로 내기(위키마다 색인이 따로 있어야 한다), `root`가 `None`일 때 파일을 만들려고 하기, `marks`를 코드 포인트로 세기.

**끄기와 남는 데이터**: 설정에서 이름을 지우거나 패키지를 제거하면 다음 순서의 방식으로 돌아간다. 고른 이름이 설치돼 있지 않으면 대체 방식을 쓰고 `wiki.search_degraded`를 보인다. 색인 파일은 남지만 다시 만들 수 있는 캐시이므로 지워도 된다.

<!-- extdocs:facts wiki-search-index -->
- 등록: entry point 그룹 `agent_console.wiki_search_indexes`(상수 `agent_console_wiki:SEARCH_INDEX_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_wiki:WikiSearchIndex` — 위키 검색 색인. 스레드에서 불러도 안전해야 한다.
- 설정: `wiki.search_backend`, `mod-wiki.search.backend`
- 기본 구현: —
- 예제:
  - package: [examples/extensions/agent-console-example-wiki-search](../../examples/extensions/agent-console-example-wiki-search/README.md)
  - contract-tests: `agent_console_wiki.testing:WikiSearchContractTests`
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->

## wiki-syntax

**언제 쓰나**: 다른 도구에서 만든 위키 폴더를 그대로 열고 싶을 때. 링크 모양(`[[대상|라벨]]` 대신 다른 괄호), 머리말 키 이름(`title` 대신 `제목`), 제목을 어디서 읽을지, 페이지 확장자, 대소문자, 앱 화면으로 가는 링크 스킴, 기본 점검의 심각도를 바꾼다.

**최소 모양**: 워크스페이스 설정의 `wiki` 섹션 `syntax`(모든 위키) 또는 위키 규칙의 `syntax`(그 규칙을 쓰는 위키)다.

```yaml extdocs:validate=agent_console_contracts.wiki:WikiSettings
include_default_syntax: true
syntax:
  links:
    - id: double-paren
      kind: pattern
      pattern: '\(\((?P<target>[^)|]+)(?:\|(?P<label>[^)]+))?\)\)'
      insert: "(({target}|{label}))"
      resolve: [path, title, alias]
    - {id: markdown, kind: markdown, resolve: [relative_path, path]}
  front_matter:
    roles: {title: 제목, tags: 분류, aliases: 별칭}
  page_extensions: [.md]
  lint:
    builtin: {orphan: null, broken_link: warning}
```

**규칙**
- 병합 순서는 패키지 기본 → 사용자 설정 `wiki.syntax` → 위키 규칙 `syntax`(규칙 순서)다. `null`은 상속, 빈 목록은 "이 층에서는 없음"이다. `front_matter`·`lint`는 그 안의 키 단위로 합치고 나머지는 통째로 바꾼다. 값마다 어느 층에서 왔는지 남는다.
- 코드가 뜻을 아는 것은 머리말 역할(`title`·`tags`·`aliases`), 기본 점검(`broken_link`·`orphan`·`duplicate_title`), 대상 찾기(`path`·`title`·`alias`·`relative_path`)뿐이다. 패턴·키 이름·순서는 데이터다.
- 패턴은 이름 그룹 `target`(필수)·`label`·`anchor`를 쓴다. 코드 블록·인라인 코드 안의 링크는 링크가 아니다.
- 이름 바꾸기는 링크 대상 글자만 고친다. 제목·별칭으로 이어진 링크는 고치지 않는다(옮겨도 이어진다).

**흔한 실수**: `links`에 규칙 하나만 적어 기본 마크다운 링크 읽기를 지우기(목록은 통째로 바뀐다), `target` 그룹 없는 패턴(`wiki.link_pattern_invalid`), 페이지가 많은 위키에서 느린 정규식(`wiki.parse_timeout`).

**끄기**: `include_default_syntax: false`면 기본 문법이 빠진다. 다른 문법도 없으면 링크가 0개이고 `wiki.syntax_missing`이 붙는다. 설정 일부가 깨지면 그 부분만 빼고 `wiki.settings_invalid`로 알린다.

<!-- extdocs:facts wiki-syntax -->
- 등록: 패키지 데이터 `data/default_syntax.yaml`를 설정(`wiki.syntax`)으로 덮어쓴다.
- 인터페이스:
  - `agent_console_contracts.wiki:WikiSyntax` — 링크·머리말·제목을 페이지에서 읽는 규칙입니다.
  - `agent_console_wiki:load_default_syntax` — 패키지 기본 위키 문법(`data/default_syntax.yaml`)을 읽는다.
- 기본 구현: —
- 예제:
  - snippet: 사용자 설정 wiki.syntax 데이터
- 끄기·제거: 끄는 키: `wiki.include_default_syntax`.
<!-- /extdocs:facts -->

## wiki-write-check

**언제 쓰나**: 위키 쓰기에 데이터 규칙으로는 표현할 수 없는 검사를 더한다. 예: 머리말의 키 조합 검사, 외부 목록과 대조. 정규식·조건으로 되는 검사는 위키 규칙의 쓰기 규칙([wiki-rules](#wiki-rules))으로 충분하다.

**최소 모양**: `id`와 `check(subject, text) -> list[WikiIssue]`다. entry point 값은 검사 객체이거나, 옵션(사용자 설정 `options`)을 받아 검사를 만드는 공장이다.

```python
>>> from agent_console_contracts.wiki import WikiIssue
>>> from agent_console_wiki import run_write_checks
>>> class NoTodo:
...     id = "example.no-todo"
...     def __init__(self, options):
...         self.word = str(options.get("word", "TODO"))
...     def check(self, subject, text):
...         if self.word not in text:
...             return []
...         return [WikiIssue(severity="error", code="example.todo_left", message="할 일이 남았습니다")]
>>> decision = run_write_checks([NoTodo({})], {"page": {"path": "a"}}, "TODO 나중에")
>>> [(i.code, i.rule_id) for i in decision.issues]
[('example.todo_left', 'example.no-todo')]

```

사용자 설정에서 켠다. 연동 모듈이 포트로 주는 검사는 늘 켜져 있고 `enabled: false`로 끈다.

```yaml extdocs:validate=agent_console_contracts.wiki:WikiSettings
write_checks:
  - id: example.front-matter-keys
    enabled: true
    options: {keys: [owner, source], paths: ["decisions/**"]}
```

**규칙**
- 위키 규칙의 쓰기 규칙과 비밀 검사 뒤에 차례로 불린다. `subject`는 쓰기 판단 대상(동작·쓴 주체·쓴 뒤 페이지·쓰기 전 페이지), `text`는 새 본문(지우기는 빈 문자열)이다.
- `severity: error`만 쓰기를 거부한다. 나머지는 저장하고 경고로 보인다. 이슈의 `rule_id`가 비면 검사 `id`가 들어간다.
- 옵션이 틀리면 생성자에서 예외를 던진다. 위키 모듈은 그 검사를 쓰지 않고 `wiki.settings_invalid`를 남긴다(쓰기는 된다).
- `check`가 예외를 던지면 그 검사만 건너뛰고 `wiki.rule_warning` 경고가 붙는다. 이슈 문장·예외 문장에 본문이나 비밀 값을 싣지 않는다.

**흔한 실수**: 키 이름·경로·문구를 코드에 두기(옵션 데이터로 받는다), 지우기(`op: delete`)에서 `text`를 읽어 판단하기(지우기 전 사실은 `subject.page`에 있다).

**끄기와 남는 데이터**: 설정에서 `enabled: false`로 두거나 패키지를 제거하면 검사가 빠진다. 설치되지 않은 검사를 켜 두면 `wiki.settings_invalid` 경고가 붙고 나머지 쓰기는 그대로 된다.

<!-- extdocs:facts wiki-write-check -->
- 등록: entry point 그룹 `agent_console.wiki_write_checks`(상수 `agent_console_mod_wiki:WRITE_CHECKS_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_wiki:WikiWriteCheck` — 위키 쓰기 검사 보탬. 쓰기 규칙·비밀 검사 뒤에 차례로 부른다.
- 설정: `wiki.write_checks`
- 기본 구현: —
- 예제:
  - package: [examples/extensions/agent-console-example-wiki-check](../../examples/extensions/agent-console-example-wiki-check/README.md)
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->
