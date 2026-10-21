# 변경 기록: @agent-console/projects

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [0.1.0]
- 처음 만듦(5.2R.35): 보기 규칙·기본 범위·범위 배지·로그 필터·현재 프로젝트 저장소·옮기기 계획 도우미·REST 클라이언트. 의존은 contracts 타입뿐.
- 5.2R.3 후속: `SCOPE_ISSUE_CODES`·`MOVE_TO_SHARED_SUGGESTION_ID`의 값을 손 복사 대신 계약 생성 상수(`@agent-console/contracts/constants`의 `KNOWN_ISSUE_CODES`·`KNOWN_SUGGESTION_IDS`)에서 가져온다. contracts 값 import는 이 상수 진입점만 허용한다(dependency-cruiser `projects-contracts-types-only`).
