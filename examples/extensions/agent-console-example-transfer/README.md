# agent-console-example-transfer

정의를 **JSON 파일 하나**로 내보내고, 같은 파일에서 다시 가져오는 예제이자 작성 가이드(확장 지점
"내보내기 형식"과 "가져오기 출처" 한 쌍). 엔진·서버·웹 코드를 고치지 않는다. 설치하면 내보내기 형식 목록과
가져오기 출처 목록에 `example-json`이 생기고, 제거하면 사라진다.

형식 `example-json`
- **내보내기**: 고른 정의(+ 함께 쓰는 정의 — 팀 구성의 에이전트·리소스 등)를 파일 하나(`agent-console-bundle.json`)에
  담는다. 정의 원문은 그대로, 본문 파일은 글이면 `text`, 바이너리면 `base64`로 담는다. 정의 종류를 가리지 않는다.
- **가져오기**: 프로젝트(작업) 폴더의 같은 이름 파일을 읽어 후보로 보인다. 원본 파일은 읽기만 한다.
- **형식 이름·필드 이름·파일 이름은 옵션 데이터**다(기본값 `data/defaults.json`). 설치자 설정으로 바꾼다.
- **비밀 값은 파일에 들어가지 않는다**: 비밀 참조(`secret://이름`)는 참조로 담기고, 평문으로 의심되는 값은 내보내기
  서비스의 마지막 검사가 가린다(경고 `export.secret_redacted`, 위치만). 가져올 때도 평문 의심 값은 가리고
  `import.secret_suspected`(위치만)를 단다.
- 의존: 계약(`agent-console-contracts`)·내보내기 라이브러리(`agent-console-exports`)·가져오기 라이브러리
  (`agent-console-imports`)·`agent-console-secret-rules`·`pydantic`. 서버 모듈은 import하지 않는다.

이 패키지는 uv workspace 멤버가 아니다. 설치하지 않으면 아무 동작도 바꾸지 않는다.

## 형식·출처 만드는 법

내보내기 형식은 `agent_console_exports.Exporter`(`descriptor`, 순수 `plan(items, catalog, options) -> ExportOutput`)를,
가져오기 출처는 `agent_console_imports.ImportSource`(`descriptor`, 읽기만 하는 `scan() -> ScanResult`)를 지킨다.
등록하는 쪽은 **공장**이다: 내보내기 = `(설치자 옵션) -> 형식`, 가져오기 = `(ImportSourceContext) -> 출처 목록`.

서버 없이 두 라이브러리만으로 한 바퀴(메모리 카탈로그 → 파일 → 메모리 저장소):

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_contracts import (
...     ExportSelection, ExportWriteRequest, ImportRequest, ImportSelection,
... )
>>> from agent_console_exports import ExportRoot, ExportService, FolderWriter
>>> from agent_console_exports.testing import MemoryCatalog
>>> from agent_console_imports import ImportService, ImportSourceContext
>>> from agent_console_imports.testing import MemoryDefinitionWriter
>>> from agent_console_example_transfer import (
...     FORMAT_ID, json_bundle_exporter, json_bundle_sources,
... )

>>> tmp = tempfile.TemporaryDirectory()
>>> out = Path(tmp.name)  # 설치자가 허용한 내보내기 루트
>>> catalog = MemoryCatalog().add("agent", {"id": "writer", "name": "작성자", "system_prompt": "짧게 쓴다."})
>>> exports = ExportService(
...     {FORMAT_ID: json_bundle_exporter({})}, catalog, writer=FolderWriter([ExportRoot("out", out)])
... )
>>> written = exports.write(ExportWriteRequest(
...     exporter=FORMAT_ID, items=[ExportSelection(kind="agent", id="writer")], root="out", subdir="proj",
... ))
>>> [(f.path, f.action) for f in written.files]
[('agent-console-bundle.json', 'create')]

>>> (source,) = json_bundle_sources(ImportSourceContext(project_dir=out / "proj"))
>>> store = MemoryDefinitionWriter()  # 실제로는 정의 저장소
>>> imports = ImportService([source], store)
>>> [(c.kind, c.suggested_id, c.name) for c in imports.preview(FORMAT_ID).candidates]
[('agent', 'writer', '작성자')]
>>> result = imports.apply(ImportRequest(source=FORMAT_ID, items=[ImportSelection(candidate_id="agent:writer")]))
>>> [(i.target_id, i.action) for i in result.items]
[('writer', 'created')]
>>> store.documents[("agent", "writer")]["system_prompt"]
'짧게 쓴다.'
>>> tmp.cleanup()

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

규칙
1. **`plan`은 순수하다**: 카탈로그를 읽기만 하고 파일 내용을 만들어 돌려줄 뿐이다. 쓰기(보관 파일·허용 폴더)는
   `ExportService`가 한다 — 경로 탈출·링크·보호 위치 거부와 충돌 처리가 형식마다 다시 구현되지 않는다.
2. **비밀은 형식이 따로 다루지 않아도 된다**: 서비스가 모든 형식의 산출물을 마지막에 검사해 평문 의심 값을 가린다.
   형식은 비밀 참조를 값으로 풀지 않는다.
3. **출처는 원본을 읽기만 한다**: 파일은 링크를 따라가지 않고(`O_NOFOLLOW`), 출처 폴더 밖으로 풀리는 경로는 읽지
   않는다(`import.skipped_link`). 없는 파일은 빈 결과다.
