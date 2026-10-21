# 변경 기록

## 미출시

- 5.2R.34: 응답 틀 변수 `$cwd`(요청 작업 폴더, 없으면 빈 문자열).
- 5R.10: `capabilities.host_tools = true`. 규칙 `host_tool_calls: [{tool, input, when?, append}]`(`FakeHostToolCall`·`FakeHostToolWhen`)로 플랫폼 도구를 부르고 `$host_N`·`$host_N_status`와 응답 끝에 결과를 붙인다.

## 0.1.0

- 독립 프로젝트로 정리(3R.3): 사내 의존을 이름 + 버전 범위로 선언, 패키지별 pytest·mypy·ruff 설정과 `dev` 의존 그룹, LICENSE·CHANGELOG 추가. 동작 변경 없음.
