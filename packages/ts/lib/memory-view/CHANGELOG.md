# 변경 기록: @agent-console/memory-view

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [미출시]
- Messages (0.2.0, I.9c): moved the default messages to `src/locales/ko.json` (`defaultMessages` is still the Korean table) and added `en.json`. New subpath exports `./locales/ko` and `./locales/en` (`messages={en}`), plus `flattenMessageTree` and the `MessageTree` type. Added tests for matching keys and placeholders and for no Korean string literals in the source. The public API only grew and the default behavior is the same.

## [0.1.0]
- 처음 만듦: 범위 나무·항목 표(가상 목록, 서버 정렬)·편집기(조합 중 저장 보류)·정보·버전 목록/비교·정리 미리보기·정렬 메뉴, 순수 함수 groupScopes·scopeLabel·visibleScopes·formatAuthor (5.7R.17).
