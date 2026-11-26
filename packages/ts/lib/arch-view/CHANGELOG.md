# 변경 기록: @agent-console/arch-view

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [0.2.0]
- 문구 데이터(0.2.0, I.9b): 기본 문구를 `src/locales/ko.json`으로 옮기고(`defaultMessages`는 ko 그대로) `en.json`을 더했다. 하위 경로 내보내기 `./locales/ko`·`./locales/en`(`messages={en}`으로 영어). `checkLayout` 옵션 `errorsPlaceholder` 추가(기본은 기본 문구 `metricErrors`에 0을 채운 글자, 옛 하드코딩 "오류 0"과 같은 결과). `ArchitectureDiagram` 밖에서 `useDiagram`을 쓴 오류 문구를 영어로, `josa`의 "으로" 비교를 코드 점 표기로 바꿨다. 키·자리표시자 같음 검사와 소스 한글 문자열 0 검사 테스트 추가.

## [0.1.0]
- 처음 만듦.
