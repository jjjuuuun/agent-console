# pkgkit

패키지 이식성 도구 모음(design §3R.2). Python 도구(.py)는 backend-lead가 이 파일에 절을 더한다.

## TS 도구 (.mjs, 3R.4)

패키지 하나를 저장소 밖으로 복사해도 설치·빌드·테스트가 되도록 만들고 검사한다. Node ^22.23.4 || ^24.22.1 || >=26.12.1(CVE-2026-111497 패치 버전), 외부 의존 없음(순수 함수는 `lib/`, 입출력은 각 CLI).

| 파일 | 하는 일 |
| --- | --- |
| `pkg-lint.mjs` | `workspace:`·상대 `extends`·패키지 밖 경로/import·`exports` 규칙(development→src, default→dist)·스크립트·필수 파일·선언하지 않은 의존·다른 패키지 내부 직접 참조·README `ts readme` 블록 ↔ `test/readme.test.ts` 구간 일치 |
| `pack-all.mjs` | `pnpm -r --if-present build` 뒤 `pnpm -r pack --pack-destination dist/npm` |
| `portability.mjs` | 패키지를 임시 폴더로 복사 → 사내 의존을 `dist/npm` tarball(`file:` + `overrides`)로 바꿈 → `npm install` → build·typecheck·test → 결과 표 |
| `new-package.mjs` | 템플릿으로 새 패키지 생성. 루트 파일은 고치지 않는다 |
| `lib/*.mjs` | 순수 함수: `lint-rules`·`readme-sync`·`plans`·`scaffold`·`template`·`workspace` (`fsutil`만 파일을 읽는다) |
| `templates/ts/` | `common/` + `lib/` 또는 `config/` 층. 파일은 `.tmpl`, 자리표시자는 `{{키}}`, `package.patch.json`은 package.json에 합쳐진다 |

사용(저장소 루트에서; 루트 `package.json`에 `pnpm pkg-lint`·`pnpm pack:all`·`pnpm portability`·`pnpm new-package`로 등록돼 있다. `pkg-lint`는 `pnpm check`에 포함, `pack:all`은 `./packages/**`만 빌드·pack하고 루트·앱은 제외한다):

```sh
node scripts/pkgkit/pkg-lint.mjs [--package NAME] [--json]
node scripts/pkgkit/pack-all.mjs [--dry-run]
node scripts/pkgkit/portability.mjs [--package NAME] [--keep]     # 먼저 pack-all
node scripts/pkgkit/new-package.mjs --kind lib|config [--dom] [--scope @scope] NAME
```

`portability`는 복사본에서 단계를 돌릴 때 `AGENT_CONSOLE_SKIP_PERF=1`을 설정한다(`lib/plans.mjs`의 `PORTABILITY_ENV`). 시간 단언이 있는 테스트는 이 값이면 시간 비교만 건너뛰고 정확성 단언은 유지한다. 직접 돌릴 때도 같은 변수를 쓸 수 있다.

README 규칙: README의 ` ```ts readme ` 코드 블록은 `test/readme.test.ts`의 `// readme:start` ~ `// readme:end` 구간과 같아야 한다(공통 들여쓰기·줄 끝 공백 무시). 테스트가 패키지 이름으로 import할 수 있게 템플릿의 `vitest.config.ts`가 이름을 소스로 alias한다.

공통 옵션:
- `--prefix P`(반복 가능): 사내 패키지 이름 접두사. 기본은 루트 package.json 이름의 scope, 없으면 워크스페이스 패키지들의 scope, 그래도 없으면 `@agent-console/`. `--scope @acme`로 만든 패키지는 `--prefix @acme`(또는 기본 추정)로 검사한다.
- `--under PREFIX`: 패키지를 찾을 폴더 접두사(기본 `packages/ts/`). 폴더가 없으면 읽을 수 있는 오류로 끝난다(종료 코드 2).
- 종류(`lib`|`config`)는 package.json의 `"agentConsole": {"kind": "..."}` 표식으로 정한다(`new-package`가 쓴다). 표식이 없을 때만 경로에 `config` 단계가 있는지로 추정한다.

