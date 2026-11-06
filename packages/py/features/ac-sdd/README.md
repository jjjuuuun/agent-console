# agent-console-sdd

Agent Console SDD(스펙 기반 개발) 핵심 라이브러리. 서버·실행·프로젝트를 모르고, **마크다운 문서 문자열**과
계약 모델(`agent_console_contracts.sdd`), 주입한 정의 저장소(`ac-store` `DefinitionStore`)·파일 접근
(`SpecFiles`)만 다룬다(design §6R.1~§6R.1.6).

- **작업 문법은 데이터다.** 패키지 기본(`data/default_syntax.yaml`) → 사용자 설정 `sdd.syntax` → 스펙
  `rules.syntax`(+ `rules.task_statuses`) 순서로 덮어쓴다. None은 "상속", 빈 목록은 "이 층에서는 없음".
  첫 단계(`task`·`requirement`·`stage`)는 키 단위로 합치고 그 아래 값(목록·`roles`)은 통째로 바꾼다.
  값마다 출처(`default`·`settings`·`spec`)가 `EffectiveSyntax.sources`에 남는다. 기본 문법은 끌 수 있다
  (`SddSettings.include_default_syntax: false` → 작업 0개 + `sdd.syntax_missing`).
- **작업의 원본은 마크다운 원문이다.** `parse_spec`이 읽을 때마다 작업·필드·요구 id·단계를 만든다(저장 안 함).
  블록 구조(목록·제목·코드 블록·인용·줄 범위)는 markdown-it-py가, 머리 줄 안의 체크 칸·id·`[키: 값]` 필드는
  문법 정규식(`ac-safe-regex`, 시간·길이 상한)이 읽는다. 코드 블록·인용 안의 목록은 작업이 아니다.
- **코드가 뜻을 아는 필드 역할은 의존(`dependencies`)·요구(`requirements`)·담당(`assignee`)**(+ 선택 `weight`)
  뿐이다. 어느 필드가 그 역할인지는 문법 `roles` 데이터다. 상태·필드·단계·문서 이름은 모두 데이터다.
- **상태 바꾸기 = 줄 하나 고치기.** `patch_task`는 그 작업 머리 줄의 체크 칸 글자와 필드 값만 바꾸고 다른
  바이트(줄바꿈 종류·들여쓰기·뒤 공백·다른 줄)는 그대로 둔다. 충돌은 머리 줄 해시(`line_hash`)로 판단한다.

## 의존성: 무엇을 / 왜 / 대안

- **markdown-it-py**(MIT, 활발): CommonMark 블록 파서. 토큰 `map`이 줄 범위를 줘서 원문 줄 고치기가 쉽다.
  인라인 파싱은 꺼서(블록 구조만) 큰 문서에서도 빠르다. 대안: mistune(줄 범위가 약함), 직접 줄 파서(코드 블록·
  중첩 목록 예외가 많음). design §6R.10의 `mdit-py-plugins`(tasklists)는 쓰지 않는다 — 체크 칸 글자가 데이터
  (`~`·`?` 등)라 표준 tasklist(`[ ]`·`[x]`)만 아는 플러그인으로는 읽을 수 없어 머리 줄 분석이 어차피 필요하다.
- **ruamel.yaml**: 패키지 기본 문법 데이터 읽기(저장소 전체가 쓰는 YAML 라이브러리).
- 사내: `agent-console-contracts`(모델), `agent-console-safe-regex`(사용자 정규식),
  `agent-console-conditions`(관문·프로필 조건 — 새 표현식 언어를 두지 않는다), `agent-console-text-template`
  (실행 입력 틀 — 같은 안전 치환을 두 곳에 두지 않는다), `agent-console-store`(정의 저장소 프로토콜·
  `DefinitionKind`·경로 검사 — 스펙·틀은 정의 종류라 새 저장소가 없다).
- 표준 `graphlib`: 계획의 위상 층(대안 networkx — 의존이 무겁다).

## 설치

```bash
pip install agent-console-sdd
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-sdd
```

## 최소 사용 (서버 없이 문서 문자열 → 작업 목록)

