# extdocs

확장 지점 선언을 코드와 대조하고(`poe extpoints-check`), 확장 가이드의 사실 부분을 생성하고(`poe extdocs`), 생성 문서가 낡지 않았는지 검사한다(`poe extdocs-check`). 저장소 도구이며 배포하지 않는다. 워크스페이스 venv(pydantic·ruamel.yaml)에서 돈다.

경로·대상은 인자와 데이터 파일로 받는다. 다른 저장소에 복사해 쓸 때는 `extdocs.yaml`만 고친다(`--root`·`--config`·`--tool-dir`).

## 명령

| poe 작업 | 직접 실행 | 하는 일 | `poe check` |
| --- | --- | --- | --- |
| `extpoints-check` | `python scripts/extdocs/extdocs.py points [--allow-missing [CAT ...]]` | 코드 ↔ 선언 대조(아래 "대조 항목"). 문서 없이 동작 | 포함(`--allow-missing`) |
| `extdocs` | `python scripts/extdocs/extdocs.py generate [--scaffold]` | `docs/extending/reference.md`, 문서 폴더 안 `extdocs:facts` 구간, `examples/extensions/README.md` 생성. `--scaffold`는 선언의 `guide`가 가리키는 절이 없으면 빈 틀(`extdocs:todo`)을 만든다 | — |
| `extdocs-check` | `python scripts/extdocs/extdocs.py docs [--allow-missing [CAT ...]]` | 재생성 diff 0, 가이드 절 손글·생성 구간, `extdocs:todo` 없음, 상대 링크·앵커, 공개 가능 린트, `>>>` doctest, `extdocs:validate` 조각 검증. 문서 폴더가 없으면 "문서 폴더 없음 — 건너뜀"으로 0 종료 | 포함(`--allow-missing guides`) |
| — | `python scripts/extdocs/extdocs.py docs --report [GLOB ...]` | 공개 가능 린트만 경고로(기본 `report_globs` — 패키지·앱 README). 늘 0 종료 | — |
| — | `python scripts/extdocs/extdocs.py schema [--check]` | `declaration.schema.json`을 모델에서 다시 쓴다(`points`가 드리프트를 잡는다) | — |
| `extdocs-test` | `pytest -q -c scripts/extdocs/pytest.ini scripts/extdocs` | 도구 자체 mypy(strict)·테스트(임시 저장소) | 포함 |

공통 옵션: `--root`(기본 현재 폴더), `--config`, `--tool-dir`, `--quiet`(경고는 규칙별 건수만). 종료 코드 0 통과, 1 위반, 2 설정·입력 오류.

## 선언 형식

모델은 `extdocs_model.py`(Pydantic)이고 공용 JSON Schema `declaration.schema.json`은 그 모델에서 만든다(TS 쪽 검사도 이 파일을 쓴다).

Python 패키지 `pyproject.toml`:

```toml
[tool.agent-console]
# 확장 지점이 아닌 포트·그룹(대조에서 뺀다, 사유 필수)
internal-ports = [{ port = "wiki.service", reason = "위키 모듈과 연동 모듈 사이 전용" }]
internal-groups = [{ group = "agent_console.config_schemas", reason = "..." }]

[tool.agent-console.extension-points.wiki-search-index]
title = "위키 검색 색인"
area = "wiki"                     # areas.yaml의 id
design_id = "X48"                 # 선택, 문서에 나가지 않는다
summary = "위키 검색을 다른 색인 구현으로 바꾼다"
registration = { kind = "entry-point", group = "agent_console_wiki:SEARCH_INDEX_GROUP" }
interface = ["agent_console_wiki:WikiSearchIndex"]
settings = ["wiki.search_backend"]
builtin = "entry-points"          # 선택: entry-points(기본, entry-point 종류) · providers(기본, port 종류) · none
example = { kind = "package", path = "examples/extensions/agent-console-example-wiki-search" }
guide = "wiki.md#wiki-search-index"   # 문서 폴더 기준, 절을 생략하면 slug
```

- slug(표 키): 소문자·숫자·하이픈. 저장소 전체에서 하나.
- `registration.kind`는 열린 문자열이다. 아는 값: `entry-point`(`group`), `port`(`port`, `multi`), `data`(`path`·`settings`·`disable`), `injection`, `annotation`·`descriptor`·`registry`(`name`), `props`(`export`). 모르는 값은 원문 그대로 표에 나오고 `templates/registration.yaml`의 `_default` 문장을 쓴다. 문장 틀 하나를 더하면 전용 문장이 된다.
- `group`·`port`는 기호(`모듈:이름`)가 원칙이다. 기호가 아닌 문자열이면 그대로 그룹·포트 이름으로 본다.
- `example`은 표 하나 또는 목록. 종류: `package`(설치형 예제 폴더 `path`), `reference`(저장소 안 참조 구현 `path`), `contract-tests`(`symbols` — 계약 테스트 묶음·대역 기호), `snippet`(가이드 절 안의 `>>>` 또는 `extdocs:validate` 조각).
- `interface`·`settings`는 문자열 하나 또는 목록.

TS 패키지·앱 `package.json`(같은 모델, 키는 `extensionPoints`):