`dist`는 번들러 소비자 전제다(`moduleResolution: Bundler`, 확장자 없는 상대 import). Node가 `dist`를 직접 실행해야 하는 패키지가 생기면 그 패키지만 NodeNext로 바꾼다(에이전트 결정 E-20).

`pkg-lint` 규칙(rule id):
| id | 내용 |
| --- | --- |
| `required-file` | 종류별 필수 파일 누락 |
| `package-json` | JSON 오류, name·semver version·`private: true`·license·`type: module` |
| `workspace-protocol` | `workspace:`·`link:`·패키지 밖 `file:` 의존, overrides의 같은 문법 |
| `inhouse-range` | 사내 의존은 `^x.y.z`·`~x.y.z`·`>=a <b` 범위만 |
| `scripts` / `external-path` | 필수 스크립트(lib: build·typecheck·lint·test, config: lint·test), 스크립트·tsconfig의 패키지 밖 경로 |
| `tsconfig`, `tsconfig-extends` | tsconfig 파싱, 패키지 밖을 가리키는 상대 `extends` |
| `exports` | `main`/`types`가 src를 가리킴, development→src·default→dist·types→dist 규칙, `files`에 dist |
| `escaping-import` / `deep-import` | 패키지 밖 상대 import / 다른 사내 패키지의 `src`·`dist`·`test(s)` 직접 import |
| `undeclared-dep` | 소스가 import하지만 package.json에 없는 의존(`@types/*` 선언 인정) |
| `readme-sync` | README `ts readme` 블록 ↔ `test/readme.test.ts` 구간 불일치 |

테스트: `pnpm exec vitest run scripts/pkgkit`

## Python 도구 (.py, 3R.2)

표준 라이브러리만 쓴다(Python 3.12+, `tomllib`). 도구가 아는 값(접두사·경로·사내 의존 범위·규칙 켜고 끄기)은 전부 `pkgkit_py.toml`에 있고, 종류(kind) 목록은 `templates/python/kinds/` 폴더가 정한다. 모든 명령은 `--root`(기본 현재 폴더)·`--config`를 받는다. 오류는 종료 코드 2, 위반·실패는 1.

