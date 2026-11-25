# 가져오기·내보내기

정의(에이전트·팀 구성·리소스 …)를 바깥 형식으로 내보내고, 바깥 폴더에서 정의 후보를 가져온다. 기본 구현은 Claude
Code의 프로젝트 설정 폴더 형식(내보내기 `claude-dir`, 가져오기 `claude`)이고, 다른 형식도 같은 그룹에 등록하는 구현이다.
두 지점은 서로 독립이다. 내보내기만, 가져오기만 만들어도 된다. 한 형식을 왕복시키려면 둘을 한 패키지에 두고 같은 옵션을
쓴다([예제](../../examples/extensions/agent-console-example-transfer/README.md)).

공통으로 지킬 것:

- **원본은 읽기 전용이다.** 가져오기 출처는 바깥 폴더를 읽기만 한다. 사용자의 실제 도구 설정 폴더도 마찬가지다.
- **쓰기는 서비스가 한다.** 내보내기 형식은 파일 내용을 돌려줄 뿐 쓰지 않는다. 서비스가 사용자가 고른 허용 폴더에만
  쓰고, 경로를 검사한다(폴더 밖·보호 위치로 나가는 경로는 거부).
- **비밀은 옮기지 않는다.** 비밀 참조(`secret://이름`)는 참조로 둔다. 평문으로 의심되는 값은 내보내기 서비스의 마지막
  검사가 가리고(`export.secret_redacted`, 위치만), 가져오기도 가리고 `import.secret_suspected`(위치만)를 단다. 형식이
  따로 가릴 필요는 없지만, 형식이 값을 바꿔(인코딩·일부 잘라) 담으면 검사가 알아보지 못한다.
- 형식·출처 옵션은 설치자 설정이다. 내보내기는 `modules.options.mod-exports.options.<형식 id>`, 가져오기는
  `modules.options.mod-imports.options.<출처 공장 이름>`. 옵션이 틀리면 그 형식·출처만 빠지고 경고가 남는다.

## exporter

**언제 쓰나**: 정의를 다른 도구가 읽는 형식(다른 에이전트 CLI의 설정 폴더, 팀 공유용 묶음 파일, 문서)으로 내보내고
싶을 때.

**최소 모양**: entry point가 가리키는 것은 **공장** `(설치자 옵션) -> Exporter`다. `Exporter`는 `descriptor`
(`ExporterDescriptor` — `id`·`title`, 선택 `config_schema`(요청 옵션)·`kinds`(내보낼 수 있는 정의 종류))와
`plan(items, catalog, options) -> ExportOutput`이다. `ExportOutput`은 파일 목록(상대 경로 + 내용)과 경고다.

**규칙**

- `plan`은 **순수**하다. `catalog`로 정의를 읽기만 하고 파일·네트워크를 건드리지 않는다. 같은 입력이면 같은 출력이다.
  그래서 미리보기와 실제 쓰기가 같은 결과를 낸다.
- 본문은 `catalog`의 두 길로 읽는다. 여러 파일 본문은 `files(kind, id)`(경로 → 내용), 한 파일 본문(문서의 본문 필드가
  파일 하나를 가리키는 종류)은 `content(kind, id)`다. 어느 쪽인지는 종류가 정하므로 형식은 둘 다 읽어 있는 것을 담는다.
- 경로는 상대 경로만 낸다. `..`·절대 경로를 내면 서비스가 요청 전체를 거부한다.
- 함께 쓰는 정의(팀 구성이 참조하는 에이전트·리소스)를 담을지는 요청 옵션으로 받는다.
- 형식이 담을 수 없는 것(그 형식에 칸이 없는 설정)은 버리지 말고 경고로 알린다. 내보내기를 멈춰야 하면 오류 경고를
  내면 서비스가 요청을 거부한다.

**흔한 실수**: 형식 이름·파일 이름·필드 이름을 코드에 고정한다. 옵션 데이터(패키지 기본값 + 설치자 옵션)로 받으면 다른
팀이 같은 패키지를 자기 이름으로 쓸 수 있다.

