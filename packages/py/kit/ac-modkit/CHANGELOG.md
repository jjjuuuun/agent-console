# 변경 기록

## 미출시

- 5.5R.10: 조립 순서. 선택 포트 순환을 끊을 때 "순환 구성원 사이 선택 간선 모두 빼기" 대신 "필수 간선 전부 + 순환을 만들지 않는 선택 간선만(단일 포트 먼저, 여러 제공자 포트 나중)"으로 정렬한다. 큰 선택 순환(강연결 요소)에 묶여도 설정 제공자 → 소비자 순서를 잃지 않는다.
- 5.2R.93(설정 호환 정리): 옛 키를 읽어 옮기는 장치 `MovedSetting`·`SettingsMove`·`migrate_settings`와 `SettingsCompat.moved`·`SeedSetting.before_moves`를 지웠다(4R.18부터 선언 0개, 정책은 "옛 키는 읽지 않고 `RemovedSetting`으로 거부"). 기본값 채우기는 새 함수 `seed_settings(data, compats)`가 한다. 예제 `ECHO_SETTINGS_COMPAT`에서 옮기기 선언을 뺐다. 0.1.0 미출시 범위 안의 변경이라 버전은 그대로다.
- 5.2R.29: 모듈 옵션 읽기 전용 보기. 코어 `read_module_options`·`ModuleOptions`·`mask_values`·`OPTIONS_MASK`·`SECRET_SCHEMA_KEY`·`SecretPathFinder`, `Assembly.module_options(id)`(`Assembly.descriptors`·`Assembly.options` 필드 추가). 호스트 `GET /modules/{id}/options`(`build_module_options_router`·`default_module_options_payload`, `create_host_app(options_payload=)`)와 YAML 조각 `options_yaml_snippet`(가린 줄은 주석 `MASKED_LINE_NOTE`, 비게 된 객체·목록은 `{}`·`[]`). 가림 문자열은 `OPTIONS_MASK` 하나(`host.REDACTED`가 같은 값), `mask=` 인자로 호스트가 맞춘다. 쓰기 없음.
- 4R.18: `RemovedSetting`에 `new`(새 위치)·`reason` 기본값·`message()`를 더했다. 읽기 호환이 끝난 옛 키를 새 위치 안내 오류로 바꿀 때 쓴다.

## 0.1.0

- 3R.13: `Assembly.routers(first_kinds=)`, 호스트 `include_routers(app, assembly, prefix=, first_kinds=ROUTE_FIRST_KINDS)` — 연동 모듈 라우터를 먼저 붙여 고정 하위 경로(예: `/runs/handoffs`)가 기능 모듈의 매개변수 경로(`/runs/{run_id}`)에 가리지 않게 한다. `create_host_app`이 이것을 쓴다.

- 3R.12: HTTP 도우미 `host.IfMatchHeader`·`if_match_version`·`etag`·`json_with_etag`·`attachment_response`(버전 있는 자원·본문 파일 응답, 모듈 공통).

- 3R.11: `DatabaseHandle`(프로토콜)·`MigrationBranch`, `ModuleDescriptor.migrations`, `assemble`이 켜진 모듈의 계보만 build 직전에 `database.upgrade`(실패 시 그 모듈만 `failed`), `standalone.run(database=)`.

- 처음 만듦(scripts/pkgkit 템플릿 `kit`, 3R.8).
- 코어: `PortKey(multi=)`·`Topic`·`ModuleDescriptor`·`ModuleParts`·`Module`·`ModuleContext`·`assemble`
  (위상 정렬·상태 5종·bindings·multi 목록)·`EventBus`(구독자 예외 격리)·`Hub`·`BaseServices`·
  `load_installed_modules`.
- extra `[host]`: 보안 미들웨어·토큰·`/health`·WS 다중화·로그 가림을 `apps/server`에서 옮겨 왔다
  (동작 불변), `create_host_app`·`HostSettings`.
- `standalone.run(module, argv)`: `--with`·`--config`·`--host`·`--port 0`·`--check`.
- `testing`: `fake_module`, 예제 `EchoModule`.
- 3R.9: `ModuleDescriptor.contracts`·`ModuleReport.contracts`를 `{계약 하위 모듈: 버전}` 매핑으로 바꿈,
  `ModuleReport.to_dict()`, `ModulesConfig.with_overrides(enable=, disable=)`(명령행 켜고 끄기),
  `Assembly.start(fail_fast=)`, `FeatureUnavailableError`·`FEATURE_UNAVAILABLE`·`ModuleContext.unavailable(key)`.
  호스트: `GET /modules`(`build_modules_router`·`default_modules_payload`, `create_host_app(modules_payload=)`),
  `install_feature_unavailable`(409 `{module, port}`), `DEFAULT_ERROR_STATUS`에 `feature_unavailable`. 예제
  `EchoModule`에 `GET /echo/transformed`(선택 포트 없으면 409). 코어가 fastapi·uvicorn·websockets·ruamel·
  starlette 없이 import·조립되는지 확인하는 import 차단 테스트.
- 3R.10: `ErrorReply`·`ErrorMapper`·`ErrorMapping`·`error_reply` — `ModuleParts.error_map` 값으로 코드 문자열 대신
  예외 → `ErrorReply`(코드·메시지·`details`·헤더) 함수를 받는다(`install_error_map`이 처리). `standalone.run(default_with=,
  error_status=)`: `--with`가 없을 때 붙일 모듈, 오류 코드 → HTTP 상태 표.