| 파일 | 하는 일 |
| --- | --- |
| `pkg_lint.py` | 정적 검사. 규칙: `layout`(종류 폴더 밖), `workspace-source`(패키지 `[tool.uv.sources]`), `outside-path`(pyproject 값의 패키지 밖 상대 경로), `root-lookup`(`Path(__file__).parents[N]`·`.parent` 사슬이 패키지 뿌리 위로), `foreign-tests-import`(다른 패키지 `tests/` 모듈·`*.tests` import), `required-files`(공통 + 종류별), `tool-config`(pytest·mypy·ruff 표와 dev 그룹 ↔ 템플릿), `internal-dep-range`(사내 의존 범위 누락), `readme-doctest`(README "최소 사용" 절 안에 doctest `>>>`가 0건이거나 절이 없으면 위반, 3R.6에서 켬, 4R.18부터 그 절만 센다. 절 제목은 `pkgkit_py.toml` `[pkg_lint] readme_doctest_heading`), 저장소 규칙 `template-root-drift`(템플릿 ↔ 루트 도구 설정), `root-source`(루트 `[tool.uv.sources]`가 사내 워크스페이스 프로젝트를 빠짐없이 `workspace = true`로 잇는지, 없는 패키지 항목), `importlinter-drift` |
| `importlinter_sync.py` | `importlinter.rules.toml`(그룹 `@all`·`@packages`·`@app`·`@<kind>`, 빼기 `!이름`·`!@그룹`, 사용자 `[groups]`) → 루트 `pyproject.toml`의 `[tool.importlinter]` 영역(표식 줄 사이). `--check`는 의미 차이만 보고, `--init`은 지금 계약을 규칙 파일로 옮긴다 |
| `wheels.py` | `uv build --all-packages --wheel -o dist/wheelhouse`(얇은 래퍼, `--clean`·`--package`·`--dry-run`) |
| `mypy_conftests.py` | `poe typecheck` 둘째 단계. 패키지 `tests/`에는 `__init__.py`가 없어 모든 `conftest.py`가 같은 모듈 이름이 되므로 루트 `[tool.mypy] exclude`가 집계 실행에서 빼고, 이 스크립트가 `[tool.mypy] files` 아래 `conftest.py`를 파일마다 루트 설정으로 검사한다(4R.22). 패키지 단독 mypy에는 영향 없음 |
| `portability.py` | 패키지 폴더를 `$TMPDIR`로 복사 → `uv venv` → `uv sync`(복사본에만 휠 모음 flat 인덱스를 덧붙여 사내 패키지는 휠 모음에서) → `ruff check`·`ruff format --check`·`mypy`·`pytest`(README doctest 포함) → `module`·`link` 종류면 `python -m <import> --check` → 결과 표. `UV_PROJECT_ENVIRONMENT`·`VIRTUAL_ENV`·`PYTHONPATH`·`MYPY_CACHE_DIR`는 넘기지 않는다(mypy 캐시는 임시 복사본 안에 생기고 세션과 함께 지워진다, 5.2R.94b). `--wheels`는 휠 모음을 다시 만들고 기본으로 세션 임시 `UV_CACHE_DIR`을 쓴다(같은 버전으로 다시 만든 사내 휠을 uv 캐시가 옛 내용으로 재사용하지 않게, `--reuse-uv-cache`로 끔, `--uv-cache-dir`로 위치 지정). `--wheels` 없이 돌릴 때 휠이 패키지 소스(`pyproject.toml`·`README.md`·`src/`)보다 오래되었으면 경고한다(4R.18) |
| `new_package.py` | `--kind {base,feature,kit,module,link} NAME`으로 `packages/py/<종류 폴더>/NAME` 생성, workspace `members`에 없으면 추가, 루트 `[tool.uv.sources]`에 `<배포 이름> = { workspace = true }` 추가, 규칙 파일이 있으면 import-linter 갱신 |
| `pkgkit_common.py`·`pkgkit_template.py` | 순수 함수: 설정·패키지 찾기·이름 규칙·TOML 쓰기 / 템플릿 렌더링. `with_range`는 범위 없는 사내 의존에 설정 범위를 붙이고 extra(예: `agent-console-modkit[host]`)는 유지한다 |
| `templates/python/` | `common.toml`(공통 필수 파일·dev 도구) + `common/**.tmpl` + `kinds/<kind>/kind.toml`(폴더·의존·필수 파일·단독 실행·entry point) + `kinds/<kind>/files/**.tmpl` |

루트 `pyproject.toml`의 poe 작업으로 등록돼 있다(3R.3): `uv run poe pkg-lint`(`poe check`에 포함) · `poe importlinter-sync` · `poe wheels` · `poe portability` · `poe new-package` · `poe pkgkit-test`. 인자는 poe 뒤에 그대로 붙인다(예: `uv run poe portability --package ac-chat`). 직접 실행:

```sh
python scripts/pkgkit/pkg_lint.py [--package NAME] [--path DIR] [--rule ID] [--json] [--list-rules]
python scripts/pkgkit/importlinter_sync.py [--check | --init [--force]]
python scripts/pkgkit/wheels.py [--clean] [--package DIST]
python scripts/pkgkit/portability.py [--package NAME] [--wheels] [--no-index] [--reuse-uv-cache | --uv-cache-dir DIR] [--keep] [--dry-run]
python scripts/pkgkit/new_package.py --kind KIND NAME [--dep D] [--dev-dep D] [--id MODULE_ID] [--dry-run]
```

README doctest는 예상 출력 뒤에 빈 줄을 둔다(없으면 닫는 ```` ``` ```` 줄을 출력으로 읽는다).

사내 의존 범위 `"from-package"`(`pkgkit_py.toml` `[python.internal_ranges]`)는 워크스페이스에 그 패키지가 있어야 풀린다. 저장소 밖에서 `new_package.py`·`pkg_lint.py`를 쓰면(그 패키지가 워크스페이스에 없으면) `"from-package"` 대신 범위를 직접 적는다(예: `agent-console-contracts = ">=0.5,<0.6"`).

테스트: `uv run pytest scripts/pkgkit`(이 폴더의 `pytest.ini`를 쓴다) · `uv run mypy scripts/pkgkit` · `uv run ruff check scripts/pkgkit`