**지운 뒤 남는 데이터**: 형식 목록에서 사라지고, 그 형식을 고른 요청은 404 `not_found`다. 이미 내보낸 파일은 남는다.
남은 설치자 옵션은 쓰이지 않을 뿐 오류가 아니다.

<!-- extdocs:facts exporter -->
- 등록: entry point 그룹 `agent_console.exporters`(상수 `agent_console_exports:EXPORTERS_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_exports:Exporter` — 내보내기 형식. `plan`은 **순수**하다: 카탈로그를 읽기만 하고 파일을 쓰지 않는다
  - `agent_console_exports:ExporterFactory` — 설치자 옵션(`modules.options.mod-exports.options.<형식>`) → 형식.
  - `agent_console_exports:ExportOutput` — 형식이 만든 산출물(파일 내용 + 경고). 쓰기는 `ExportService`가 한다.
- 기본 구현: `claude-dir (agent-console-exports)`
- 예제:
  - package: [examples/extensions/agent-console-example-transfer](../../examples/extensions/agent-console-example-transfer/README.md)
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->

## import-source

**언제 쓰나**: 다른 도구가 만든 설정(에이전트·지침·스킬·MCP 서버)을 이 콘솔의 정의로 가져오고 싶을 때. 다른 에이전트
CLI의 설정 폴더, 팀이 공유한 묶음 파일이 예다.

**최소 모양**: entry point가 가리키는 것은 **공장** `(ImportSourceContext) -> 출처 목록`이다. 맥락에는 사용자 홈·프로젝트
폴더·설치자 옵션·비밀 의심 규칙이 들어 있다. 출처 하나(`ImportSource`)는 `descriptor`(`ImportSourceDescriptor` — `id`·
`title`, 선택 `path`·`available`)와 `scan() -> ScanResult`다. 결과의 항목(`ImportItem`)은 화면용 후보와 저장할 정의
문서(+ 본문)다.

**규칙**

- `scan`은 원본을 읽기만 한다. 결과를 저장하지 않는다. 사용자가 고른 항목만 서비스가 정의로 저장한다.
- 폴더가 없거나 형식 표지가 다르면 예외 대신 `available = false` 또는 빈 결과로 알린다. 다른 출처는 그대로 보인다.
- 읽을 위치는 맥락(홈·프로젝트 폴더)과 옵션에서 정한다. 경로를 코드에 고정하지 않는다.
- 공장이 출처 여럿을 돌려줄 수 있다(사용자 폴더와 프로젝트 폴더를 각각 출처로).
- 가져온 정의는 이 콘솔의 보통 정의다. 출처 패키지와 묶이지 않는다.

**흔한 실수**: 읽을 수 없는 파일 하나 때문에 `scan` 전체가 실패한다. 그 항목만 경고로 빼고 나머지를 보인다.

**지운 뒤 남는 데이터**: 출처 목록에서 사라진다. 이미 가져온 정의는 남는다(출처와 무관한 보통 정의다). 원본 파일은
처음부터 건드리지 않았으므로 그대로다.

<!-- extdocs:facts import-source -->
- 등록: entry point 그룹 `agent_console.import_sources`(상수 `agent_console_imports:IMPORT_SOURCES_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_imports:ImportSource` — 가져오기 출처(예: 사용자 `~/.claude`). **원본을 읽기만 한다.**
  - `agent_console_imports:ImportSourceFactory` — 환경 값으로 출처들을 만든다(entry point `agent_console.import_sources`가 가리키는 것).
  - `agent_console_imports:ImportItem` — 가져올 수 있는 항목 하나: 화면용 후보 + 쓸 문서(+ 본문).
- 기본 구현: `claude (agent-console-imports)`
- 예제:
  - package: [examples/extensions/agent-console-example-transfer](../../examples/extensions/agent-console-example-transfer/README.md)
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->
