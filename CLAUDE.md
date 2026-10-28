# Agent Console — 프로젝트 규칙

Claude Code로 이 저장소를 개발할 때 따르는 규칙이다. 사람 기여자에게도 같은 규칙이 적용된다.

## 무엇을 만드는가
에이전트 기반 개발 작업을 **사용자가 원하는 대로 구성할 수 있는** 로컬 웹 플랫폼.
사용법은 [USAGE.md](USAGE.md), 개발 방식은 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)에 있다.

## 참고한 내부 자료
실행 엔진과 로그 수집·분석은 이전에 만든 내부 벤치마크 도구의 아키텍처와 로그 처리 방식을 참고해 설계했다.
가져온 코드는 이 프로젝트의 패키지로 옮겨 재사용 원칙에 맞게 정리했고, hook·MCP 로직을 파악하는 데 필요한 요소
(hook 실행 이벤트, MCP 서버·도구 호출 추적, 요청·응답·소요 시간·에러 수집, 세션 로그와의 연결)를 더했다.

## 최우선 원칙: 아무것도 하드코딩하지 않는다
- 에이전트, 팀, 역할, 라우팅 분류, 그래프 노드 종류, 모델, 도구, 로그 소스, 위키 규칙은
  **전부 사용자가 만들고 고치고 지우는 데이터**다. 코드에 고정된 목록을 두지 않는다.
- 구체적인 예(PL·디자이너·백엔드 팀 등)는 예시일 뿐이다. 서버는 빈 workspace로 시작하고, 사용자가 화면에서 직접 만들거나
  기존 `.claude/` 설정을 가져와서 쓴다. 미리 깔린 정의 없이도 모든 기능이 동작해야 한다.
- 새 종류(노드 타입, 로그 소스, 실행 백엔드)는 코드 수정 없이 또는 플러그인 하나 추가로 확장 가능해야 한다.
  확장 지점은 설계 문서와 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)에 적는다.
- 판단 기준: "사용자가 이걸 다르게 원하면 코드를 고쳐야 하나?" → 그렇다면 데이터나 확장 지점으로 뺀다.
- **기능은 따로 쓸 수 있어야 한다.** 채팅·실행·사용량·관측·설정·리소스·가져오기/내보내기 같은 백엔드 기능은 각각
  서버·웹·다른 기능 없이 단독으로 쓸 수 있어야 한다. 웹은 이 기능들을 한 화면에 합칠 뿐이다.
  기능끼리의 연동은 주입 인터페이스로 하는 선택 사항이며, 연동 대상이 없으면 그 부분만 꺼지고 나머지는 동작해야 한다.
  패키지 폴더 하나를 저장소 밖으로 가져가도 설치·테스트·실행이 되어야 한다(워크스페이스 전용 경로·루트 설정에 기대지 않는다).

## 개발 팀 (이 프로젝트를 만드는 팀)
[`.claude/agents/`](.claude/agents/)의 리더들이 역할을 나눠 개발한다. 이 팀 구성 역시 필요하면 바꿔도 된다.
- `pl`: 설계·작업 분해·통합 검토
- `web-designer-lead`, `publisher-lead`: 화면 설계와 구현
- `backend-lead`, `db-lead`: 서버·실행 엔진·데이터
- `qa-lead`: 검증

## 운영 방식
- 메인 세션이 오케스트레이터다. 서브에이전트끼리는 서로 호출할 수 없으므로,
  작업 목록(tasks.md)을 보고 담당 리더에게 위임하는 일은 메인 세션이 한다. 메인 세션은 직접 구현하지 않는다.
- 위임할 때 작업 번호, 관련 요구사항 ID, 참고할 설계 문서(design.md) 섹션을 함께 넘긴다.
- 요구사항·설계·작업 목록 문서는 개인 작업 폴더에 두며 공개 저장소에는 넣지 않는다.

## 작업 흐름 (SDD)
1. 단계 시작 → `pl`이 design.md와 그 단계의 tasks.md를 작성한다. **사람 승인 전에는 구현하지 않는다.**
2. 각 작업에는 `[owner: ...]`, `[req: ...]`, 필요하면 `[depends: ...]`를 붙인다.
3. 의존 없는 작업만 병렬로 위임한다.
4. 작업이 끝나면 `qa-lead`가 검증한다. 실패 시 담당자에게 되돌리고, 3회 연속 실패하면 멈추고 보고한다.
5. 통과하면 체크 표시. 코드가 스펙에 적힌 내용과 달라지면 스펙도 갱신한다.
6. 한 번에 한 단계만 진행하고, 끝나면 요약 보고 후 멈춘다.