4. **틀린 파일·항목은 경고로**: 예외 대신 경고(`example_transfer.*`, 위치만)를 남기고 맞는 항목만 후보로 낸다.
5. **형식 id = entry point 이름 = 디스크립터 id**: 다르면 내보내기 로더가 경고 후 건너뛴다.

## 등록

`pyproject.toml`의 entry point 두 표. 이름 = 형식 id. 값은 공장 함수.

```toml
[project.entry-points."agent_console.exporters"]
"example-json" = "agent_console_example_transfer:json_bundle_exporter"

[project.entry-points."agent_console.import_sources"]
"example-json" = "agent_console_example_transfer:json_bundle_sources"
```

서버 시작 때 내보내기·가져오기 서버 모듈의 호스트 플러그인 로더가 이 그룹을 읽는다. 가져오기 출처는 프로젝트(작업)
폴더가 정해진 요청에서만 만들어진다(`ImportSourceContext.project_dir`). 홈 폴더 같은 다른 곳은 읽지 않는다.

## 설정 예

형식 설정은 기본값(`data/defaults.json`)에 설치자 옵션을 덮어쓴다. **내보내기와 가져오기 옵션이 같아야** 왕복된다.

```yaml
modules:
  options:
    mod-exports:
      options:
        example-json:
          file_name: team-bundle.json
          format_name: my-team-bundle
          fields: {items: things}     # 필드 이름은 하나씩 덮어쓴다
          drop_fields: [project]      # 내보낼 때 뺄 최상위 필드
    mod-imports:
      options:
        example-json:
          file_name: team-bundle.json
          format_name: my-team-bundle
          fields: {items: things}
```

| 옵션 | 기본 | 뜻 |
| --- | --- | --- |
| `file_name` | `agent-console-bundle.json` | 내보낼 파일 이름 = 가져올 때 프로젝트 폴더에서 찾을 파일(상대 경로, `..` 금지) |
| `format_name`·`format_version` | `agent-console-example-bundle`·`1` | 파일의 형식 표지(다르면 가져오지 않음, `example_transfer.unknown_format`) |
| `fields` | `format`·`version`·`definitions`·`kind`·`id`·`document`·`files`·`text`·`base64` | 파일 안 필드 이름(같은 층에서 겹치면 거부) |
| `name_field`·`type_field` | `name`·`type` | 가져오기 미리보기의 이름·리소스 종류로 쓸 정의 필드 |
| `drop_fields` | 없음 | 내보낼 때 정의에서 뺄 최상위 필드 |
| `max_file_bytes` | 10MiB | 가져올 때 읽을 최대 크기 |
| 요청 옵션 `include_dependencies` | `true` | 함께 쓰는 정의도 담기(내보내기 요청마다, 화면 폼은 `config_schema`) |

설치자 옵션이 틀리면(모르는 키·절대 경로·겹치는 필드 이름) 로더가 경고를 남기고 이 형식·출처만 빠진다.
위치는 내보내기 모듈 `modules.options.mod-exports.options.<형식 id>`, 가져오기 모듈 `modules.options.mod-imports.options.<출처 공장 이름>`이다.

## 설치·제거

저장소 루트에서 실행한다. WSL(`/mnt/c`)에서는 환경변수를 붙인다.

```bash
export UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=$HOME/.cache/agent-console-wsl-venv   # WSL만
uv pip install --python "$UV_PROJECT_ENVIRONMENT" -e examples/extensions/agent-console-example-transfer   # 설치
uv pip uninstall --python "$UV_PROJECT_ENVIRONMENT" agent-console-example-transfer                        # 제거
```

entry point는 서버 시작 때 읽으므로 설치·제거 뒤 **서버를 재시작**한다.
- 설치: 내보내기 형식 목록과 가져오기 출처 목록에 `example-json`이 보인다.
- 제거: 목록에서 사라진다. 이미 내보낸 파일과 가져온 정의는 그대로 남는다(가져온 정의는 이 패키지와 무관한 보통 정의다).
  남은 설치자 옵션은 쓰이지 않을 뿐 오류가 아니다.
- 설치한 채 로드하지 않기: 서버 설정 `plugins.enabled`(허용 목록)에서 `example-json`을 뺀다.

주의: `uv sync`는 lock에 없는 패키지를 지운다. 예제를 설치한 채 동기화하려면 `uv sync --all-packages --inexact`.

## 테스트

설치 없이 실행한다(pytest 설정 `pythonpath = ["src"]`). 루트 `uv run poe check`의 `examples` 단계가 이 폴더 설정으로
mypy·pytest를 돌린다(`uv run poe examples`). 저장소 밖에서는 이 폴더만 복사해 `uv sync --find-links <wheelhouse>`
(저장소에서 `uv run poe wheels`) 뒤 `uv run pytest`.

```bash
cd examples/extensions/agent-console-example-transfer
uv run --project ../../.. python -m pytest
```

- `tests/test_round_trip.py`: 실제 정의 저장소(파일 workspace)에 에이전트·리소스(글·바이너리 본문)를 두고 → 허용 폴더에
  내보내기 → **빈 workspace로 가져오기 → 같은 정의·같은 본문**, 다시 가져오면 새 이름(원본 파일 그대로), 비밀 참조는
  그대로·평문 값은 파일에도 가져온 정의에도 없음.
- `tests/test_agent_console_example_transfer.py`: entry point 선언, 라이브러리 로더로 로드, 틀린 옵션은 그 형식만 빠짐,
  필드·형식 이름 옵션, 글·바이너리 본문, 틀린 파일·항목 경고, 없는 의존 경고, 링크·폴더 밖 거부, 크기 상한.