```python
>>> from agent_console_contracts.sdd import SpecDefinition
>>> from agent_console_sdd import effective_syntax, find_task, parse_spec, patch_task

>>> spec = SpecDefinition.model_validate({
...     "kind": "spec", "id": "demo", "name": "데모",
...     "documents": [{"id": "tasks", "title": "작업", "file": "tasks.md", "roles": ["tasks"]}],
... })
>>> text = (
...     "## 1단계\n"
...     "- [x] 1.1 뼈대 [owner: be] [depends: —]\n"
...     "- [ ] 1.2 화면 [owner: fe] [depends: 1.1]\n"
...     "- [ ] 1.3 검증 [depends: 1.1~1.2]\n"
... )
>>> syntax = effective_syntax()          # 패키지 기본 문법(끌 수 있음)
>>> index = parse_spec(spec, {"tasks.md": text}, syntax)
>>> [(t.key, t.status, t.ready, t.dependencies) for t in index.tasks]
[('1.1', 'done', False, []), ('1.2', 'todo', True, ['1.1']), ('1.3', 'todo', False, ['1.1', '1.2'])]
>>> index.stages[0].id, index.stages[0].done, index.stages[0].total
('1단계', 1, 3)

>>> task = find_task(index, "1.2")
>>> print(patch_task(text, task, syntax=syntax, status="done", fields={"owner": "qa"}), end="")
## 1단계
- [x] 1.1 뼈대 [owner: be] [depends: —]
- [x] 1.2 화면 [owner: qa] [depends: 1.1]
- [ ] 1.3 검증 [depends: 1.1~1.2]

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

문법 바꾸기: `effective_syntax(rules, settings)`에 스펙 규칙(`SpecRules.syntax`·`task_statuses`)과 사용자 설정
(`SddSettings`)을 주거나, `merge_syntax(("default", ...), ("spec", {...}))`로 층을 직접 준다. 파싱 문제는
`SpecIssue`(문서·줄·작업 키·코드, 값 원문 없음)로 `index.issues`에 모두 모이고, 작업 하나에 걸린 것은 그 작업
`issues`에도 들어간다. 코드: `sdd.duplicate_task_id`·`unknown_dependency`·`dependency_cycle`·
`unknown_status_marker`·`range_unresolved`·`unknown_requirement`·`document_missing`·`parse_timeout`·
`too_many_tasks`·`syntax_missing`·`invalid_pattern`·`duplicate_status_marker`.

## 계획·추적·관문 (서버 없이)

```python
>>> from agent_console_sdd import compile_syntax, plan, trace
>>> compiled = compile_syntax(syntax)
>>> index = parse_spec(spec, {"tasks.md": text}, compiled)
>>> p = plan(index, compiled)   # 끝나지 않은 작업: 층(= 병렬 묶음)·병목·순환
>>> p.layers, p.critical_path
([['1.2'], ['1.3']], ['1.2', '1.3'])
>>> trace(index, [], [], syntax=compiled).rows   # 요구 문서가 없으면 행도 없다
[]

>>> from agent_console_conditions import builtin_operators
>>> from agent_console_contracts.sdd import SpecRules
>>> from agent_console_sdd import evaluate_gates, gate_context
>>> ops = {op.descriptor.id: op for op in builtin_operators()}
>>> rules = SpecRules.model_validate({"gates": [{
...     "id": "design-ok", "applies_to": ["run"], "message": "설계 승인 전",
...     "require": {"all": [{"path": "/documents/design/state", "op": "eq", "value": "approved"}]}}]})
>>> [b.details.document_ids for b in evaluate_gates(rules, "run", gate_context(spec), operators=ops)]
[['design']]

```

- `plan(index, syntax)`: 끝난 의존은 풀린 것, 문서에 없는 의존은 무시. 순환에 든 작업과 그것에 기대는
  작업은 층에 넣지 않고 `blocked`·`cycles`에. 병목 가중치는 문법 `roles`에서 `weight` 역할인 필드(없으면 1).
- `trace(index, links, results, *, syntax, max_runs, run_kinds, failed_results)`: 빈 곳 `no_task`·`no_run`·
  `not_verified`·`verification_failed`·`task_not_done`, 고아(요구 없는 작업·모르는 요구 참조·지금 없는
  작업 키를 가리키는 연결). 실패로 볼 검증 결과 값(`failed_results`)·실행으로 셀 연결 종류는 인자다.
- 관문을 평가하는 때(`run`·`task_status`·`document_state`)는 코드 개념이고, 맥락은
  `{spec, documents: {<id>: {state, title}}, task, stage, change}`다. 모르는 연산자·없는 값은 거짓이라 막힌다.
- `check_rules(rules, *, operators, documents, settings, graphs)`: 문법 정규식·표시 문자 중복, 조건 검사,
  모르는 상태·프로필·변수, 공간에 없는 팀 구성(목록을 줄 때). 깨진 규칙도 예외 없이 이슈로.
- `render_run_input(profile, task, spec, *, spec_dir)`: 변수 표는 `run_input_variables(documents)`(스펙·틀
  공용). `spec_dir`은 프로젝트 폴더 기준 상대 경로만(절대 경로는 `SpecPathError`).

## 저장소·가져오기/내보내기

```python
>>> from agent_console_sdd.testing import MemorySpecFiles, memory_repository
>>> from agent_console_sdd import import_documents, list_import_files
>>> repo = memory_repository()   # 실제로는 SpecRepository(store, spec_kind=…, template_kind=…)
>>> folder = MemorySpecFiles({"docs/tasks.md": "# 작업\n- [ ] 1 첫 일\n", "docs/.x.md": "숨김"})
>>> [f.name for f in list_import_files(folder, "docs", extensions=[".md"]).files]
['tasks.md']
>>> got = import_documents(folder, ["docs/tasks.md"])
>>> stored = repo.create(name="Demo", documents=got.documents, contents=got.contents)
>>> stored.id, [d.title for d in stored.spec.documents]
('demo', ['작업'])

