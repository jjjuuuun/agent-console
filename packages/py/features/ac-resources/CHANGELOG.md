# 변경 기록

## 미출시

- 안전 치환 구현을 기반 패키지 `ac-text-template`로 옮김(6R.4). `render_template`·`fill_value`·`DEFAULT_MAX_RENDER_CHARS`는 같은 이름으로 다시 내보낸다(공개 API·동작 불변).

## 0.1.0

- 독립 프로젝트로 정리(3R.3): 사내 의존을 이름 + 버전 범위로 선언, 패키지별 pytest·mypy·ruff 설정과 `dev` 의존 그룹, LICENSE·CHANGELOG 추가. 동작 변경 없음.