## 기술 스택
| 영역 | 확정 |
| --- | --- |
| 서버·실행 엔진·CLI | Python 3.12+(최신 보안 패치 권장), uv 0.13.4+, uv workspace (`packages/py/{base,features,kit,modules,links}/*`, `apps/server`, `apps/cli`) |
| 웹 | TypeScript, React 19 + Vite(메타 프레임워크 없음), Node `^22.23.4 \|\| ^24.22.1 \|\| >=26.12.1`, pnpm 10.34.5+ workspace(`packageManager` 10.34.9) (`packages/ts/{config,lib}/*`, `apps/web`) |
| 서버·실시간 | FastAPI + uvicorn, WebSocket 단일 채널 (`/ws`) |
| 계약 | Pydantic v2(`agent_console_contracts`)가 단일 소스 → JSON Schema/OpenAPI → TS 타입 생성(`@agent-console/contracts`), 생성물 커밋 + 드리프트 검사 |
| 실행 엔진 | 자체 asyncio 경량 스케줄러(`GraphRuntime` 인터페이스 뒤) |
| 저장 | 정의 = workspace YAML(ruamel.yaml), 버전·실행·이벤트 = SQLite(SQLAlchemy 2 Core + Alembic) |
| 플러그인 | Python entry points + 명시 모듈 목록 + 선언형 데이터 |
| 에이전트 실행 | claude-agent-sdk(Python) + 테스트용 가짜 백엔드 |
| 웹 라이브러리 | @xyflow/react, @rjsf/core v6, TanStack Query, recharts(지연 로드), @tanstack/react-virtual, react-router v7, CodeMirror 6(text-editor), react-markdown(chat), elkjs(graph-editor 자동 배치) |
| CLI | Typer — `agent-console` 실행 명령(`serve`는 서버 `main`에 위임해 모듈이 선언한 옵션이 자동으로 보임, `statusline`은 서버를 import하지 않음) |
| 품질 | ruff, mypy, pytest(+pytest-asyncio), import-linter / ESLint, tsc, Vitest, Playwright, dependency-cruiser |
| 이름 | Python import `agent_console_*`, 배포 `agent-console-*`, TS `@agent-console/*` |

고정·환경 메모:
- 런타임 최소 버전: Node `^22.23.4 || ^24.22.1 || >=26.12.1`(CVE-2026-111497, 루트 `engines.node`), pnpm 10.34.5 이상(CVE-2026-82392, `packageManager` 10.34.9), uv 0.13.4 이상, Python 3.12 이상 + 최신 보안 패치(CVE-2026-115557). `engine-strict`는 켜지 않는다(범위 밖이면 경고만).
- TypeScript는 6.0.x로 고정한다. typescript-eslint 8.x가 TS 7을 지원하지 않기 때문이며, 지원되면 올린다.
- Vitest 워커 수는 기본 min(4, CPU-1)이고 `VITEST_MAX_WORKERS`로 바꾼다. 루트 `vitest.config.ts`가 계산값을 패키지·인라인 프로젝트에 같이 쓰게 하므로 패키지 config에는 maxWorkers를 두지 않는다. 부하가 큰 환경에서는 `--testTimeout=60000`을 준다.
- DOM 테스트는 happy-dom을 쓴다. 레이아웃 API가 필요한 테스트(React Flow)는 jsdom이나 브라우저 모드로 전환할 수 있다.
- 새 Python 패키지는 `uv run poe new-package`로 만든다(workspace members·루트 `[tool.uv.sources]`·import-linter 자동 갱신, 누락은 `poe pkg-lint`가 잡는다). import-linter 계약은 `importlinter.rules.toml`을 고치고 `poe importlinter-sync`로 반영한다.
- TS 패키지는 `exports`의 `development` 조건으로 소스를, `types`·`default`로 `dist`를 가리킨다(번들러 소비자 전제). 앱은 `resolve.conditions`에 `development`를 넣는다. 공용 tsconfig·ESLint 설정은 `@agent-console/tsconfig`·`@agent-console/eslint-config` 패키지다.
- 사내 TS 의존은 `^x.y.z` 범위 + pnpm `linkWorkspacePackages`로 연결한다. `workspace:` 프로토콜은 쓰지 않는다. 새 TS 패키지는 `pnpm new-package`로 만든다.
- 서버 기능 설정은 `modules.options.mod-*` 아래에 둔다(예: `mod-runs.backends`, `mod-logs.scan_interval_seconds`). 없어진 옛 최상위 키가 남아 있으면 서버가 시작을 거부하고 `settings.removed_key` 오류로 새 위치를 안내한다.
- 서버 앱은 기능 이름을 모른다. 기본 서비스(레지스트리·DB·플러그인 로더)는 entry point `agent_console.host_registries`·`host_plugin_loaders`·`host_database`로, 모듈이 선언한 명령행 옵션은 모듈 `settings_compat`으로 들어온다(선언한 모듈이 없는 옵션은 설정 오류). `/api/v1/health`는 모듈 시작 훅이 끝난 뒤에만 200(이전·종료 후 503 `not_ready`).
- 각 모듈은 자기 DB 계보(Alembic 버전 테이블)를 소유한다. 모듈을 끄면 그 계보를 올리지 않는다.

