# 변경 기록

## 0.1.1 (미발행)

- 5.7R.8(X32): 선택 여러 제공자 포트 `architecture.profile_checks`(`ProfileCheck.check(profile,
  profile_id) -> list[Issue]`)를 받아 목록 `issues` 수·상세 `problems`·`POST
  /architecture/profiles/check` 결과에 더한다(부를 때 읽음, 예외를 낸 검사는 건너뜀).
  `ArchitectureCatalogService(..., checks=)`. 제공자가 없으면 지금과 같다.

## 0.1.0

- 5.5R.10: 사용자 설정 포트 `workspace.settings`를 build 때가 아니라 부를 때 찾는다(조립 순서와 무관하게 설정을 읽음).
- 처음 만듦(scripts/pkgkit 템플릿 `module`).
- 5.5R.9: 프로필 목록·상세·검사·단독 투영 REST, 포트 `architecture.catalog`, X23 호스트 플러그인 로더,
  설치자 옵션 `max_request_events`·`max_scope_events`, 단독 실행(`python -m`), 웹 역할 `architecture`.
