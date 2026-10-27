# 변경 기록

## 미출시

- 5.2R.104: 프리셋 기능 삭제로 `serve --apply-preset`이 없어졌다(옵션을 선언하던 모듈 `mod-presets`가 없음). 도움말·테스트에서 뺐다.
- 5.2R.92: `serve`는 인자를 서버 `agent_console_server.main`에 그대로 넘긴다(옵션 정의는 서버 한 곳). 모듈이 `SettingsCompat.flags`로 선언한 옵션이 `agent-console serve`에도 나온다(전에는 `--apply-preset`만 하드코딩). 옵션·의미·종료 코드는 그대로다. 내부 함수 `_server.serve_overrides`·`run_server`·`merge_origins`(→ 서버 `merge_origins`)와 상수 `APPLY_PRESET_FLAG`를 지웠다. 설명을 "실행 명령"으로 고쳤다. 테스트 dev 의존에 `agent-console-modkit`(예제 모듈 선언용).
- 5.2R.27: `statusline`이 `--label`이 없으면 데이터의 짧은 창 이름(`5h`·`7d`, `agent_console_usage.default_window_labels`)을 쓴다.

## 0.1.0

- 독립 프로젝트로 정리(3R.3): 사내 의존을 이름 + 버전 범위로 선언, 패키지별 pytest·mypy·ruff 설정과 `dev` 의존 그룹, LICENSE·CHANGELOG 추가. 동작 변경 없음.
- `serve --enable-module ID --disable-module ID`(여러 번, 설정 `modules`보다 우선, 3R.9).
- 3R.10: `serve --apply-preset`가 `modules.options.mod-presets.apply_on_start`로 들어간다(옛 `presets.*` 대신).