## 명령어
| 용도 | 명령 |
| --- | --- |
| 설치 | `uv sync --all-packages` · `pnpm install` |
| 서버 실행 | `uv run agent-console serve [--allow-origin ORIGIN] [--open\|--no-open] [--enable-module ID] [--disable-module ID]` (기본 127.0.0.1:8765, 모듈 상태는 `GET /api/v1/modules`) |
| 서버 하나로 웹까지 | 웹 빌드 후 `AGENT_CONSOLE_SERVE_STATIC=1 AGENT_CONSOLE_WEB_DIR=apps/web/dist uv run agent-console serve [--open]` (또는 설정 `web.serve_static`·`web.static_dir`·`web.open`) |
| 준비 신호 | `GET /api/v1/health` (200이면 준비) |
| 서버 + 웹 미리보기 | `pnpm app` (`--port`·`--web-port`·`--config`·`--build`, `--` 뒤는 serve 인자) |
| 사용량 상태 줄 브리지 | `uv run agent-console statusline --output <경로>` |
| 웹 개발 서버 / 빌드 / 미리보기 | `pnpm --filter @agent-console/web dev` / `build` / `preview` |
| Python 전체 검사 | `uv run poe check` (= ruff check·format --check, mypy, lint-imports, `pkg-lint` 패키지 이식성 정적 검사, `schema-help-lint` 설정 스키마 라벨·설명 검사, pytest, `examples` 확장 예제 검사) |
| Python 휠·이식성 | `uv run poe wheels` (→ `dist/wheelhouse`) · `uv run poe portability [--package NAME] [--wheels]` (저장소 밖 복사 설치·검사) |
| Python 새 패키지 | `uv run poe new-package --kind {base,feature,kit,module,link} NAME` (서버 모듈은 `--kind module ac-mod-<이름> --id mod-<이름>`, 연동 모듈은 `--kind link ac-link-<a>-<b> --id link-<a>-<b>`, 배치 `packages/py/{base,features,kit,modules,links}/`) |
| import-linter 목록 생성 | `uv run poe importlinter-sync` (`--check`) |
| TS 전체 검사 | `pnpm check` (= ESLint, `pkg-lint`, tsc, Vitest, dependency-cruiser). `pnpm check -- <vitest 인자>`는 test 단계에만 전달 |
| TS tarball·이식성 | `pnpm pack:all` (→ `dist/npm`) · `pnpm portability [--package NAME]` |
| TS 새 패키지 | `pnpm new-package --kind lib\|config NAME` |
| 계약 생성·드리프트 | `uv run poe contracts` (생성) · `uv run poe contracts-check` (재생성 후 diff 0) |

## 기존 라이브러리·프레임워크 우선
- 직접 만들기 전에 검증된 라이브러리·프레임워크가 있는지 먼저 찾는다.
  그래프 편집 UI, 워크플로/그래프 실행, 에이전트 오케스트레이션, 웹 터미널, 로그 파싱, 차트,
  마크다운 편집, ORM·마이그레이션 등은 기존 도구를 적극 활용한다.
- 기존 오픈소스 프로젝트를 기반으로 확장하는 것도 선택지로 검토한다.
- 채택 기준: 유지보수가 활발한가, 라이선스가 맞는가, 사용자 정의·확장성을 막지 않는가.
  특정 라이브러리에 깊게 묶이면 나중에 교체가 어려우므로, 핵심 도메인 코드와는 어댑터로 분리한다.
