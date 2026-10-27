# @agent-console/web

Agent Console 웹 앱(Vite + React 19, PWA). **패키지를 조립만 하는 얇은 층**이다: 표현 컴포넌트·스키마 폼은 `packages/ts/lib/*`의 것을 쓰고,
이 앱은 (1) 부팅(서버 주소·토큰), (2) 데이터 연결 훅(TanStack Query), (3) 라우팅·셸, (4) 한글 문구만 가진다.
노드 타입·연결 종류·리소스 종류·상호작용 종류·사용량 창·모델·로그 출처·로그 범주·위젯 종류·차원·지표 이름과 서버 모듈 id는 코드에 없다(서버 디스크립터/설정 데이터, `src/app/moduleIdsNoHardcoding.test.ts`가 모듈 id를 점검한다).
로그 화면(`src/features/logs`, 4R.17)의 필터·열 이름은 데이터 파일 `logsData.json`, 기간·시간 상수·저장소 키는 `logsConfig.ts` 한 곳에 있다.
`src/app/noHardcoding.test.ts`가 소스를 훑어 점검한다. 서버(API+WS)와 웹은 **별도 프로세스**다. 서버는 웹을 모른다.

## 실행
```bash
pnpm app                                              # 루트: 서버 + 웹 미리보기를 함께 (1R.15)
uv run agent-console serve                            # 서버만 (기본 127.0.0.1:8765)
pnpm --filter @agent-console/web dev                  # 웹 개발 서버(Vite, HMR)
pnpm --filter @agent-console/web build                # tsc + vite build -> apps/web/dist (PWA 포함)
pnpm --filter @agent-console/web preview              # 빌드본 로컬 서빙 (서비스 워커·설치 확인은 이쪽에서)
```
`dev`/`preview` 스크립트 이름과 `build`는 루트 `pnpm app`이 쓰므로 바꾸지 않는다.

### 서버 주소 (코드에 포트 없음)
부팅 때 `GET /config.json`(웹 정적 파일, 배포 후 고칠 수 있음)의 `apiBaseUrl` → 빌드 변수 `VITE_AGENT_CONSOLE_API_URL` → 없으면 **같은 출처** 순으로 정한다.
파일이 없거나 `apiBaseUrl`이 비어도 오류가 아니다.
- 같은 출처: `dev`/`preview`가 `/api`, `/ws`를 서버로 프록시한다. 대상은 `AGENT_CONSOLE_SERVER_URL`(우선) 또는 `AGENT_CONSOLE_HOST`/`AGENT_CONSOLE_PORT`(기본 127.0.0.1 / 8765).
- 직접 호출: `config.json`에 `{ "apiBaseUrl": "http://127.0.0.1:8765" }`. 서버는 웹 출처를 허용해야 한다(`serve --allow-origin …` 또는 `security.allowed_origins`). 연결 실패가 CORS로 추정되면 화면이 그 안내를 보여 준다.

### PWA
`vite-plugin-pwa`가 manifest + 서비스 워커를 만든다(빌드·미리보기에서만 등록). **서비스 워커는 정적 파일만 캐시한다**: `/api`, `/ws`, `config.json`은 캐시·오프라인 대체에서 제외.
새 버전은 자동 새로고침하지 않고 토스트 "새 버전이 있습니다 [지금 새로고침]"로 알린다(저장 안 된 변경이 있으면 확인). 설치 안내는 사이드바 버튼(브라우저가 이벤트를 줄 때)과 설정 → 앱 설치.

## 구조 (`src/`)
| 폴더 | 역할 |
| --- | --- |
| `app/` | 부팅(`config`, `boot`, `AppRoot`), API·질의 컨텍스트(`ApiContext`, `queries`), 한글 문구(`messages`), 안내 배너(`hints`), 저장소(`storage`) |
| `definition/` | 정의 편집 공통: `useDefinitionEditor`(초안·If-Match 저장·412 충돌), `ConflictBanner`, `SaveStatus`, `UnsavedGuard`(이탈 보호) — 팀 구성·에이전트·리소스 화면도 쓴다 |
| `shell/` | 앱 셸: 라우트 설정 데이터(`routeConfig`), 페이지 표(`routes.tsx`), 사이드바, 빠른 이동, 도움말, 단축키, 응답 대기 구독, Esc 스택 |
| `pwa/` | 설치 안내 상태(`installPrompt`), 업데이트 알림 어댑터(`registerSw`는 `main.tsx`만 import) |
| `features/settings/` | 설정 화면과 섹션, `UserSettingsForm`(팀 구성 화면도 재사용), `LayerForm`(출처 표시 폼 래퍼) |
| `lib/` | 순수 함수(JSON Pointer, 스키마 도구, 단축키 검증, 층 편집, 포맷) |
| `testing/` | 테스트 전용 가짜 클라이언트(앱 코드에서 import 금지) |

새 화면 추가: ① `shell/routeConfig.ts`의 `DEFAULT_ROUTES`에 항목 한 줄(사이드바·`g` 단축키·빠른 이동·문서 제목이 자동. 다른 화면이 링크할 때 찾는 `serves` 역할도 적는다 — 기능 코드는 라우트 id가 아니라 `routePath(ROUTE_ROLES.*)`로 찾는다), ② `shell/routes.tsx`의 `DEFAULT_PAGES`에 `routeId → 하위 라우트`.
단축키 기본 표는 셸이 가지며 설정 `ui.keybindings`가 덮어쓴다(개발 모드에서만 중복 키 경고).

## 의존성 (무엇을 / 왜 / 대안)
| 의존 | 왜 | 대안 |
| --- | --- | --- |
| `react-router` ^7 | 라우팅·이탈 보호(`useBlocker`)·메모리 라우터 테스트 | TanStack Router |
| `@tanstack/react-query` ^5 | 화면 간 서버 상태 캐시·무효화·창 포커스 복귀 갱신(결정 §R13-11) | 직접 만든 `useAsync`(1R.22 전 방식) |
| `vite-plugin-pwa` ^2 + `workbox-window` (dev) | manifest·서비스 워커(워크박스) 생성, 설치 가능한 앱 | 수작업 manifest + 서비스 워커 |
| 워크스페이스 패키지 | contracts, api-client, ui, schema-form, graph-editor(1R.23 대비) | — |

터미널 도크·콘솔·Phase 1 그래프/편집기/실행 화면은 제거했다(`@agent-console/terminal` 패키지도 삭제했다).

## 테스트
`npx vitest run apps/web --maxWorkers=1` (루트). 가짜 클라이언트로 부팅 실패·인증 거부·셸·단축키 덮어쓰기·빠른 이동·응답 대기 배지·설정 저장/충돌/사용량 출처/서버 정보를 검사한다.
E2E(Playwright)는 1R.26에서 다시 쓴다(`apps/web/e2e`의 기존 시나리오는 Phase 1 화면 기준이라 지금은 맞지 않는다).
