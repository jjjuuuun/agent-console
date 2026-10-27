# agent-console-link-definitions-teams

Agent Console 정의 ↔ 팀 의미 연동 모듈(design §3R.1.4 L9, R2·R13.5). 정의 저장소와 `ac-teams` 계산을 잇는다.

- 경로: `GET /agents/{id}/usages`·`GET /resources/{id}/usages`(붙은 곳), `GET /agents/{id}/effective-settings`,
  `GET /graphs/{id}/plan`·`POST /graphs/plan`(초안), `GET /graphs/{id}/nodes/{node}/effective-settings`·
  `POST /graphs/effective-settings`, `GET /graphs/{id}/nodes/{node}/bundle-preview`·`POST /graphs/bundle-preview`.
  `x-secret` 평문과 해석한 비밀 값은 가린다.
- 제공 포트: `graphs.entry_labels`(팀 구성 목록 입구 이름), `definitions.usages`(리소스 목록 `usage_count`),
  `definitions.dependencies`(문서가 쓰는 정의 `TeamDocumentDependencies` — 팀 구성 → 에이전트·리소스·자식 팀 구성,
  에이전트 → 리소스. 여러 정의를 한꺼번에 쓸 때 쓰는 정의부터 쓰는 순서를 정하는 데 쓴다. 지금 기본 모듈 중
  소비자는 없다),
  `definitions.references`(X25, 여러 제공자 — 같은 계산의 참조 추출 함수 `(kind, doc) -> [(kind, id)]`,
  `TeamDocumentDependencies.references`. 프로젝트 범위 검사·옮기기 계획이 주입받는다).
- 필수 포트: `definitions.lookup`. 선택: `workspace.settings`, `resources.lookup`·`resources.types`(없으면 빈 것),
  `secrets.redact`(없으면 `secrets.rules`의 의심 값 가리기), `secrets.rules`.
- 디스크립터: 호스트 기본 서비스 `registries`(노드·엣지·위임 방식·백엔드)를 요청마다 읽는다(`catalog_from_registries`).
- 웹 역할(`WEB_ROLES`): `definitions:teams` — 팀 구성 편집기의 초안 미리보기(`POST /graphs/plan`·`effective-settings`·`bundle-preview`)와 에이전트 사용처 패널(`GET /agents/{id}/usages`)이 이 역할로 켜진다.
- 꺼지면: 위 경로는 404(웹이 해당 패널을 숨김), 목록의 입구 이름·사용 수는 null.

## 설치

```bash
pip install agent-console-link-definitions-teams
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-link-definitions-teams
```

## 최소 사용

`TeamViews`는 서버 없이 쓴다. 정의 읽기(저장소)와 디스크립터 묶음을 넘긴다.

```python
>>> from agent_console_store import InMemoryDefinitionStore
>>> from agent_console_teams import TeamCatalog
>>> from agent_console_teams.testing import Kit
>>> from agent_console_link_definitions_teams import TeamViews
>>> kit = Kit()
>>> store = InMemoryDefinitionStore()
>>> graph = kit.graph([kit.person(), kit.worker("a", "alice")], [kit.edge("e1", "entry", "me", "a")])
>>> _ = store.create("graph", graph.model_dump(mode="json", exclude_none=True))
>>> catalog = TeamCatalog(node_types=tuple(kit.node_types), edge_types=tuple(kit.edge_types))
>>> views = TeamViews(store, catalog=lambda: catalog)
>>> [(r.kind, r.id, r.node_ids) for r in views.references("agent", "alice")]
[('graph', 'team', ['a'])]
>>> views.entry_labels(graph)
['A']

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

단독 실행. `--with`를 주지 않으면 `testing.local_definitions_module`(워크스페이스 파일 저장소)을 붙인다.

```bash
python -m agent_console_link_definitions_teams [--with ID] [--config PATH] [--port 0] [--check]
```
