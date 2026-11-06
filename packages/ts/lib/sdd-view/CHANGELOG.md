# 변경 기록: @agent-console/sdd-view

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [미출시]
- 7R.6: `DocumentEditor`·`ToneChip`·`DocumentStateChip`·`RulesSourceBadge`와 `toneAttr`·`statusTone`·`formatMessage`·`messageOr`를 `@agent-console/markdown-doc`로 옮기고 같은 이름으로 다시 내보낸다(공개 API 그대로). `editor.*`·`source.*` 문구 키는 markdown-doc의 `defaultMessages`로 갔고 `messages` prop 덮어쓰기는 그대로 통한다. 칩·편집기 CSS는 markdown-doc `styles.css`(클래스 `ac-sdd-chip*`·`ac-sdd-editor*`·`ac-sdd-source` → `ac-md-*`)이고 `styles.css`가 @import한다. 의존에서 text-editor·react-markdown·remark-gfm을 빼고 markdown-doc를 더했다.
- `TaskTable`: 행 선택(`selectable`), 단계 접힘 덮어쓰기와 기본(모두 끝난 단계는 접힘), 행 아래 인라인 안내 `renderRowNotice`, 행 메뉴 `rowMenuItems`, 손잡이 `TaskTableHandle`. 기존 props는 그대로다(선택·접힘 저장은 호출자 몫).

## [0.1.0]
- 처음 만듦.