```

- `SpecRepository(store, *, spec_kind, template_kind, operators, settings, directory, …)`: 정의 종류 이름·
  폴더는 호출자 데이터(`definition_kinds(...)`로 `DefinitionKind` 두 개를 만든다 — 스펙은 `library=False`).
  만들기(틀 복사 — 스펙 파일에 틀 id 없음, 버전 메시지에만 / 가져온 문서 / 빈 스펙 = 패키지 데이터
  `data/blank_spec.yaml`), 규칙 저장, 문서 본문(파일 sha256 `If-Match`, 없으면 `DocumentMissingError` —
  읽기로 만들지 않음, 만들기만 `create_only`, 상태 `on_edit`), 상태 전환(`transitions`의 `from`·`to`·`by`,
  관문), 작업 고치기(최신 원문 재파싱 → 작업 키 → 머리 줄 해시 비교, 다른 줄이 바뀌어도 통과, 정의 저장
  충돌이면 한 번 다시 시도), 틀 목록·틀로 저장(`fail`·`overwrite`·`rename`). 문서 틀이 다른 저장소에
  있으면 `template_store`로 준다(예: 단독 공간 스펙 + 앱 라이브러리 틀 — 틀 읽기·목록·틀로 저장 기본
  대상).
- `SpecFiles`(프로토콜): 프로젝트 폴더 기준 상대 경로만. 이 패키지가 `..`·절대·드라이브·링크·예약 폴더를
  먼저 거부하고(`check_project_path`), 기본 구현 `LocalSpecFiles(root)`는 링크를 푼 실제 경로가 폴더 안인지
  한 번 더 본다. 가져오기·내보내기는 복사이고 원본과 연결하지 않는다.
- 오류는 `SddError` 하위(`code` = 계약 오류 코드, `details`에 값 원문 없음): `SpecNotFoundError`·
  `DocumentMissingError`·`DocumentExistsError`·`DocumentChangedError`·`TransitionDeniedError`·
  `GateBlockedError`·`TemplateExistsError`·`SpecPathError`. 저장소 오류(`VersionConflict` 등)는 그대로 올라간다.

## 확장 지점

- **X42 `VerificationSource`**: `id` + `async collect(VerificationContext) -> list[VerificationResult]`.
  파일을 읽는 출처는 `ctx.spec.files`(폴더 안만)만 쓴다.
- **X43 `TaskIntegration`**: `id` + `async actions(ctx, task)`·`invoke(ctx, task, action, args)`·
  `links(ctx, tasks)`(한 번에 모음). 선택 능력 `ProfileChecker.check_profile`,
  `TaskIssueSource.task_issues(ctx, tasks) -> list[SpecIssue]`(동기, 작업 키별로 `ParsedTask.issues`에
  더함 — 예: `sdd.status_not_applied`·`sdd.automation_skipped`), `AutomationControl`
  (`automation_state`·`control(op)`).
- 예제 구현(테스트 가짜): `agent_console_sdd.testing.FakeVerificationSource`·`FakeTaskIntegration`.

## 규칙 요약

| 무엇 | 규칙 |
| --- | --- |
| 작업 키 | 작업 id, 없으면 `@<문서 id>:<그 문서 안 순번>`. 같은 id가 또 나오면 뒤의 것은 위치 키 + `sdd.duplicate_task_id` |
| 작업 문서·요구 문서 | 문서 `roles`에 `tasks`·`requirements`가 있는 것만 읽는다. 역할 없는 문서는 있는지·해시만 |
| 범위 `a~b` | 문서 순서상 a부터 b까지 전부(의존·요구 모두). 끝 뒤의 낱말(`6R.11 전부`)은 첫 낱말로 찾는다 |
| 모르는 의존 | 이슈만 내고 준비(`ready`)를 막지 않는다 |
| 모르는 요구 | 요구 문서를 읽었을 때만 `sdd.unknown_requirement`(info) |
| 상한 | `max_tasks`(스펙 전체), `timeout_ms`(문서 하나 — 넘으면 그 문서 작업·요구를 버림) |
| 체크 칸 없는 목록(`list_item: bullet`·`ordered`) | 첫 작업 상태로 보고, 상태를 바꾸면 목록 표시 뒤에 `[글자] `를 넣는다 |
| 없는 필드 덧붙이기 | 머리 줄 끝(뒤 공백 앞)에 `field_format`(기본 `[{key}: {value}]`), 다시 읽히지 않으면 거부 |

## 테스트 도우미

`agent_console_sdd.testing`: 표본 문서(`sample_spec`·`sample_files`·`render_tasks`), 이름을 모두 바꾼 문법
(`RENAMED_SYNTAX`·`RENAMED_NAMES`), 가짜 파일 접근 `MemorySpecFiles`, 가짜 검증 출처·작업 연동, 메모리 저장소
조립 `memory_repository`(종류 이름 `TEST_SPEC_KIND`·`TEST_TEMPLATE_KIND`). 기본 문법·프리셋이 아니라 테스트
표본이다.

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
AGENT_CONSOLE_PERF=strict uv run pytest -k perf   # 벽시계 단언(한가한 장비에서)
```
