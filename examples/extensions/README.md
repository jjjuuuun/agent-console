<!-- 이 파일은 `uv run poe extdocs`가 만든다. 직접 고치지 않는다. -->

# 확장 예제

예제 하나가 확장 지점 하나 이상을 보인다. 설치·제거·테스트는 각 README를 본다.

| 예제 | 언어 | 보이는 지점 | 설치 |
| --- | --- | --- | --- |
| [agent-console-example-architecture](agent-console-example-architecture/README.md) | python | `architecture-profile` 구조도 프로필 | `uv pip install -e examples/extensions/agent-console-example-architecture` |
| [agent-console-example-backend](agent-console-example-backend/README.md) | python | `backend-session-archive` 백엔드 세션 기록 보관·복원, `execution-backend` 실행 백엔드 | `uv pip install -e examples/extensions/agent-console-example-backend` |
| [agent-console-example-collector](agent-console-example-collector/README.md) | python | `collector` 관측 수집기 | `uv pip install -e examples/extensions/agent-console-example-collector` |
| [agent-console-example-condition](agent-console-example-condition/README.md) | python | `condition-operator` 조건 연산자 | `uv pip install -e examples/extensions/agent-console-example-condition` |
| [agent-console-example-delegation](agent-console-example-delegation/README.md) | python | `delegation-strategy` 위임 방식 | `uv pip install -e examples/extensions/agent-console-example-delegation` |
| [agent-console-example-edges](agent-console-example-edges/README.md) | python | `edge-type` 연결 종류 | `uv pip install -e examples/extensions/agent-console-example-edges` |
| [agent-console-example-interactions](agent-console-example-interactions/README.md) | python | `interaction-kind` 상호작용 종류 | `uv pip install -e examples/extensions/agent-console-example-interactions` |
| [agent-console-example-link](agent-console-example-link/README.md) | python | `agent-tool-provider` 에이전트 도구 공급자, `resource-type` 리소스 종류, `run-scope` 실행 범위 | `uv pip install -e examples/extensions/agent-console-example-link` |
| [agent-console-example-log-source](agent-console-example-log-source/README.md) | python | `log-classifier` 로그 분류기, `log-source` 로그 출처 | `uv pip install -e examples/extensions/agent-console-example-log-source` |
| [agent-console-example-memory-scope](agent-console-example-memory-scope/README.md) | python | `memory-scope-kind` 메모리 범위 종류 | `uv pip install -e examples/extensions/agent-console-example-memory-scope` |
| [agent-console-example-module](agent-console-example-module/README.md) | python | `definition-kind-contribution` 정의 종류 기여, `migration-scope` 모듈 계보 범위, `server-module` 서버 모듈 | `uv pip install -e examples/extensions/agent-console-example-module` |
| [agent-console-example-nodes](agent-console-example-nodes/README.md) | python | `node-type` 노드 종류 | `uv pip install -e examples/extensions/agent-console-example-nodes` |
| [agent-console-example-sdd-junit](agent-console-example-sdd-junit/README.md) | python | `sdd-verification-source` 검증 결과 출처 | `uv pip install -e examples/extensions/agent-console-example-sdd-junit` |
| [agent-console-example-secret-provider](agent-console-example-secret-provider/README.md) | python | `secret-provider` 비밀 값 공급자 | `uv pip install -e examples/extensions/agent-console-example-secret-provider` |
| [agent-console-example-transfer](agent-console-example-transfer/README.md) | python | `exporter` 내보내기 형식, `import-source` 가져오기 출처 | `uv pip install -e examples/extensions/agent-console-example-transfer` |
| [agent-console-example-usage](agent-console-example-usage/README.md) | python | `usage-source` 사용량 출처 | `uv pip install -e examples/extensions/agent-console-example-usage` |
| [agent-console-example-wiki-check](agent-console-example-wiki-check/README.md) | python | `wiki-write-check` 위키 쓰기 검사 보탬 | `uv pip install -e examples/extensions/agent-console-example-wiki-check` |
| [agent-console-example-wiki-search](agent-console-example-wiki-search/README.md) | python | `wiki-search-index` 위키 검색 색인 | `uv pip install -e examples/extensions/agent-console-example-wiki-search` |
| [@agent-console/example-web](../web/agent-console-example-web/README.md) | ts | `architecture-cell-renderer` 구조도 칸·연결 그리기, `config-form-widget` 설정 폼 위젯, `dashboard-widget` 대시보드 위젯 | `pnpm --filter @agent-console/example-web test` |
