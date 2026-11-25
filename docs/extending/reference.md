<!-- 이 파일은 `uv run poe extdocs`가 만든다. 직접 고치지 않는다. -->

# 확장 지점 참조

패키지 선언과 코드에서 만든 표다. 설명은 영역 페이지에 있다.

## 확장 지점

| 영역 | slug | 제목 | 등록 종류 | 등록 이름 | 기본 구현 수 | 예제 종류 |
| --- | --- | --- | --- | --- | --- | --- |
| 그래프·실행 | [condition-operator](graph.md#condition-operator) | 조건 연산자 | entry-point | `agent_console.condition_operators` | 11 | package |
| 그래프·실행 | [delegation-strategy](graph.md#delegation-strategy) | 위임 방식 | entry-point | `agent_console.delegation_strategies` | 2 | package |
| 그래프·실행 | [edge-type](graph.md#edge-type) | 연결 종류 | entry-point | `agent_console.edge_types` | 11 | package |
| 그래프·실행 | [interaction-kind](graph.md#interaction-kind) | 상호작용 종류 | entry-point | `agent_console.interaction_kinds` | 3 | package |
| 그래프·실행 | [node-type](graph.md#node-type) | 노드 종류 | entry-point | `agent_console.node_types` | 5 | package |
| 실행 백엔드 | [backend-session-archive](backends.md#backend-session-archive) | 백엔드 세션 기록 보관·복원 | capability | `session_archive` | — | package, reference |
| 실행 백엔드 | [execution-backend](backends.md#execution-backend) | 실행 백엔드 | entry-point | `agent_console.backends` | 2 | package |
| 실행 백엔드 | [secret-provider](backends.md#secret-provider) | 비밀 값 공급자 | entry-point | `agent_console.secret_providers` | — | package |
| 리소스 | [resource-type](resources.md#resource-type) | 리소스 종류 | entry-point | `agent_console.resource_types` | 9 | package, reference |
| 사용량 | [runtime-usage-source](usage.md#runtime-usage-source) | 런타임 사용량 출처 | port | `usage.sources` | 1 | reference |
| 사용량 | [usage-source](usage.md#usage-source) | 사용량 출처 | entry-point | `agent_console.usage_sources` | 3 | package |
| 로그 | [collector](logs.md#collector) | 관측 수집기 | entry-point | `agent_console.collectors` | 2 | package |
| 로그 | [log-classifier](logs.md#log-classifier) | 로그 분류기 | entry-point | `agent_console.log_classifiers` | 4 | package |
| 로그 | [log-filter-predicate](logs.md#log-filter-predicate) | 로그 필터 확장 | port | `logs.filter_predicates` | 1 | reference |
| 로그 | [log-scope-kind](logs.md#log-scope-kind) | 로그 범위 종류 | port | `logs.scope_kinds` | 1 | reference |
| 로그 | [log-source](logs.md#log-source) | 로그 출처 | entry-point | `agent_console.log_sources` | 4 | package |
| 로그 | [runtime-log-source](logs.md#runtime-log-source) | 런타임 로그 출처 | port | `logs.sources` | 1 | reference |
| 가져오기·내보내기 | [exporter](transfer.md#exporter) | 내보내기 형식 | entry-point | `agent_console.exporters` | 1 | package |
| 가져오기·내보내기 | [import-source](transfer.md#import-source) | 가져오기 출처 | entry-point | `agent_console.import_sources` | 1 | package |
| 서버 호스트·모듈 | [definition-kind-contribution](host.md#definition-kind-contribution) | 정의 종류 기여 | port | `definitions.kind_contributions` | 2 | package |
| 서버 호스트·모듈 | [definition-store](host.md#definition-store) | 정의 저장소 | injection | — | — | reference |
| 서버 호스트·모듈 | [host-database](host.md#host-database) | 호스트 DB 공장 | entry-point | `agent_console.host_database` | 1 | contract-tests |
| 서버 호스트·모듈 | [host-plugin-loader](host.md#host-plugin-loader) | 호스트 플러그인 로더 | entry-point | `agent_console.host_plugin_loaders` | 11 | contract-tests |
| 서버 호스트·모듈 | [host-registries](host.md#host-registries) | 호스트 레지스트리 묶음 | entry-point | `agent_console.host_registries` | 1 | reference |
| 서버 호스트·모듈 | [migration-scope](host.md#migration-scope) | 모듈 계보 범위 | descriptor | `MigrationBranch.scopes` | — | package |
| 서버 호스트·모듈 | [run-labels](host.md#run-labels) | 실행 라벨 | field | `Run.labels` | — | snippet |
| 서버 호스트·모듈 | [server-module](host.md#server-module) | 서버 모듈 | entry-point | `agent_console.server_modules` | 33 | contract-tests, package |
| 프로젝트 | [definition-reference-rewriter](projects.md#definition-reference-rewriter) | 정의 참조 고치기 | port | `definitions.reference_rewriters` | — | snippet |
| 프로젝트 | [definition-references](projects.md#definition-references) | 정의 참조 추출 | port | `definitions.references` | 1 | reference |
| 프로젝트 | [folder-browse-defaults](projects.md#folder-browse-defaults) | 폴더 탐색 시작 위치·숨김 이름 | data | `data/browse_defaults.json` | — | snippet |
| 프로젝트 | [folder-dialog-provider](projects.md#folder-dialog-provider) | 폴더 선택 창 제공자 | entry-point | `agent_console.folder_dialogs` | — | reference, snippet |
| 프로젝트 | [path-field](projects.md#path-field) | 경로 필드 표시 | annotation | `x-path` | — | snippet |
| 프로젝트 | [portable-definition-kind](projects.md#portable-definition-kind) | 프로젝트 공간에 들어가는 정의 종류 | descriptor | `DefinitionKind.portable` | — | snippet |
| 프로젝트 | [project-space-layout](projects.md#project-space-layout) | 프로젝트 폴더 배치·.gitignore 틀 | data | `data/gitignore.template` | — | snippet |
| 프로젝트 | [run-scope](projects.md#run-scope) | 실행 범위 | port | `runs.scopes` | 3 | package, reference |
| 프로젝트 | [settings-scope-layer](projects.md#settings-scope-layer) | 범위 설정 층 | port | `settings.scope_layers` | 1 | reference |
| 구조도 | [architecture-profile](architecture.md#architecture-profile) | 구조도 프로필 | entry-point | `agent_console.architecture_profiles` | — | package, snippet |
| 구조도 | [architecture-profile-check](architecture.md#architecture-profile-check) | 구조도 프로필 검사 보탬 | port | `architecture.profile_checks` | 1 | reference |
| 메모리 | [agent-tool-provider](memory.md#agent-tool-provider) | 에이전트 도구 공급자 | service | `agent_console_nodes_core:TOOL_PROVIDERS` | — | contract-tests, package |
| 메모리 | [memory-scope-kind](memory.md#memory-scope-kind) | 메모리 범위 종류 | entry-point | `agent_console.memory_scope_kinds` | — | package, snippet |
| 메모리 | [memory-store](memory.md#memory-store) | 메모리 저장소 | injection | — | — | contract-tests |
| SDD | [sdd-syntax](sdd.md#sdd-syntax) | 작업 문법·요구 ID·단계 규칙 | data | `data/default_syntax.yaml` | — | snippet |
| SDD | [sdd-task-integration](sdd.md#sdd-task-integration) | 작업 연동 | port | `sdd.integrations` | 1 | reference |
| SDD | [sdd-verification-source](sdd.md#sdd-verification-source) | 검증 결과 출처 | entry-point | `agent_console.sdd_verification_sources` | — | package, reference |
| SDD | [spec-template](sdd.md#spec-template) | 문서 틀 | definition | `spec-template` | — | snippet |
| 위키 | [wiki-history](wiki.md#wiki-history) | 페이지 기록 저장소 | injection | — | — | contract-tests |
| 위키 | [wiki-rules](wiki.md#wiki-rules) | 위키 규칙 | definition | `wiki-rules` | — | snippet |
| 위키 | [wiki-search-index](wiki.md#wiki-search-index) | 위키 검색 색인 | entry-point | `agent_console.wiki_search_indexes` | — | contract-tests, package |
| 위키 | [wiki-syntax](wiki.md#wiki-syntax) | 위키 문법 | data | `data/default_syntax.yaml` | — | snippet |
| 위키 | [wiki-write-check](wiki.md#wiki-write-check) | 위키 쓰기 검사 보탬 | entry-point | `agent_console.wiki_write_checks` | — | package |
| 웹 | [architecture-cell-renderer](web.md#architecture-cell-renderer) | 구조도 칸·연결 그리기 | props | `@agent-console/arch-view#ArchitectureDiagramProps` | — | package |
| 웹 | [config-form-widget](web.md#config-form-widget) | 설정 폼 위젯 | registry | `@agent-console/web/src/features/delegation/configWidgets.ts#CONFIG_WIDGETS` | — | package |
| 웹 | [dashboard-widget](web.md#dashboard-widget) | 대시보드 위젯 | props | `@agent-console/log-view#DashboardGridProps` | — | package |
| 웹 | [interaction-renderer](web.md#interaction-renderer) | 상호작용 renderer | props | `@agent-console/chat#defaultRenderers` | — | reference |
| 웹 | [screen-entry](web.md#screen-entry) | 화면 진입 | registry | `@agent-console/web/src/shell/routeConfig.ts#DEFAULT_ROUTES` | — | reference |

## entry point 그룹

| 그룹 | 정의 상수 | 기본 등록 |
| --- | --- | --- |
| `agent_console.architecture_profiles` | `agent_console_architecture:ARCHITECTURE_PROFILES_GROUP` | — |
| `agent_console.backends` | `agent_console_runtime:BACKENDS_GROUP` | `claude-agent-sdk` (agent-console-backend-claude-sdk), `fake-agent` (agent-console-backend-fake-agent) |
| `agent_console.collectors` | `agent_console_backend_claude_sdk.collectors:COLLECTORS_GROUP` | `mcp-calls` (agent-console-backend-claude-sdk), `sdk-hooks` (agent-console-backend-claude-sdk) |
| `agent_console.condition_operators` | `agent_console_conditions:CONDITION_OPERATORS_GROUP` | `any_item` (agent-console-conditions), `contains` (agent-console-conditions), `eq` (agent-console-conditions), `exists` (agent-console-conditions), `gt` (agent-console-conditions), `gte` (agent-console-conditions), `in` (agent-console-conditions), `lt` (agent-console-conditions), `lte` (agent-console-conditions), `matches` (agent-console-conditions), `ne` (agent-console-conditions) |
| `agent_console.config_schemas` | — | `log-source-platform-runs` (agent-console-link-logs-runs), `usage-source-local-logs` (agent-console-link-logs-usage) |
| `agent_console.delegation_strategies` | `agent_console_runtime:DELEGATION_STRATEGIES_GROUP` | `host` (agent-console-delegation-host), `sdk-subagents` (agent-console-nodes-core) |
| `agent_console.edge_types` | `agent_console_runtime:EDGE_TYPES_GROUP` | `ask_user` (agent-console-nodes-core), `data` (agent-console-nodes-core), `delegate` (agent-console-nodes-core), `handoff` (agent-console-nodes-core), `loop` (agent-console-nodes-core), `message` (agent-console-nodes-core), `on_error` (agent-console-nodes-core), `reply` (agent-console-nodes-core), `subagent` (agent-console-nodes-core), `uses` (agent-console-nodes-core), `when` (agent-console-nodes-core) |
| `agent_console.exporters` | `agent_console_exports:EXPORTERS_GROUP` | `claude-dir` (agent-console-exports) |
| `agent_console.folder_dialogs` | `agent_console_mod_projects:FOLDER_DIALOGS_GROUP` | — |
| `agent_console.host_database` | `agent_console_modkit:HOST_DATABASE_GROUP` | `sqlite` (agent-console-store) |
| `agent_console.host_plugin_loaders` | `agent_console_modkit:HOST_PLUGIN_LOADERS_GROUP` | `architecture` (agent-console-mod-architecture), `exports` (agent-console-mod-exports), `imports` (agent-console-mod-imports), `logs` (agent-console-mod-logs), `memory` (agent-console-mod-memory), `projects` (agent-console-mod-projects), `resources` (agent-console-mod-resources), `runs` (agent-console-mod-runs), `sdd` (agent-console-mod-sdd), `usage` (agent-console-mod-usage), `wiki` (agent-console-mod-wiki) |
| `agent_console.host_registries` | `agent_console_modkit:HOST_REGISTRIES_GROUP` | `runs` (agent-console-mod-runs) |
| `agent_console.import_sources` | `agent_console_imports:IMPORT_SOURCES_GROUP` | `claude` (agent-console-imports) |
| `agent_console.interaction_kinds` | `agent_console_runtime:INTERACTION_KINDS_GROUP` | `question` (agent-console-nodes-core), `review` (agent-console-nodes-core), `tool_permission` (agent-console-nodes-core) |
| `agent_console.log_classifiers` | `agent_console_logs:LOG_CLASSIFIERS_GROUP` | `claude-code` (agent-console-logs-claude), `hook-probe` (agent-console-hook-probe), `mapped-jsonl` (agent-console-logs), `normalized-v1` (agent-console-logs) |
| `agent_console.log_sources` | `agent_console_logs:LOG_SOURCES_GROUP` | `claude-code-jsonl` (agent-console-logs-claude), `hook-probe-jsonl` (agent-console-hook-probe), `mapped-jsonl` (agent-console-logs), `normalized-v1` (agent-console-logs) |
| `agent_console.memory_scope_kinds` | `agent_console_memory:MEMORY_SCOPE_KINDS_GROUP` | — |
| `agent_console.node_types` | `agent_console_runtime:NODE_TYPES_GROUP` | `agent` (agent-console-nodes-core), `resource` (agent-console-nodes-core), `team` (agent-console-nodes-core), `user` (agent-console-nodes-core), `wiki-update` (agent-console-link-wiki-runs) |
| `agent_console.resource_types` | `agent_console_resources:RESOURCE_TYPES_GROUP` | `file` (agent-console-resources-core), `hook` (agent-console-resources-core), `instruction` (agent-console-resources-core), `mcp-server` (agent-console-resources-core), `memory` (agent-console-link-memory-runs), `rule` (agent-console-resources-core), `skill` (agent-console-resources-core), `tool-permission` (agent-console-resources-core), `wiki` (agent-console-link-wiki-runs) |
| `agent_console.sdd_verification_sources` | `agent_console_mod_sdd:VERIFICATION_SOURCES_GROUP` | — |
| `agent_console.secret_providers` | `agent_console_runtime:SECRET_PROVIDERS_GROUP` | — |
| `agent_console.server_modules` | `agent_console_modkit:MODULES_GROUP` | `link-chat-runs` (agent-console-link-chat-runs), `link-definitions-resources` (agent-console-link-definitions-resources), `link-definitions-teams` (agent-console-link-definitions-teams), `link-exports-teams` (agent-console-link-exports-teams), `link-logs-architecture` (agent-console-link-logs-architecture), `link-logs-runs` (agent-console-link-logs-runs), `link-logs-trace` (agent-console-link-logs-trace), `link-logs-usage` (agent-console-link-logs-usage), `link-memory-runs` (agent-console-link-memory-runs), `link-projects-memory` (agent-console-link-projects-memory), `link-projects-records` (agent-console-link-projects-records), `link-projects-runs` (agent-console-link-projects-runs), `link-projects-sdd` (agent-console-link-projects-sdd), `link-projects-wiki` (agent-console-link-projects-wiki), `link-runs-sdd` (agent-console-link-runs-sdd), `link-runs-teams` (agent-console-link-runs-teams), `link-runs-trace` (agent-console-link-runs-trace), `link-runs-usage` (agent-console-link-runs-usage), `link-wiki-runs` (agent-console-link-wiki-runs), `mod-architecture` (agent-console-mod-architecture), `mod-chat` (agent-console-mod-chat), `mod-definitions` (agent-console-mod-definitions), `mod-exports` (agent-console-mod-exports), `mod-imports` (agent-console-mod-imports), `mod-logs` (agent-console-mod-logs), `mod-memory` (agent-console-mod-memory), `mod-projects` (agent-console-mod-projects), `mod-resources` (agent-console-mod-resources), `mod-runs` (agent-console-mod-runs), `mod-sdd` (agent-console-mod-sdd), `mod-usage` (agent-console-mod-usage), `mod-versions` (agent-console-mod-versions), `mod-wiki` (agent-console-mod-wiki) |
| `agent_console.usage_sources` | `agent_console_usage:USAGE_SOURCES_GROUP` | `fake` (agent-console-usage), `run-events` (agent-console-usage), `statusline-file` (agent-console-usage) |
| `agent_console.wiki_search_indexes` | `agent_console_wiki:SEARCH_INDEX_GROUP` | — |
| `agent_console.wiki_write_checks` | `agent_console_mod_wiki:WRITE_CHECKS_GROUP` | — |

## 포트

| 포트 | 제공 | 필수 소비 | 선택 소비 | 다중 | 내부 사유 |
| --- | --- | --- | --- | --- | --- |
| `architecture.catalog` | mod-architecture | link-logs-architecture | — | 아니오 | 구조도 모듈이 병합한 프로필 카탈로그를 연동 모듈에 주는 통로(구현은 이 모듈 하나). 프로필은 architecture-profile 지점으로 더한다 |
| `architecture.profile_checks` | link-logs-architecture | — | mod-architecture | 예 |  |
| `chat.conversations` | mod-chat | link-chat-runs | — | 아니오 | 대화 모듈이 연동 모듈에 주는 서비스 통로(구현은 이 모듈 하나) |
| `chat.interactions` | link-chat-runs | — | mod-chat | 아니오 | 대화-실행 연동이 턴 상호작용 조회를 붙이는 모듈 사이 통로 |
| `chat.move_hooks` | link-chat-runs | — | mod-chat | 예 | 대화 옮기기에 딸린 실행 기록 옮기기를 묶는 모듈 사이 통로(대화-실행 연동이 제공) |
| `chat.run_events` | link-chat-runs | — | mod-chat | 아니오 | 대화-실행 연동이 턴 이벤트 조회를 붙이는 모듈 사이 통로 |
| `chat.runs` | link-chat-runs | — | mod-chat | 아니오 | 대화-실행 연동이 턴 Run 조회를 붙이는 모듈 사이 통로 |
| `chat.turn_launcher` | link-chat-runs | — | mod-chat | 아니오 | 대화-실행 연동이 턴 실행을 붙이는 모듈 사이 통로(구현은 그 연동 하나) |
| `chat.turn_sessions` | link-chat-runs | — | mod-chat | 아니오 | 대화-실행 연동이 턴 세션 수집·정리 규칙을 주는 모듈 사이 통로 |
| `definitions.checks` | link-definitions-resources, link-memory-runs, link-wiki-runs, mod-definitions, mod-usage | — | link-runs-teams, mod-definitions, mod-resources, mod-versions | 예 | 기능 모듈·연동이 저장 전 정의 검사를 정의 모듈에 보태는 모듈 사이 다중 통로. 새 정의 종류의 검사는 definition-kind-contribution 지점 |
| `definitions.dependencies` | link-definitions-teams | — | — | 아니오 | 팀 구성 연동이 정의 사이 의존을 계산해 주는 모듈 사이 통로(구현은 그 연동 하나) |
| `definitions.kind_contributions` | mod-sdd, mod-wiki | — | mod-definitions, mod-projects | 예 |  |
| `definitions.lookup` | mod-definitions | link-definitions-resources, link-definitions-teams, link-exports-teams, link-runs-teams, mod-exports, mod-runs | link-projects-runs, link-runs-trace, mod-chat, mod-projects | 아니오 | 정의 모듈이 다른 기능 모듈·연동에 주는 정의 읽기 통로(구현은 이 모듈 하나). 저장소를 바꾸는 확장은 definition-store 지점 |
| `definitions.reference_rewriters` | — | — | mod-projects | 예 |  |
| `definitions.references` | link-definitions-teams | — | mod-projects | 예 |  |
| `definitions.save_warnings` | mod-definitions | — | mod-resources | 아니오 | 정의 모듈이 저장 응답의 평문 비밀 경고 계산을 리소스 모듈에 주는 모듈 사이 통로(구현은 이 모듈 하나) |
| `definitions.spaces` | mod-projects | — | link-definitions-resources, link-definitions-teams, link-projects-runs, link-runs-trace, mod-chat, mod-definitions, mod-exports, mod-imports, mod-resources, mod-versions | 아니오 | 프로젝트 모듈이 공간 이름 → 정의 저장소를 기능 모듈에 주는 모듈 사이 통로 |
| `definitions.store` | mod-definitions | mod-imports, mod-resources, mod-versions | mod-projects, mod-sdd, mod-wiki | 아니오 | 정의 모듈이 다른 기능 모듈에 주는 정의 저장소 통로(구현은 이 모듈 하나). 저장소를 바꾸는 확장은 definition-store 지점 |
| `definitions.usages` | link-definitions-teams | — | mod-resources | 아니오 | 팀 구성 연동이 정의가 붙은 곳을 리소스 모듈에 주는 모듈 사이 통로(구현은 그 연동 하나) |
| `exports.dependencies` | link-exports-teams | — | mod-exports | 아니오 | 팀 구성 연동이 함께 내보낼 정의를 계산해 주는 모듈 사이 통로. 새 내보내기 형식은 exporter 지점 |
| `graphs.entry_labels` | link-definitions-teams | — | mod-definitions | 아니오 | 팀 구성 연동이 팀 구성 입구 이름을 정의 모듈에 주는 모듈 사이 통로 |
| `graphs.session_summary` | link-definitions-teams | — | mod-definitions | 아니오 | 팀 구성 연동이 목록용 세션 집계를 정의 모듈에 주는 모듈 사이 통로 |
| `graphs.validation` | link-runs-teams | — | mod-definitions | 아니오 | 실행-팀 구성 연동이 목록용 검증 요약을 정의 모듈에 주는 모듈 사이 통로 |
| `interactions.port` | mod-runs | — | link-chat-runs | 아니오 | 실행 모듈이 상호작용 조회·응답을 대화 연동에 주는 통로. 새 상호작용 종류는 interaction-kind 지점 |
| `logs.filter_predicates` | link-logs-architecture | — | mod-logs | 예 |  |
| `logs.ingest` | mod-logs | link-logs-runs | link-logs-usage | 아니오 | 로그 모듈이 런타임 출처 수집·수집 예약을 연동 모듈에 주는 통로(구현은 이 모듈 하나) |
| `logs.query` | mod-logs | link-logs-architecture, link-logs-runs, link-logs-trace, link-logs-usage | — | 아니오 | 로그 모듈이 색인 읽기를 연동 모듈에 주는 통로(구현은 이 모듈 하나) |
| `logs.scope_kinds` | link-logs-runs | — | mod-logs | 예 |  |
| `logs.source_defaults` | link-logs-usage | — | mod-logs | 예 | 연동 모듈이 자기 출처의 기본 켜기 값을 로그 모듈에 알리는 모듈 사이 통로. 새 출처는 log-source·runtime-log-source 지점 |
| `logs.sources` | link-logs-runs | — | mod-logs | 예 |  |
| `memory.service` | mod-memory | link-memory-runs | — | 아니오 | 메모리 모듈이 연동 모듈(실행 도구)에 주는 서비스 통로(구현은 이 모듈 하나) |
| `memory.spaces` | link-projects-memory | — | mod-memory | 아니오 | 프로젝트 연동이 공간 이름 → 메모리 저장소를 주는 모듈 사이 통로. 저장소 교체는 memory-store 지점 |
| `projects.folders` | mod-projects | — | mod-exports, mod-imports, mod-logs | 아니오 | 등록된 프로젝트 폴더를 다른 기능 모듈에 주는 통로(구현은 이 모듈 하나) |
| `projects.lookup` | mod-projects | link-projects-runs | link-logs-runs, link-projects-memory, link-runs-usage, link-wiki-runs, mod-chat, mod-runs | 아니오 | 프로젝트 모듈이 연동 모듈과 기능 모듈(대화·실행의 위치 찾기 등)에 주는 읽기 통로(구현은 이 모듈 하나) |
| `projects.spaces` | mod-projects | link-projects-memory, link-projects-records, link-projects-sdd, link-projects-wiki | — | 아니오 | 프로젝트 공간을 연동 모듈에 여는 통로(구현은 이 모듈 하나) |
| `records.sessions` | link-projects-records | — | mod-chat | 아니오 | 대화 모듈이 프로젝트 기록 공간의 세션 이어 가기 상태를 받는 모듈 사이 통로. 새 백엔드의 세션 보관은 backend-session-archive 지점 |
| `records.spaces` | link-projects-records | — | link-runs-usage, mod-chat, mod-projects, mod-runs, mod-wiki | 아니오 | 프로젝트 연동이 공간 이름 → 프로젝트 기록 DB를 기능 모듈에 주는 모듈 사이 통로(구현은 이 연동 하나) |
| `resources.lookup` | mod-resources | — | link-definitions-resources, link-definitions-teams, link-runs-teams | 아니오 | 리소스 모듈이 리소스 정의·본문 조회를 연동 모듈에 주는 통로(구현은 이 모듈 하나) |
| `resources.types` | mod-resources | link-definitions-resources | link-definitions-teams, link-runs-teams | 아니오 | 리소스 모듈이 등록된 리소스 종류 레지스트리를 연동 모듈에 주는 통로. 새 종류는 resource-type 지점 |
| `runs.events` | mod-runs | link-chat-runs, link-logs-runs, link-runs-trace, link-runs-usage | — | 아니오 | 실행 모듈이 실행 이벤트 조회를 연동 모듈에 주는 통로(구현은 이 모듈 하나) |
| `runs.move_hook` | mod-runs | — | link-chat-runs | 아니오 | 실행 모듈이 대화 옮기기에 딸린 Run 옮기기 훅을 대화 연동에 주는 통로 |
| `runs.preparers` | link-runs-teams | — | mod-runs | 예 | 팀 구성 연동이 실행 전 검사·준비를 실행 모듈에 보태는 모듈 사이 다중 통로 |
| `runs.reader` | mod-runs | link-chat-runs, link-logs-runs, link-runs-sdd, link-runs-trace, link-runs-usage | link-projects-records | 아니오 | 실행 모듈이 Run·NodeRun 조회를 연동 모듈에 주는 통로(구현은 이 모듈 하나) |
| `runs.resume_handlers` | link-chat-runs | — | mod-runs | 예 | 대화 연동이 이어 가기 처리기를 실행 모듈에 보태는 모듈 사이 다중 통로 |
| `runs.scopes` | link-memory-runs, link-projects-runs, link-wiki-runs | — | mod-runs | 예 |  |
| `runs.services` | link-runs-teams, link-wiki-runs | — | mod-runs | 예 | 연동 모듈이 노드 서비스를 실행 모듈에 보태는 모듈 사이 다중 통로. Run마다 도구를 더하는 확장은 run-scope·agent-tool-provider 지점 |
| `runs.session_archive` | mod-runs | — | link-projects-records | 아니오 | 실행 모듈이 백엔드 id → 세션 기록 보관을 프로젝트 기록 연동에 주는 통로. 새 백엔드의 보관 능력은 backend-session-archive 지점 |
| `runs.starter` | mod-runs | link-chat-runs, link-runs-sdd, link-runs-teams | — | 아니오 | 실행 모듈이 실행 시작·검증·취소를 연동 모듈에 주는 통로(구현은 이 모듈 하나) |
| `sdd.integrations` | link-runs-sdd | — | mod-sdd | 예 |  |
| `sdd.service` | mod-sdd | link-runs-sdd | — | 아니오 | 스펙 모듈이 연동 모듈에 주는 서비스 통로(구현은 이 모듈 하나) |
| `sdd.spaces` | link-projects-sdd | — | mod-sdd | 아니오 | 프로젝트 연동이 공간 이름 → 스펙 저장 공간을 주는 모듈 사이 통로 |
| `sdd.verification_sources` | link-runs-sdd | — | mod-sdd | 예 |  |
| `secrets.redact` | mod-runs | — | link-definitions-teams | 아니오 | 실행 모듈이 해석한 비밀 값 가리기를 연동 모듈에 주는 통로(구현은 이 모듈 하나) |
| `secrets.rules` | mod-definitions | — | link-definitions-resources, link-definitions-teams, mod-exports, mod-imports, mod-logs, mod-projects, mod-runs, mod-sdd, mod-versions, mod-wiki | 아니오 | 정의 모듈이 지금 비밀 의심 규칙(사용자 설정)을 다른 모듈에 나눠 주는 통로. 비밀 값 출처를 더하는 확장은 secret-provider 지점 |
| `server.attributes` | mod-runs | — | — | 예 | 모듈이 서버 정보(GET /server-info) 속성을 보태는 호스트 통로 — 모듈 작성 공통 사항(서버 모듈 안내)으로 다룬다 |
| `server.warnings` | link-projects-records, mod-architecture, mod-chat, mod-definitions, mod-logs, mod-memory, mod-runs, mod-sdd, mod-usage, mod-wiki | — | — | 예 | 모듈이 서버 정보(GET /server-info) 경고를 보태는 호스트 통로 — 모듈 작성 공통 사항(서버 모듈 안내)으로 다룬다 |
| `settings.scope_layers` | link-projects-runs | — | link-definitions-teams, link-exports-teams | 예 |  |
| `usage.event_query` | link-runs-usage | — | mod-usage | 아니오 | 실행-사용량 연동이 실행 이벤트 조회를 사용량 모듈에 주는 모듈 사이 통로(구현은 그 연동 하나) |
| `usage.service` | mod-usage | link-logs-usage | — | 아니오 | 사용량 모듈이 연동 모듈에 존재·보고 서비스를 알리는 통로(구현은 이 모듈 하나) |
| `usage.sources` | link-logs-usage | — | mod-usage | 예 |  |
| `usage.token_rollups` | link-runs-usage | — | mod-usage | 아니오 | 실행-사용량 연동이 플랫폼 실행분 토큰 집계를 주는 모듈 사이 통로(구현은 그 연동 하나) |
| `wiki.integrations` | link-wiki-runs | — | mod-wiki | 예 | 저장소 연동 모듈이 켜 주는 능력 이름을 알리는 모듈 사이 통로(능력 이름은 위키 모듈이 아는 것만 뜻이 있다) |
| `wiki.service` | mod-wiki | link-wiki-runs | — | 아니오 | 위키 모듈이 연동 모듈에 주는 서비스 통로(구현은 이 모듈 하나) |
| `wiki.spaces` | link-projects-wiki | — | mod-wiki | 아니오 | 프로젝트 연동이 공간 이름 → 위키 저장 공간을 주는 모듈 사이 통로 |
| `wiki.write_checks` | — | — | mod-wiki | 예 |  |
| `workspace.settings` | mod-definitions | — | link-definitions-teams, link-exports-teams, link-runs-teams, mod-architecture, mod-chat, mod-logs, mod-memory, mod-runs, mod-sdd, mod-usage, mod-wiki | 아니오 | 정의 모듈이 지금 워크스페이스 설정을 다른 모듈에 나눠 주는 통로(구현은 이 모듈 하나) |

## 서버 모듈

| id | 종류 | web_roles | 계약 하위 모듈 | 계보(범위) |
| --- | --- | --- | --- | --- |
| `link-chat-runs` | link | conversations:runs | chat 1.4.0, runs 1.9.0 | — |
| `link-definitions-resources` | link | — | resources 1.1.0 | — |
| `link-definitions-teams` | link | definitions:teams | definitions 2.0.0 | — |
| `link-exports-teams` | link | — | exports 1.0.0 | — |
| `link-logs-architecture` | link | logs:architecture | architecture 1.0.0, logs 2.0.0 | — |
| `link-logs-runs` | link | logs:runs | logs 2.0.0, runs 1.9.0 | — |
| `link-logs-trace` | link | logs:trace | logs 2.0.0, runs 1.9.0 | — |
| `link-logs-usage` | link | — | logs 2.0.0, usage 1.1.0 | — |
| `link-memory-runs` | link | memory:runs | memory 1.3.0, runs 1.9.0 | — |
| `link-projects-memory` | link | — | — | — |
| `link-projects-records` | link | — | — | — |
| `link-projects-runs` | link | — | — | — |
| `link-projects-sdd` | link | — | — | — |
| `link-projects-wiki` | link | — | — | — |
| `link-runs-sdd` | link | — | runs 1.9.0, sdd 1.3.0 | — |
| `link-runs-teams` | link | runs:team-rules | definitions 2.0.0 | — |
| `link-runs-trace` | link | runs:trace | runs 1.9.0 | — |
| `link-runs-usage` | link | usage:tokens | usage 1.1.0 | — |
| `link-wiki-runs` | link | wiki:runs | runs 1.9.0, wiki 1.3.0 | — |
| `mod-architecture` | feature | architecture | architecture 1.0.0 | — |
| `mod-chat` | feature | conversations | chat 1.4.0 | chat(app/project) |
| `mod-definitions` | feature | definitions:agent, definitions:graph, settings | definitions 2.0.0 | — |
| `mod-exports` | feature | exports | exports 1.0.0 | — |
| `mod-imports` | feature | imports | imports 1.1.0 | — |
| `mod-logs` | feature | logs | logs 2.0.0 | logs(app) |
| `mod-memory` | feature | memory | memory 1.3.0 | memory(app/memory) |
| `mod-projects` | feature | projects | projects 4.0.0 | — |
| `mod-resources` | feature | definitions:resource | resources 1.1.0 | — |
| `mod-runs` | feature | runs | runs 1.9.0 | runs(app/project) |
| `mod-sdd` | feature | sdd | sdd 1.3.0 | — |
| `mod-usage` | feature | usage | usage 1.1.0 | usage(app) |
| `mod-versions` | feature | versions | definitions 2.0.0 | — |
| `mod-wiki` | feature | wiki, wiki:rules | wiki 1.3.0 | wiki(app/project) |

## 계약 하위 모듈 버전

| 하위 모듈 | 버전 |
| --- | --- |
| `architecture` | 1.0.0 |
| `chat` | 1.4.0 |
| `common` | 2.0.0 |
| `definitions` | 2.0.0 |
| `exports` | 1.0.0 |
| `imports` | 1.1.0 |
| `logs` | 2.0.0 |
| `memory` | 1.3.0 |
| `modules` | 1.7.0 |
| `projects` | 4.0.0 |
| `resources` | 1.1.0 |
| `runs` | 1.9.0 |
| `sdd` | 1.3.0 |
| `usage` | 1.1.0 |
| `wiki` | 1.3.0 |

## 알려진 RunEvent type

- `agent.context_prepared`
- `agent.message`
- `agent.session_started`
- `agent.subagent_started`
- `agent.subagent_stopped`
- `agent.text_delta`
- `agent.tool_call`
- `agent.tool_result`
- `agent.usage`
- `edge.skipped`
- `edge.traversed`
- `interaction.answered`
- `interaction.closed`
- `interaction.requested`
- `log.warning`
- `loop.exhausted`
- `loop.iteration`
- `node.cancelled`
- `node.completed`
- `node.failed`
- `node.queued`
- `node.resumed`
- `node.skipped`
- `node.started`
- `node.waiting`
- `run.cancelled`
- `run.child_finished`
- `run.child_started`
- `run.completed`
- `run.created`
- `run.failed`
- `run.interrupted`
- `run.paused`
- `run.reply`
- `run.resumed`
- `run.started`
- `run.waiting`
- `usage.rate_limit`
