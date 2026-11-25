# 패키지 만들기

확장은 패키지 하나로 들어온다. 패키지는 자기 역할 하나만 하고, 공개 API와 내부 구현을 나누고, 저장소 밖으로
가져가도 설치·테스트가 된다. 이 문서는 소스 저장소 안에서 기본 패키지를 더할 때와, 저장소 밖에서 플러그인
패키지를 만들 때를 나눠 설명한다.

## 저장소 밖에서 (플러그인 작성자)

### 최소 `pyproject.toml`

```toml
[project]
name = "my-console-notes"                    # 자기 이름. agent-console- 접두는 쓰지 않는다
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "agent-console-contracts>=0.15,<0.16",   # 쓰는 서버 패키지마다 범위를 적는다
]

[project.entry-points."agent_console.node_types"]   # 확장 지점 = entry point 그룹
"mine.note" = "my_console_notes:NoteNode"          # 이름 = 등록 id

[build-system]
requires = ["uv_build>=0.8.17,<0.9"]
build-backend = "uv_build"
```

배치는 `src/` 아래에 import 이름 폴더 하나를 둔다(`src/my_console_notes/__init__.py`). 처음부터 끝까지 따라 하는
예는 [시작하기](getting-started.md).

### 이름 규칙

| 무엇 | 규칙 | 예 |
| --- | --- | --- |
| 배포 이름 | 자기 이름. `agent-console-*`는 서버 배포가 쓰므로 피한다 | `my-console-notes` |
| import 이름 | 배포 이름의 `-`를 `_`로. `agent_console_*`는 피한다 | `my_console_notes` |
| 등록 id(entry point 이름) | 자기 접두사 + 점 + 이름. 기본 구현과 겹치지 않게 | `mine.note`, `acme.relay` |
| 이벤트 type·이슈 코드 | 자기 접두사로 시작 | `mine.note_saved`, `mine.too_long` |
| 서버 모듈 id | 기능 모듈 `mod-<이름>`, 연동 모듈 `link-<a>-<b>` 모양을 권한다 | `mod-notes`, `link-notes-runs` |

