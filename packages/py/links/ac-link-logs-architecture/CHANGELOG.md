# 변경 기록

## 0.1.1 (미발행)

- 5.7R.8(M-4, X32): 포트 `architecture.profile_checks` 제공(`UnlistedPathCheck`) — 프로필 조건이 목록
  본문에 없는 경로를 보면 warning `architecture.condition_path_unlisted`. 접두는 설치자 옵션
  `unlisted_paths`(기본 `DEFAULT_UNLISTED_PATHS` = `/detail`·`/raw`).

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `link`).
- 5.5R.10: `GET /logs/architecture`·`GET /logs/events/{uid}/architecture`, X28 필터 `arch`·`arch_group`·`arch_sources`, 범위 캐시(증분 읽기·판정 재사용·결과 캐시), 출처 종류 대응 옵션, 웹 역할 `logs:architecture`, 단독 실행·테스트 도구.
