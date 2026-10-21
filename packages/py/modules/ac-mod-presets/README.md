# agent-console-mod-presets

Agent Console 프리셋 기능 모듈(design §3R.1.3, E-19). 프리셋 라이브러리 `agent-console-presets`를 서버에 꽂는다.

- 경로: `GET /presets`, `POST /presets/{id}/apply`(기본 충돌 정책 skip, 없는 id는 404. 요청 `project`가 있으면
  만든 정의에 범위를 찍는다 — `scope_stamp`, 생략 = 공용).
- 요약(`PresetSummary`, 5.2R.6): `featured`·`start_graph`·`badges`는 매니페스트 데이터다. `badges`에는 프리셋 항목이 쓰는
  실행 백엔드(항목 문서의 `backend` 값)의 디스크립터 `ui_hints.badge`를 덧붙인다(호스트 레지스트리 묶음의 `backends`,
  없으면 덧붙이지 않는다). `start_graph`는 생략하면 `default_entry`이고, 그 팀 구성이 항목에 없으면 null이다.
  웹은 적용 결과 `items`에서 `kind == graph`·`id == start_graph`의 `target_id`(이름 바꿈 반영)로 대화를 연다.
- 시작 훅: 설정 `apply_on_start`의 프리셋을 적용한다(없는 id면 시작 실패).
- 필수 포트: `definitions.store`(정의 저장소). 선택 포트: `definitions.checks`(여러 제공자, 저장 전 검사 —
  error 이슈가 있는 항목은 `failed`), `definitions.dependencies`(문서가 쓰는 정의 — 있으면 쓰는 정의부터 적용,
  예: 에이전트 → 자식 팀 구성 → 팀 구성. 통합 서버에서는 `link-definitions-teams`가 넣는다. 없으면 매니페스트 순서).
- 설정 `modules.options.mod-presets`(옛 최상위 `presets`는 4R.18부터 `settings.removed_key` 오류로 새 위치를 안내): `directories`(상대 경로는
  `base_dir` 기준)·`apply_on_start`·`on_conflict`.
- 웹 역할: `presets`.

## 설치

```bash
pip install agent-console-mod-presets
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-mod-presets
```

## 최소 사용

정의 저장소가 없으면 모듈은 꺼진다(이유 보고, 자동 보정 없음). 제공 모듈을 함께 조립하면 켜진다.

```python
>>> from agent_console_modkit import assemble
>>> from agent_console_mod_presets import module
>>> from agent_console_mod_presets.testing import local_definitions_module
>>> [(r.id, r.state.value) for r in assemble([module]).report]
[('mod-presets', 'unsatisfied')]
>>> [(r.id, r.state.value) for r in assemble([module, local_definitions_module()]).report]
[('local-definitions', 'active'), ('mod-presets', 'active')]

```

HTTP 없이 서비스로도 쓴다(프리셋 폴더가 비어 있어도 동작한다).

```python
>>> from agent_console_store import DEFAULT_KINDS, InMemoryDefinitionStore
>>> from agent_console_mod_presets import PresetService
>>> PresetService(InMemoryDefinitionStore(DEFAULT_KINDS), []).presets()
[]

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```

단독 실행(같은 modkit 호스트, 기본 127.0.0.1). `--with`를 주지 않으면 `testing.local_definitions_module`
(워크스페이스 폴더의 파일 저장소)을 붙인다. 다른 제공자를 쓰려면 `--with <모듈 id>`.

```bash
python -m agent_console_mod_presets [--with ID] [--config PATH] [--port 0] [--check]
```
