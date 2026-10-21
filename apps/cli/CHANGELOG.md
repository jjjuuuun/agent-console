# 변경 기록

## 미출시

- 5.2R.27: `statusline`이 `--label`이 없으면 데이터의 짧은 창 이름(`5h`·`7d`, `agent_console_usage.default_window_labels`)을 쓴다.

## 0.1.0

- 독립 프로젝트로 정리(3R.3): 사내 의존을 이름 + 버전 범위로 선언, 패키지별 pytest·mypy·ruff 설정과 `dev` 의존 그룹, LICENSE·CHANGELOG 추가. 동작 변경 없음.
- `serve --enable-module ID --disable-module ID`(여러 번, 설정 `modules`보다 우선, 3R.9).
- 3R.10: `serve --apply-preset`가 `modules.options.mod-presets.apply_on_start`로 들어간다(옛 `presets.*` 대신).
