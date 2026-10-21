# 변경 기록: @agent-console/trace-view

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [미출시]
- 호출 span(`call`/`invoked_by`) 별도 세션 배지·과제 미리보기, 회차 ` #n`·호출 ` · 호출 n` 이름, 자식 Run 묶음 행(접기·펴기 제어형 `expandedGroupIds`/`onGroupToggle`, `onOpenChildRun`, `groupBadgeFor`), 링크 칩 `linkBadgeFor`. `flattenRows` 옵션 `runId`·`expandedGroups`, `spanOrdinals`·`defaultExpandedGroups`·`isCallSpan`·`isChildRunSpan` 공개. 새 필드가 없는 trace는 이전과 같다.

## [0.1.0]
- 처음 만듦.
