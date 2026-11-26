# 변경 기록: @agent-console/schema-form

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [Unreleased]
- 문구 데이터(0.2.0, I.9a): 기본 문구를 `src/locales/ko.json`으로 옮기고(`DEFAULT_MESSAGES`는 ko 그대로) `en.json`을 더했다. 하위 경로 내보내기 `./locales/ko`·`./locales/en`. 새 선택 prop `translate?: (text: string) => string`(스키마 제목·설명·`x-ui` when·그룹 제목·단위·선택지 이름, uiSchema `ui:title` 등에 적용, 기본은 그대로)과 `translateSchema`·`translateUiSchema`·`TranslateText` 공개. 키·자리표시자 같음 검사와 소스 한글 문자열 0 검사 테스트 추가. 공개 API는 늘기만 했고 기본 동작은 같다.
- `x-ui` 렌더(필수 칩·설명·예시·기본값·단위·고급 접힘), `xui`·`advancedStorageKey`·`compactProvenance` prop, 메시지 키 추가.
- `hideRootTitle` prop: 최상위 객체 제목을 숨긴다(바깥 패널이 머리말을 가질 때). 기본 false.

## [0.1.0]
- 처음 만듦.
