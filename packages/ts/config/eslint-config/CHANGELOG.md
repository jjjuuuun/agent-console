# 변경 기록: @agent-console/eslint-config

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [Unreleased]
- `DEFAULT_IGNORES`에 `**/dist-*/**` 추가: 별도 outDir 빌드 산출물(`dist-*`)을 린트하지 않는다.
- 5.2R.13: `/react` 설정에 `agent-console/button-name` 규칙(error) 추가: 접근성 이름이 없는 `<button>`(아이콘만) 금지. 규칙은 `rules/button-name.js`.

## [0.1.0]
- 처음 만듦.
