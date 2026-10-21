# 변경 기록: @agent-console/ui

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [Unreleased]
- 5.2R.13 (UX-P1): `Dialog` 3행 그리드(제목/스크롤 본문/하단 고정 `actions`), `size` sm|md|lg|xl(`wide`는 lg 별칭, 사용 중단), 본문 `fieldset` 초기화, `.ac-choice`. `Tabs` 넘침 "더 보기 ▾"(`moreLabel`), `TabItem.title`. 신규 `ChipRow`(+N 팝오버), `ActionButton`·`ActionDef`, `Tooltip`(CSS 400ms), `Popover`·`Menu`, `PageHeader` `secondaryActions`(컨테이너 쿼리 640px) · `moreLabel`, `computeVisible`·`useOverflowFit`. 아이콘 21개 추가(refresh close more plus undo check trash send stop panel-left-close/open filter columns table chevron-right/left/down expand play pencil pin). 토큰 `--ac-chip-max-w`·`--ac-tab-min/max-w`·`--ac-dialog-w-*`·`--ac-dialog-max-h`·`--ac-header-title-max`·`--ac-tip-delay`. 새 외부 의존 없음.
- 5R.16: 독립 위임·반복·조건·중첩 팀 토큰(tokens.md 5.10) 추가: `--ac-edge-loop`·`--ac-edge-failure`·`--ac-loop-region(-offset)`·`--ac-edge-pattern-0..3`·`--ac-edge-chip-max-w`·`--ac-stack-offset`·`--ac-run-badge-h`·`--ac-run-badge-picked`·`--ac-run-list-row-h`·`--ac-progress-indent`. 새 hex 없음(별칭).
- 5R.21: `useModalBackdrop`·`trapTabKey`·`FOCUSABLE_SELECTOR` 공개(앱 Drawer 중복 제거). 포커스 복귀 때 트리거가 사라졌으면 포커스를 두지 않는다.
- 5.2R.16 (UX-P3): 신규 `MiddleEllipsis`·`middleEllipsis`(id·해시 가운데 말줄임 앞 8·뒤 4 + 전체 툴팁 + 선택 복사 버튼, `.ac-middle-ellipsis`). 새 외부 의존 없음.

## [0.1.0]
- 처음 만듦.