등록 id·이벤트·이슈 코드의 접두사는 다른 플러그인과 서로 부딪히지 않게 하려는 것이다. 같은 그룹에 같은 이름이
둘이면 하나만 등록된다([플러그인 공통](plugins.md#이름과-중복)).

### 의존 범위

- 서버 쪽 패키지는 **이름 + 버전 범위**로만 의존한다. 경로 의존(`path = "../.."`)이나 저장소 상대 경로를 쓰지 않는다.
- 0.x 패키지는 같은 minor 안에서만 호환을 약속한다. `>=0.15,<0.16`처럼 minor 하나로 묶는다.
- 계약(`agent-console-contracts`) 범위는 설치된 서버의 계약 버전에 맞춘다. 버전과 하위 모듈 버전은
  [계약과 이벤트](contracts-events.md#버전)를 본다.
- 쓰는 것만 의존한다. 조건 연산자는 계약 하나로 충분하고, 노드 종류는 런타임(`agent-console-runtime`)의 프로토콜을
  쓴다. 테스트에만 쓰는 서버 패키지는 dev 의존으로 둔다.

```toml
[dependency-groups]
dev = [
    "pytest>=8.3",
    "agent-console-conditions>=0.1,<0.2",    # 테스트가 평가기로 확인할 때만
]
```

사내 패키지는 PyPI에 없다. 설치·`uv sync`할 때 휠 모음을 찾기 경로로 준다(`--find-links <wheelhouse>`).
자세한 내용은 [배포](distribution.md).

## 저장소 안에서 (기본 패키지)

### Python

```bash
uv run poe new-package --kind feature ac-notes
uv run poe new-package --kind module ac-mod-notes --id mod-notes
uv run poe new-package --kind link ac-link-notes-runs --id link-notes-runs
```

| 종류 | 폴더 | 무엇 |
| --- | --- | --- |
| `base` | `packages/py/base/` | 계약·레지스트리처럼 거의 모든 패키지가 쓰는 얇은 층. 다른 사내 패키지에 되도록 의존하지 않는다 |
| `feature` | `packages/py/features/` | 기능 라이브러리. 서버 프레임워크·모듈 키트·서버 모듈을 모른다 |
| `kit` | `packages/py/kit/` | 모듈 키트. 기반 층만 안다 |
| `module` | `packages/py/modules/` | 서버 모듈. 기능 라이브러리 하나를 서버에 꽂는다. `python -m <import 이름> --check`로 단독 실행 |
| `link` | `packages/py/links/` | 연동 모듈. 두 서버 모듈의 공개 포트를 잇는다 |

`new-package`는 템플릿으로 폴더를 만들고, 워크스페이스 멤버와 루트 `[tool.uv.sources]`에 이름을 더하고, import 규칙
목록을 갱신한다. 이름은 폴더 `ac-<이름>`, 배포 `agent-console-<이름>`, import `agent_console_<이름>`으로 맞춰진다.
`--dep`·`--dev-dep`로 의존을, `--dry-run`으로 만들 파일만 볼 수 있다.

만든 뒤 지킬 것:

- **import 규칙**: 패키지 사이 허용·금지는 `importlinter.rules.toml`에 그룹 단위로 적는다(예: "기능 모듈은 서로
  모른다"). 고쳤으면 `uv run poe importlinter-sync`로 반영한다. 새 패키지는 그룹 규칙에 자동으로 들어간다.
- **이식성**: `uv run poe pkg-lint`가 패키지 밖 경로·패키지별 `[tool.uv.sources]`·다른 패키지 `tests` import·필수
  파일·도구 설정을 검사한다. 실제로 저장소 밖에 복사해 돌리는 검사는 `uv run poe portability --package <폴더 이름>`.
- **확장 지점 선언**: 새 entry point 그룹 상수나 새 포트를 만들었으면 그 패키지 `pyproject.toml`에
  `[tool.agent-console.extension-points.<slug>]`를 더한다. 빠지면 `uv run poe extpoints-check`가 실패한다.
  선언 형식은 이미 선언된 패키지를 본다([확장 지점 참조](reference.md#확장-지점)의 각 행이 선언 하나다).

### TypeScript

```bash
pnpm new-package --kind lib notes-view
pnpm new-package --kind config my-config
```

- `lib`는 `packages/ts/lib/`, `config`는 공용 설정 패키지다. React 컴포넌트를 쓰면 `--dom`을 준다.
- 패키지 `exports`는 `development` 조건으로 소스를, `types`·`default`로 `dist`를 가리킨다. 사내 의존은 `^x.y.z` 범위로
  적는다(`workspace:` 프로토콜 금지).
- `pnpm pkg-lint`가 경로·exports·의존 선언·README 예 동기화를 검사하고, `pnpm portability --package <이름>`이 저장소
  밖에서 설치·빌드·테스트한다.

웹 확장 전체는 [웹](web.md)을 본다.

## README와 테스트

패키지마다 README와 테스트를 둔다. README에는 적어도 다음이 있다.

| 절 | 내용 |
| --- | --- |
| 무엇을 하나 | 한두 문단. 어떤 확장 지점을 쓰는지 |
| 설치 | 설치 명령(휠 모음 찾기 경로 포함) |
| 최소 사용 | 서버 없이 쓰는 예. Python은 `>>>` doctest로 써서 테스트가 함께 돌린다 |
| 등록과 설정 | entry point 표, 설정 키 |
| 설치·제거 | 설치·제거 명령, 다시 시작, 제거 뒤 남는 데이터와 경고 |
| 테스트 | 테스트 실행 명령 |

doctest는 예상 출력 뒤에 빈 줄을 하나 둔다(닫는 펜스 줄을 출력으로 읽지 않게). 예제 README의 실제 모양은
[예제 색인](../../examples/extensions/README.md)의 아무 예제나 보면 된다.

공개 API는 패키지 루트(`__init__.py`, TS는 `src/index.ts`)에서 내보내고 타입 힌트와 짧은 문서(용도·인자·반환·
예외)를 단다. 다른 패키지의 `_` 모듈이나 `tests`를 import하지 않는다. 시험용 대역이 필요하면 그 패키지의 공개
`testing` 모듈을 쓴다([테스트](testing.md#4-조립-테스트)).
