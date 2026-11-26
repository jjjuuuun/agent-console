# 변경 기록: @agent-console/markdown-doc

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [Unreleased]
- Messages (0.2.0, I.9c): moved the default messages to `src/locales/ko.json` (`defaultMessages` is still the Korean table) and added `en.json`. New subpath exports `./locales/ko` and `./locales/en` (`messages={en}`), plus `flattenMessageTree` and the `MessageTree` type (`wiki-view` and `sdd-view` reuse them). Added tests for matching keys and placeholders and for no Korean string literals in the source. The public API only grew and the default behavior is the same.
- `DocumentEditorHandle.insertAtCursor(text)` 추가(7R.19).
- `MarkdownPreview`: `renderLink`를 컨텍스트로 전하고 컴포넌트 표를 한 번만 만든다. 이전에는 부모가 다시 그려질 때마다 링크 요소가 지워졌다 다시 만들어져 포커스·호버를 잃었다.
- `styles.css`: `.ac-md-editor-status`에 `line-height`를 더했다(줄 높이 짝짓기 검사).

## [0.1.0]
- 처음 만듦(7R.6). `sdd-view`에서 `DocumentEditor`(비교·줄 이동·외부 변경 띠 포함)·`ToneChip`·`DocumentStateChip`·`RulesSourceBadge`를 옮겼다. 이슈 타입은 계약 `Issue`를 바탕으로 한 `DocumentIssue`(`line` 선택)라 `SpecIssue`도 들어간다. 새로 `MarkdownPreview`(`renderLink`·`transformSource`·`urlTransform` 훅)와 `DocumentEditor.previewHooks`.
