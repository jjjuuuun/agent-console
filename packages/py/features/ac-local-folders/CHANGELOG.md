# 변경 기록

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `feature`, 작업 5.7R.33d, design §PI.6·§PI.10).
- `normalize_lexical`·`normalize`·`check_folder`(`FolderCheck`, `status`)·`list_dirs`(`FolderListing`)·
  `make_folder`·`default_roots`·`nearest_existing`·`path_key`·`is_within`·
  `validate_folder_name`, 파일 시스템 주입 `FileSystem`(`LocalFileSystem`·`MemoryFileSystem`),
  규칙 데이터 `data/browse_defaults.json`(X34).
- 특정 실행 환경 전용 기능 제거(작업 5.7R.33d2): 다른 OS 경로 변환 제안(`suggest_native`·
  `TranslationRule`·`load_path_translations`·`FolderCheck.suggestion`·`data/path_translations.json`),
  이름으로 숨기던 Windows 시스템 폴더 기본 목록(`hidden_names` 기본은 빈 목록, 숨김 속성 판정은 그대로),
  드라이브 마운트 폴더를 시작 위치로 잡던 규칙. 다른 OS 경로는 `foreign_path`로만 알린다.
- 네이티브 폴더 선택 창(작업 5.7R.33d3, X35): 명령 표 데이터 `data/folder_dialogs.json`(Windows PowerShell
  `FolderBrowserDialog`·macOS `osascript`·`zenity`·`kdialog`), `load_dialog_specs`·`probe_dialogs`·
  `select_dialog`·`run_dialog`(`DialogSpec`·`DialogArg`·`DialogAvailability`·`DialogProbe`·`DialogResult`·
  `DialogStatus`·`DialogUnavailableReason`), 명령 실행기 주입 `CommandRunner`·`CommandOutcome`·
  `CancelSignal`, 실제 `SubprocessRunner`.
