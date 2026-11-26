# 변경 기록: @agent-console/folder-picker

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [미출시] (5.7R.33l2, 선택 우선 배치)
- Fix: the primary button (`.ac-fp-btn[data-variant="primary"]`) showed the light neutral hover background under white text on hover (contrast 1.12:1). It now has its own hover rule using `--ac-accent-hover`, so text contrast stays at least 4.5:1 in light and dark themes.
- 문구 데이터(0.2.0, I.9a): 기본 문구를 `src/locales/ko.json`으로 옮기고(`defaultMessages`는 ko 그대로) `en.json`을 더했다. 하위 경로 내보내기 `./locales/ko`·`./locales/en`(`messages={en}`으로 영어). 키·자리표시자 같음 검사와 소스 한글 문자열 0 검사 테스트 추가. 공개 API는 늘기만 했고 기본 동작은 같다.
- `FolderPicker`: 배치를 "선택 우선"으로 바꿨다. [폴더 선택…]이 첫 포커스인 주 버튼, 선택한 폴더 상자, 접힌 "경로를 직접 입력". 새 props `capabilities`·`onPickNative(initial, signal)`·`configDir`·`autoFocus`·`pickRef`·`defaultManualOpen`·`onSelectPhaseChange`·`waitingEscapeMs`·`cancelledNoticeMs`·`copy`.
- 선택 상태 `picked`·`cancelled`·`unavailable`·`busy`·`timeout`·`failed` + 대기(`waiting`). `unavailable`·`failed`는 찾아보기로 자동 전환, 대기 중 Esc는 선택 취소.
- 확인 상태 `manifest_found`·`manifest_invalid` 추가(`FolderCheckData.manifest` 선택 필드, 없으면 숨김). `ok_readonly`는 `configDir`가 있으면 `{dir}` 문구.
- 새 export: `SelectedFolder`·`FolderPickStatusLine`, 타입 `FolderCapabilitiesData`·`FolderPickFn`·`FolderPickOutcome`·`FolderPickStatus`·`FolderManifestInfo`·`FolderSelectPhase`. `useFolderCheck`에 `checkNow`·`adopt` 추가.
- **호환을 깨는 변경**(소비 앱 없음, 0.1.0은 어디에도 쓰이지 않았다): ① "찾아보기…" 버튼이 [폴더 선택…]으로 바뀌었고 입력 칸은 기본 접힘이다(`defaultManualOpen`으로 펼침). ② 입력 칸 라벨이 `folder.path.input_label`("폴더 경로")이고 `folder.path.label`은 선택 상자 제목이다. ③ `folder.path.help`에서 "찾아보세요"를 뺐다. ④ `inputRef`는 직접 입력이 펼쳐졌을 때만 연결된다. ⑤ `FolderPathInput`은 `label`·`showResult` props가 늘었다(기본값은 이전 동작).
- 사용하는 토큰 `--ac-pick-box-min-h`·`--ac-pick-btn-h`를 `@agent-console/ui` tokens.css에 추가했다.

## [0.1.0]
- 처음 만듦.
