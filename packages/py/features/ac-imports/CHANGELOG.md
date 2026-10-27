# 변경 기록

## 미출시

- 5.2R.94(잔해 정리): 쓰지 않는 직접 의존 `ruamel-yaml`을 뺐다(YAML은 `agent-console-claude-format`이 읽는다).
- 5.2R.31: 요청 `ImportRequest.project`(계약 0.8.0)를 쓴 정의의 범위 필드(`SCOPE_FIELD`)에 찍는다.
  `ImportService.apply(request, *, stamp=None)`, `request_stamp`. 생략 = 공용(기존과 같다).

## 0.1.0

- 독립 프로젝트로 정리(3R.3): 사내 의존을 이름 + 버전 범위로 선언, 패키지별 pytest·mypy·ruff 설정과 `dev` 의존 그룹, LICENSE·CHANGELOG 추가. 동작 변경 없음.