```json
{
  "agentConsole": {
    "kind": "lib",
    "extensionPoints": {
      "dashboard-widget": {
        "title": "대시보드 위젯", "area": "web", "summary": "...",
        "registration": { "kind": "props", "export": "@agent-console/log-view#DashboardWidgets" },
        "interface": ["@agent-console/log-view#DashboardWidget"],
        "example": { "kind": "package", "path": "examples/web/agent-console-example-web" },
        "guide": "web.md#dashboard-widget"
      }
    }
  }
}
```

예제 패키지는 자기가 보이는 지점을 적는다: Python `[tool.agent-console.example] points = ["wiki-search-index"]`, TS `"agentConsole": {"example": {"points": [...]}}`. 지점 선언의 `example`(kind `package`)과 서로 맞아야 한다.

## 대조 항목(`points`)

1. 그룹: 워크스페이스 멤버 `src`의 그룹 상수(이름 `*_GROUP`, 값 `agent_console.*` — 패턴은 `extdocs.yaml` `code`) + 멤버 pyproject entry point 그룹 = 선언 `registration.group` + `internal-groups`
2. 포트: 멤버 서버 모듈 entry point의 `descriptor`(build하지 않음)의 provides·requires·optional = 선언 `registration.port` + `internal-ports`. 상한 `descriptor_time_limit_seconds`(10초)
3. 선언의 Python 기호가 import된다. TS 기호(`@pkg#이름`)는 `pnpm extdocs-check`가 본다
4. 예제 경로가 있다, 예제 `points` ↔ 선언 `example` 짝, 지점마다 예제 하나 이상
5. 선언된 지점을 보이는 예제의 README에 필수 절(`readme_sections.yaml`, 제목에 별칭이 들어 있으면 인정)
6. slug 중복 없음, `area`가 `areas.yaml`에 있음, 선언 형식(스키마)
7. `declaration.schema.json`이 모델과 같다

대상은 루트 `[tool.uv.workspace] members` 중 `[tool.uv.sources]`에서 `workspace = true`로 이은 배포뿐이다. 설치해 둔 예제·바깥 플러그인은 섞이지 않는다(결정성).

## 단계적 적용(`--allow-missing`)

"아직 채우지 않음"만 범주로 나눠 경고로 낮춘다. 형식 오류·기호 import 실패·짝 불일치·README 절 빠짐·생성 낡음·링크·공개 가능 린트·조각 검증은 늘 오류다.

| 범주 | 경고가 되는 것 |
| --- | --- |
| `declarations` | 선언 없는 그룹·포트(`group-undeclared`·`port-undeclared`), 예제가 가리키는데 선언 없는 지점(`example-point-undeclared`) |
| `examples` | 예제가 없는 지점(`example-missing`), snippet 예제인데 절에 검증 조각이 없음(`snippet-missing`) |
| `guides` | 가이드 파일·절·생성 구간 없음, 손글 없음, `extdocs:todo` 남음 |

`--allow-missing`만 주면 세 범주 전부다. `poe check`는 지금 `extpoints-check`에 전부, `extdocs-check`에 `guides`를 준다. 선언 채우기가 끝나면 `extpoints-check`의 옵션을 떼고, 영역 가이드가 다 쓰이면 `extdocs-check`의 옵션을 뗀다.

## 문서 조각

- `>>>`가 든 코드 펜스는 파일마다 같은 이름 공간으로 doctest한다(ELLIPSIS·NORMALIZE_WHITESPACE).
- 데이터 조각은 펜스 정보 문자열로 모델을 지정한다: ` ```yaml extdocs:validate=agent_console_contracts.wiki:WikiRulesDefinition `. yaml·json·toml을 읽어 그 Pydantic 모델로 검증하고, 모르는 키를 보존하는 모델이면 남은 키(`model_extra`)도 실패로 본다.

## 데이터 파일

| 파일 | 내용 |
| --- | --- |
| `extdocs.yaml` | 경로·대상 glob·코드 패턴·계약 표 기호·시간 상한 |
| `areas.yaml` | 영역(id·제목·파일) — 새 영역은 한 줄 |
| `readme_sections.yaml` | 예제 README 필수 절과 별칭 |
| `public_lint.yaml` | 공개 가능 린트 규칙(정규식) |
| `templates/registration.yaml` | 등록 종류별 "등록"·"끄기·제거" 문장 |
| `templates/text.yaml` | 생성 파일 제목·머리말·표 머리·`extdocs:todo` 틀 |

## TS 쪽(`pnpm extdocs-check`)과의 경계

Python 쪽은 TS `package.json` 선언도 읽어 형식·slug·영역·예제 짝을 검사하고 문서를 생성한다(Node 없이 결정적). TS 쪽 도구는 다음을 맡는다.

- 읽을 곳: `extdocs.yaml`의 `ts_package_globs`, 표 이름 `ts_table`(`agentConsole`), 키 `extensionPoints`
- 형식: `declaration.schema.json`(최상위 = slug → 선언)
- 기호: `interface`와 `registration.export`의 `@pkg#이름`이 그 패키지 `src/index.ts`에서 export되는지(TypeScript 컴파일러 API)
- 출력: 사람이 읽는 줄 `오류 [code] where: message` + 선택 `--json`. Python 생성기는 이 JSON에 기대지 않는다

## 테스트

```sh
uv run poe extdocs-test
```

임시 저장소(루트 pyproject + 멤버 패키지 + 예제 + 문서)를 만들어 규칙마다 실패·통과를 본다. 저장소 실제 서버 모듈 서술자 대조 시간도 확인한다.
