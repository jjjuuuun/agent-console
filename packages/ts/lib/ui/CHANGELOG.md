# 변경 기록: @agent-console/ui

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [Unreleased]
- 0.2.1 (11/27, BC.2): 아이콘 `plug`(연결, 오른쪽 아래 모서리를 비움)를 더했다. `CommandItem`에 선택 필드 `keywords`(검색에만 쓰는 별칭)를 더하고 `filterCommandGroups`가 이를 함께 본다. `ToastInput.text`·`action.label`이 `ReactNode`를 받는다(글자도 그대로 된다. 언어를 따라 다시 그려지는 요소를 주면 떠 있는 알림 문구가 언어 전환 때 바뀐다). `FileTree`에 선택 prop `locale`(이름 정렬 언어, 기본 `en`)과 `buildRows`의 4번째 인자. 기존 동작은 같다.
- 측정 기반 접기(I.10, screen-i18n §5.0): `PageHeader`가 컨테이너 폭이 640px 이상이어도 보조 액션 때문에 제목이 120px보다 좁아지면 `more` 메뉴로 접는다(`data-collapsed`, `ResizeObserver`). 문구가 긴 언어(영어)용. 공개 API 변화 없음.
- 문구 데이터(0.2.0, I.9a): 컴포넌트 기본 문구(`더 보기`·`N개 더 보기`·단축키 중복 경고·공급자 밖 오류)를 `src/locales/ko.json`으로 옮기고(`defaultUiMessages`는 ko 그대로) `en.json`을 더했다. 하위 경로 내보내기 `./locales/ko`·`./locales/en`, `ChipRow`·`Tabs`·`PageHeader`·`ShortcutProvider`에 선택 prop `messages`, `UiMessages`·`defaultUiMessages`·`formatUiMessage` 공개. 키·자리표시자 같음 검사와 소스 한글 문자열 0 검사 테스트 추가. 기본 동작은 같다.
- 0.1.1 (11/26, P1.8): `.ac-pageheader-status`를 flex + `--ac-space-2` gap으로 바꿔 상태 칸의 Tag와 글자가 맞닿지 않게 했다.
- 5.2R.98: 공개 API `getResolvedTokens`를 삭제했다(xterm 테마용, 웹 터미널 삭제 뒤 쓰는 곳이 없었다). 쓰이지 않던 토큰 18개 삭제: `--ac-lh-lg`·`--ac-chevron`·`--ac-edge-route-pad`·`--ac-edge-selected-width`·`--ac-radius-xl`·`--ac-topbar-h`·`--ac-issues-h`·`--ac-dock-h`·`--ac-z-dock`·`--ac-z-canvas`·`--ac-log-row-h-compact`·`--ac-log-detail-w`·`--ac-lane-label-w`·`--ac-dash-row-h`·`--ac-dash-gap`·`--ac-trace-label-w`·`--ac-space-0`·`--ac-card-pad`. `.ac-toasts`는 도크 높이 없이 `bottom: var(--ac-space-4)`.
- 5.2R.13 (UX-P1): `Dialog` 3행 그리드(제목/스크롤 본문/하단 고정 `actions`), `size` sm|md|lg|xl(`wide`는 lg 별칭, 사용 중단), 본문 `fieldset` 초기화, `.ac-choice`. `Tabs` 넘침 "더 보기 ▾"(`moreLabel`), `TabItem.title`. 신규 `ChipRow`(+N 팝오버), `ActionButton`·`ActionDef`, `Tooltip`(CSS 400ms), `Popover`·`Menu`, `PageHeader` `secondaryActions`(컨테이너 쿼리 640px) · `moreLabel`, `computeVisible`·`useOverflowFit`. 아이콘 21개 추가(refresh close more plus undo check trash send stop panel-left-close/open filter columns table chevron-right/left/down expand play pencil pin). 토큰 `--ac-chip-max-w`·`--ac-tab-min/max-w`·`--ac-dialog-w-*`·`--ac-dialog-max-h`·`--ac-header-title-max`·`--ac-tip-delay`. 새 외부 의존 없음.
- 5R.16: 독립 위임·반복·조건·중첩 팀 토큰(tokens.md 5.10) 추가: `--ac-edge-loop`·`--ac-edge-failure`·`--ac-loop-region(-offset)`·`--ac-edge-pattern-0..3`·`--ac-edge-chip-max-w`·`--ac-stack-offset`·`--ac-run-badge-h`·`--ac-run-badge-picked`·`--ac-run-list-row-h`·`--ac-progress-indent`. 새 hex 없음(별칭).
- 5R.21: `useModalBackdrop`·`trapTabKey`·`FOCUSABLE_SELECTOR` 공개(앱 Drawer 중복 제거). 포커스 복귀 때 트리거가 사라졌으면 포커스를 두지 않는다.
- 5.2R.16 (UX-P3): 신규 `MiddleEllipsis`·`middleEllipsis`(id·해시 가운데 말줄임 앞 8·뒤 4 + 전체 툴팁 + 선택 복사 버튼, `.ac-middle-ellipsis`). 새 외부 의존 없음.

## [0.1.0]
- 처음 만듦.
