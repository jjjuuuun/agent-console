# 변경 기록: @agent-console/markdown-doc

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [0.1.0]
- 처음 만듦(7R.6). `sdd-view`에서 `DocumentEditor`(비교·줄 이동·외부 변경 띠 포함)·`ToneChip`·`DocumentStateChip`·`RulesSourceBadge`를 옮겼다. 이슈 타입은 계약 `Issue`를 바탕으로 한 `DocumentIssue`(`line` 선택)라 `SpecIssue`도 들어간다. 새로 `MarkdownPreview`(`renderLink`·`transformSource`·`urlTransform` 훅)와 `DocumentEditor.previewHooks`.
