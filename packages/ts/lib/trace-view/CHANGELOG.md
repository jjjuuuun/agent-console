# 변경 기록: @agent-console/trace-view

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [미출시]
- 문구 데이터(0.2.0, I.9b): 기본 문구를 `src/locales/ko.json`으로 옮기고(`defaultTraceMessages`는 ko 그대로) `en.json`을 더했다. 하위 경로 내보내기 `./locales/ko`·`./locales/en`(`messages={en}`으로 영어). 키·자리표시자 같음 검사와 소스 한글 문자열 0 검사 테스트 추가. 공개 API는 늘기만 했고 기본 동작은 같다.
- 호출 span(`call`/`invoked_by`) 별도 세션 배지·과제 미리보기, 회차 ` #n`·호출 ` · 호출 n` 이름, 자식 Run 묶음 행(접기·펴기 제어형 `expandedGroupIds`/`onGroupToggle`, `onOpenChildRun`, `groupBadgeFor`), 링크 칩 `linkBadgeFor`. `flattenRows` 옵션 `runId`·`expandedGroups`, `spanOrdinals`·`defaultExpandedGroups`·`isCallSpan`·`isChildRunSpan` 공개. 새 필드가 없는 trace는 이전과 같다.

## [0.1.0]
- 처음 만듦.
