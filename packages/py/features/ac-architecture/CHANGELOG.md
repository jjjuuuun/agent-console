# 변경 기록

## 0.1.1 (미발행)

- 5.7R.8(M-4): `unlisted_path_issues(profile, unlisted_paths)`, `profile_issues(..., unlisted_paths=())`·
  `check_profile_data(..., unlisted_paths=())` — 조건(칸·연결 `when`, `error_when`) 경로가 주어진 접두와
  같거나 그 아래면 warning `architecture.condition_path_unlisted`(`details.prefix`·`condition_path`).
  접두 이름은 패키지에 없고 호출자가 준다. 넘기지 않으면 지금과 같다.

- 5.7R.7(M-2): 기본 프로필 `platform-runs` 수집 범위에 `rules`를 되돌림(플랫폼 맥락 구성의 규칙 리소스가
  대응표로 첫 문서 `kind: rules`가 된다). 표본 `run_with_session_log`의 맥락 구성 이벤트에 `documents`를
  더함 — 골든 Rules가 `partial`·0회에서 `observed`·1회(묶음 `house-rules`)로 바뀜.
- 5.5R.10: `project_architecture(..., matches=)`(미리 판정한 결과로 투영 — 연동 모듈의 결과 캐시·증분
  읽기용), `selector_predicate(..., matcher=)`(판정 결과를 기억하는 판정기 주입). 넘기지 않으면 지금과 같다.
- 5.5R.8: 기본 프로필 데이터 `agent-architecture`(칸 16·연결 21·영역 3, 수집 범위·출처 우선순위),
  `testing.load_sample`·`SAMPLES`·`Sample`(수집 결과 표본 2개: Claude Code 세션, 플랫폼 기록 + 세션 로그).

## 0.1.0

- 처음 만듦(5.5R.4): 프로필 문서·병합(`merge_profiles`, origin·덮어쓰기·null 지우기), 검사(`profile_issues`·
  `check_profile_data`), 투영(`project_architecture`: 지표 5개·상태 3개·수집 범위·묶기·하위 구조도·분류 안 됨·
  출처 우선순위·`max_seq`), 판정(`ProfileMatcher`·`event_membership`·`selector_predicate`), X23 로더,
  `testing` 도구. 기본 프로필 데이터는 자리만(5.5R.8).
