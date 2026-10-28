# 변경 기록: @agent-console/log-view

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [Unreleased]
- 5.7R.32: 화면을 단순하게 하는 모양 옵션(기능은 그대로, 기본 모양이 바뀐다).
  `LogFilterBar`: `savedPlacement`(`menu` 기본 = 즐겨찾는 필터가 [+ 필터] 메뉴 맨 아래 구역, `button` = 예전 [★ ▾] 단추). 메시지 `saveCurrentFilter` 추가.
  `PlaybackBar`: `settingsPlacement`(`popover` 기본 = 속도·공백 건너뛰기가 [재생 설정 ▾] 팝오버 안, 1×가 아니면 단추 옆에 "2×", `inline` = 예전 모양). 메시지 `playSettings`·`playSettingsShort` 추가.
  `CategoryChips`: 접힌 동안에도 선택된 칩은 보이고, 접힌 단추에 숨은 개수 `(+n)`을 적는다.
- 5R.21: 앱이 DOM을 읽지 않게 하는 추가 API(모두 선택, 기존 사용처는 그대로 동작).
  `LogEventTable`: `ref`(`LogEventTableHandle`: `scrollToUid`·`focus`), `onActivate(uid)`(Enter).
  `LogEventDetail`: `activeTab`·`onActiveTabChange`(제어형), `ref`(`LogEventDetailHandle`: `selectTabAt`·`focusTab`·`visibleTabs`).
  `SessionList`: `onActiveChange(id|null)`(키보드 커서 행).
- dependency-cruiser `log-view-contracts-types-only`: contracts는 `import type`만 허용.

## [0.1.0]
- 처음 만듦(작업 4R.16). 이벤트 표(가상 스크롤)·필터 막대·범주 칩·이벤트 상세·세션 목록·재생 막대·레인 띠·handoff 행렬·
  대시보드 격자·위젯 편집기·템플릿 선택·색 슬롯 선택, 위젯 레지스트리(`builtinWidgets`: metric·bar·line·table),
  recharts 지연 로드 차트 어댑터, 재생 훅 `usePlayback`, 순수 함수(정렬·자르기·묶기·URL 파라미터 분리·배치·보존).
- 사내 의존은 `@agent-console/contracts` 타입만. 새 외부 의존: `@tanstack/react-virtual`, `recharts`, `react-is`.
