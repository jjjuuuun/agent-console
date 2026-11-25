# 변경 기록: @agent-console/text-editor

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [Unreleased]
- 비교 보기 접힌 구간: `@codemirror/merge` 6.13이 `role=button`만 달고 tabindex를 주지 않아 탭 정지가 사라지던 문제 수정(role과 tabindex를 따로 확인).
- `TextDiffMessagesProvider`(`@agent-console/text-editor/messages`)와 `TextDiffMessages.before`·`after` 추가: 앱 루트에서 비교 보기 기본 문구를 한 번에 주입한다.
- `TextEditorHandle.insertAtCursor(text)` 추가(7R.19, 위키 [링크 넣기]): 선택 범위를 글로 바꾸고 커서를 그 뒤로 옮긴다. 읽기 전용이면 false.

## [0.1.0]
- 처음 만듦.