- 새 의존성을 추가할 때는 해당 모듈 README에 "무엇을 / 왜 / 대안"을 한 줄 남긴다.

## 코드 작성 원칙: 모든 코드는 재사용 가능해야 한다
작성하는 **모든 코드**는 처음부터 재사용 가능한 단위로 만든다. 이 프로젝트 안에서뿐 아니라,
떼어 내서 다른 프로젝트에 가져가도 그대로 쓸 수 있는 것을 기준으로 한다.

### 구조
- 기능은 **독립 패키지(라이브러리) 단위**로 만든다. 각 패키지는 자기 역할 하나만 하고,
  공개 API(export)와 내부 구현을 구분한다. 다른 패키지의 내부 구현을 직접 참조하지 않는다.
- 애플리케이션(웹, 서버, CLI)은 패키지들을 **조립만 하는 얇은 층**이다.
  비즈니스 로직은 앱 안에 두지 않고 패키지에 둔다.
- 도메인 로직은 UI·전송 계층(HTTP, WebSocket, CLI)·저장소와 분리한다.
  같은 로직을 웹에서도, CLI에서도, 테스트에서도, 다른 프로젝트에서도 호출할 수 있어야 한다.
- 외부 의존(파일 시스템, DB, 모델 API, SDK, 시간, 환경변수)은 인터페이스로 받아서 주입한다.
  코드 안에서 직접 생성하거나 전역에서 꺼내 쓰지 않는다.
- 같은 종류가 늘어나는 것(노드 타입, 어댑터, 분류기 등)은 공통 베이스와 등록 방식 위에 구현한다.
- UI 컴포넌트도 마찬가지다. 특정 화면·API에 묶이지 않게 데이터와 콜백을 props로 받고,
  표현용 컴포넌트와 데이터 연결 로직을 분리한다.

### 작성 규칙
- 프로젝트·경로·모델명·URL·포트 등 환경에 따라 달라지는 값은 코드에 고정하지 않고 인자나 설정으로 받는다.
- 전역 상태와 숨은 부작용을 만들지 않는다. 함수는 입력과 출력이 명확해야 한다.
- 공개 API에는 타입(Python은 타입 힌트, TS는 타입 정의)과 짧은 문서(용도, 인자, 반환, 예외)를 단다.
- 각 패키지에는 README(무엇을 하는지, 설치, 최소 사용 예)와 테스트를 둔다.
- 같은 로직을 복사해서 붙이지 않는다. 이미 있는 패키지를 쓰거나 확장한다.

### 균형
- 재사용 가능하다는 것은 **경계가 분명하고 의존이 주입되며 설정이 바깥에 있다**는 뜻이지,
  추상화 계층을 많이 쌓는다는 뜻이 아니다. 단순한 함수로 충분하면 단순한 함수로 쓴다.
- 쓰임새가 하나뿐인 기능도 위 구조 규칙은 지킨다. 다만 가상의 미래 요구를 위한 옵션·계층은 추가하지 않는다.

## 완료 조건
- 아래가 모두 통과해야 완료다(해당 언어 쪽만 바뀌었으면 그쪽만):
  - `uv run poe check` — ruff·mypy·import-linter·pytest
  - `pnpm check` — ESLint·tsc·Vitest·dependency-cruiser
  - 계약(`agent_console_contracts`)을 건드렸으면 `uv run poe contracts-check`
  - 단계 통합 검증에서는 브라우저 E2E와 `uv run poe portability --wheels`
- 새 기능에는 해당 요구사항의 수용 기준을 확인하는 테스트가 있어야 한다.
- "코드 작성 원칙: 모든 코드는 재사용 가능해야 한다"를 지켜야 완료다.
  새 패키지는 README와 독립 테스트가 있어야 하고, 앱 없이 단독으로 import해 쓸 수 있어야 한다.

## 안전 규칙
- `~/.claude/` 등 외부 도구의 원본 파일은 읽기 전용이다. 수정·삭제하지 않는다.
- 에이전트 설정을 내보낼 때는 사용자가 지정한 경로에만 쓴다.
- 비밀 값은 환경변수나 로컬 비밀 저장소에만 두고 커밋·로그·화면에 노출하지 않는다.
- 서버는 기본적으로 로컬(127.0.0.1)에만 바인딩한다. 외부 공개는 사용자가 명시적으로 켤 때만.
- 테스트 데이터(녹화 로그·세션 로그·픽스처)와 실행 데이터(workspace, `.state`, DB)는 커밋하지 않는다.
