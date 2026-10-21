# agent-console-link-runs-teams

실행·팀 연동 모듈(design §3R.1.4 L4). 실행 모듈(`mod-runs`)에 팀 의미(`ac-teams`)를 잇는다.

- `runs.preparers`: 엔진 검증 뒤 팀 규칙 검사(`validate_team`, 엔진 이슈와 같은 뜻은 `merge_validation`으로 뺌)와 실행 준비(`prepare_run` — 허용 상호작용·상호작용 대기 설정).
- 사전 점검(`TeamRules.preflight`, `mod-runs`의 선택 메서드): 실행을 만들기 전에 실행 백엔드가 빈 노드(`ac-teams.resolve_backends`·`unresolved_backends`)가 있으면 422 `backend.unresolved`(`details` = `BackendUnresolvedDetails{nodes, options}`, `fix.actions` = [노드에서 지정]·[기본값으로 지정])를 낸다. Run·턴 기록이 남지 않는다. 문구·웹 라우트 역할·설정 섹션·초점은 `BackendFixTexts` 데이터(`TeamRules(fix_texts=)`)다. 자식 Run은 점검하지 않는다(노드 실패 `agent.no_backend`).
- `runs.services`: 노드 서비스(`ac-nodes-core` 키 — 에이전트·리소스 조회, 공통 설정, 기본 백엔드, 작업 폴더, 실행 파일 폴더, 중첩 팀 조회 `TEAM_LOOKUP`).
- 중첩 팀(design §5R.7): 팀 구성 읽기(`runs.starter`의 `load_graph(id, version_hash)`, 고정 버전 포함)로 노드 서비스 `TEAM_LOOKUP`과 팀 규칙의 중첩 검사(`team.recursive`·`team.nesting_exceeded`·`team.team_not_found`·`team.child_no_entry`)를 준다.
- `graphs.validation`: 팀 구성 목록 검증 요약(워크스페이스 지문 캐시, `definitions.saved` 구독으로도 버림).
- 경로 `POST /graphs/{id}/validate`(본문 그래프 또는 저장본, 이슈가 있어도 200). 결과 = 엔진 검증 + 팀 규칙 + 선택 포트 `definitions.checks`(저장 전 정의 검사)의 경고·정보(예: `mod-projects`의 `project.shared_uses_project` + 제안 `project.move_to_shared`). 검사의 error는 저장 경로가 422로 거부하므로 붙이지 않고, 같은 코드·대상·path는 한 번만 낸다. 제공 모듈이 없으면 엔진 검증 + 팀 규칙만이다(`definition_check_issues`·`with_definition_checks`는 HTTP 없이도 쓴다).

이 연동이 꺼지면 실행은 엔진 검증만으로 하고(`mod-runs`가 `team.rules_unavailable` 경고), 목록 검증 요약은 null, 검증 경로는 404다. 에이전트 노드도 에이전트 조회 서비스가 없어 `agent.lookup_unavailable`로, 중첩 팀 노드는 팀 구성 조회가 없어 `team.lookup_unavailable`로 실패한다.

## 설치

```bash
pip install agent-console-link-runs-teams
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-link-runs-teams
```

## 최소 사용

단독 실행용 동반 모듈(`testing.local_runs_module` — 검증만 하는 `runs.starter`와 파일 정의 저장소)과 조립해 검증한다.

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_contracts import Graph
>>> from agent_console_modkit import BaseServices, Paths, assemble
>>> from agent_console_runtime import Registries
>>> from agent_console_link_runs_teams import RUN_PREPARERS, module
>>> from agent_console_link_runs_teams.testing import local_runs_module
>>> root = Path(tempfile.mkdtemp())
>>> paths = Paths(base_dir=root, workspace=root / "ws", state=root / "state")
>>> assembly = assemble([local_runs_module(), module], base=BaseServices(paths=paths, registries=Registries()))
>>> [(r.id, r.state.value) for r in assembly.report]
[('link-runs-teams', 'active'), ('local-runs', 'active')]
>>> [rules] = assembly.ports(RUN_PREPARERS)
>>> rules.workspace.default_backend is None
True

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

### 해결 버튼 표(5.2R.5)

검증 이슈·노드 실패 코드 → 해결 버튼(`Fix.actions`)은 데이터 `data/issue_fixes.json`이다(입구·답변 없음,
백엔드 없음·모름, 알 수 없는 종류, 위임 깊이). `TeamRules`가 검증 이슈에 붙이고(`mod-runs` 선택 메서드
`annotate_issues`), 노드 서비스 `ERROR_FIXES`로 노드 실패(자식 Run의 `agent.no_backend` 등)에도 붙인다.
다른 표는 `load_issue_fixes(텍스트)`로 만들어 `TeamRules(issue_fixes=)`에 넘긴다.

```python
>>> from agent_console_link_runs_teams import DEFAULT_ISSUE_FIXES
>>> fix = DEFAULT_ISSUE_FIXES.fix_for("team.no_entry", team_kind="graph", graph_id="g1")
>>> fix.actions[0].target.role, fix.actions[0].target.id
('definition:graph', 'g1')

```

## 포트

| 방향 | 포트 | 모양 |
| --- | --- | --- |
| 필수 | `runs.starter` | `check(graph)`·`load_graph(id, version_hash=None)`(중첩 팀 조회에도 쓴다) |
| 필수 | `definitions.lookup` | `get(kind, id).document`(지문 재료 `kinds()`·`summaries(kind)`가 있으면 캐시 키로) |
| 선택 | `workspace.settings` / `resources.lookup` / `resources.types` | 공통 설정 / 리소스 조회 / 리소스 종류 |
| 선택(여러 제공자) | `definitions.checks` | `issues(kind, document) -> Sequence[Issue]`(검증 경로에 경고·정보를 붙인다) |
| 제공(multi) | `runs.preparers` / `runs.services` | `TeamRules`(노드 서비스에 중첩 팀 조회 `TEAM_LOOKUP` 포함, 팀 규칙에 중첩 검사) |
| 제공 | `graphs.validation` | `ValidationSummaries.summaries(graph_ids)` |
| 구독 | `definitions.saved` | 검증 요약 캐시 버리기 |

## 단독 실행

```bash
python -m agent_console_link_runs_teams [--with ID] [--config PATH] [--port 0] [--check]
```

`--with`가 없으면 `testing.local_runs_module`을 붙인다. 실제 실행까지 하려면 `--with mod-runs --with mod-definitions`.

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
