# 변경 기록: @agent-console/folder-picker

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [미출시] (5.7R.33l2, 선택 우선 배치)
- `FolderPicker`: 배치를 "선택 우선"으로 바꿨다. [폴더 선택…]이 첫 포커스인 주 버튼, 선택한 폴더 상자, 접힌 "경로를 직접 입력". 새 props `capabilities`·`onPickNative(initial, signal)`·`configDir`·`autoFocus`·`pickRef`·`defaultManualOpen`·`onSelectPhaseChange`·`waitingEscapeMs`·`cancelledNoticeMs`·`copy`.
- 선택 상태 `picked`·`cancelled`·`unavailable`·`busy`·`timeout`·`failed` + 대기(`waiting`). `unavailable`·`failed`는 찾아보기로 자동 전환, 대기 중 Esc는 선택 취소.
- 확인 상태 `manifest_found`·`manifest_invalid` 추가(`FolderCheckData.manifest` 선택 필드, 없으면 숨김). `ok_readonly`는 `configDir`가 있으면 `{dir}` 문구.
- 새 export: `SelectedFolder`·`FolderPickStatusLine`, 타입 `FolderCapabilitiesData`·`FolderPickFn`·`FolderPickOutcome`·`FolderPickStatus`·`FolderManifestInfo`·`FolderSelectPhase`. `useFolderCheck`에 `checkNow`·`adopt` 추가.
- **호환을 깨는 변경**(소비 앱 없음, 0.1.0은 어디에도 쓰이지 않았다): ① "찾아보기…" 버튼이 [폴더 선택…]으로 바뀌었고 입력 칸은 기본 접힘이다(`defaultManualOpen`으로 펼침). ② 입력 칸 라벨이 `folder.path.input_label`("폴더 경로")이고 `folder.path.label`은 선택 상자 제목이다. ③ `folder.path.help`에서 "찾아보세요"를 뺐다. ④ `inputRef`는 직접 입력이 펼쳐졌을 때만 연결된다. ⑤ `FolderPathInput`은 `label`·`showResult` props가 늘었다(기본값은 이전 동작).
- 사용하는 토큰 `--ac-pick-box-min-h`·`--ac-pick-btn-h`를 `@agent-console/ui` tokens.css에 추가했다.

## [0.1.0]
- 처음 만듦.
