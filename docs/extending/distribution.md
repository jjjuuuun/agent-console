# 배포

플러그인·모듈 패키지를 다른 사람의 서버에 설치하게 하는 방법이다. 서버는 entry point를 시작할 때 읽으므로
"설치 → 다시 시작"이 전부다. 서버 쪽 패키지는 PyPI에 없으므로 설치할 때 휠 모음을 함께 준다.

## 만들기

### Python 휠

```bash
# 내 플러그인 폴더에서
uv build --wheel                         # → dist/<이름>-<버전>-py3-none-any.whl

# 소스 저장소에서: 서버와 모든 기본 패키지
uv run poe wheels                        # → dist/wheelhouse
```

휠에는 `src/` 아래 패키지와 그 안의 데이터 파일이 들어간다. 기본값·문구·대응표 같은 데이터는 패키지 안 `data/`에
두고 `importlib.resources`로 읽는다. 패키지 밖 경로(저장소 루트, 홈 폴더)를 읽지 않는다.

### TypeScript tarball

```bash
pnpm pack:all                            # 패키지마다 빌드 후 → dist/npm/*.tgz
```

웹 확장은 런타임에 설치되지 않고 웹 앱을 다시 빌드할 때 들어간다. → [웹](web.md)

## 설치

서버가 도는 Python 환경에 설치한다.

```bash
uv pip install --find-links <wheelhouse> ./dist/my_console_ops-0.1.0-py3-none-any.whl
uv pip install --python <서버 가상 환경> --find-links <wheelhouse> my-console-ops   # 환경이 다를 때
```

- 설치 뒤 서버를 다시 시작한다. 확인: `GET /api/v1/server-info`의 `plugins`(플러그인), `GET /api/v1/modules`(서버 모듈).
- 개발 중에는 `uv pip install -e <폴더>`(편집 모드)로 설치하면 코드 수정이 다음 재시작에 바로 반영된다.
- 이름·버전이 같은 휠을 다시 만들어 설치하면 uv 캐시에 남은 옛 휠이 깔릴 수 있다. 버전을 올리거나
  `uv pip install --reinstall …` 또는 새 캐시 폴더(`UV_CACHE_DIR=<빈 폴더>`)로 설치한다.
- 서버 모듈이 명령행 옵션을 선언했으면 설치 뒤 `agent-console serve --help`에 나온다.

### `uv sync`를 쓰는 환경

서버를 uv 프로젝트(예: 소스 저장소 체크아웃)에서 돌리면 `uv sync`는 lock 파일에 없는 패키지를 **지운다**. 따로 설치한
플러그인을 남기려면:

```bash
uv sync --all-packages --inexact
```

플러그인을 프로젝트 의존으로 고정하고 싶으면 `uv add`로 lock에 넣는 편이 낫다.

## 제거

```bash
uv pip uninstall my-console-ops
```

- 서버를 다시 시작한다. 그 플러그인의 이름을 쓰던 데이터는 남고, 검사가 경고·오류로 알린다
  ([플러그인 공통](plugins.md#지운-뒤-남는-데이터)).
- 서버 모듈을 지우면 그 경로가 사라지고 **DB 표와 파일은 남는다**. 표까지 지우려면 제거하기 전에 그 모듈의 계보를
  내린다. 남은 설정 `modules.options.<id>`는 경고만 내고 서버는 시작한다.
- 지우지 않고 잠시 끄려면 플러그인은 `plugins.disabled`, 모듈은 `modules.disabled`를 쓴다.

## 버전 호환

| 상황 | 결과 | 할 일 |
| --- | --- | --- |
| 서버의 계약 minor가 플러그인 범위 밖으로 올라감(예: 0.15 → 0.16) | 설치·업그레이드 때 의존 해석이 실패한다 | 새 계약으로 시험하고 범위를 올린 새 버전을 낸다 |
| 같은 minor 안의 patch | 그대로 동작 | — |
| 플러그인이 쓰는 기능 라이브러리(`agent-console-runtime` 등)의 범위 밖 | 해석 실패 | 위와 같음 |

- 서버의 계약 버전은 `GET /api/v1/server-info`의 `contracts_version`, 하위 모듈 버전은
  [계약 하위 모듈 버전](reference.md#계약-하위-모듈-버전).
- 범위를 넓게(`>=0.15`) 열어 두지 않는다. 0.x에서는 minor가 바뀌면 모양이 바뀔 수 있고, 해석 실패가 실행 중 오류보다
  알아차리기 쉽다.
- 자기 데이터(설정 키, 이벤트 type, 이슈 코드)를 바꿀 때는 옛 값을 몰래 고쳐 읽지 않는다. 서버 모듈이면
  `settings_compat`의 `RemovedSetting`으로 새 위치를 알려 주고, 플러그인이면 CHANGELOG에 적는다.

## 공개하기 전에

공개 저장소나 패키지 색인에 올리기 전에 확인한다.

- **비밀 값**: 키·토큰·세션 값이 코드·테스트 데이터·README 예·기본값 파일에 없는지. 예에는 `secret://이름` 참조만 쓴다.
- **로컬 경로**: 내 홈 폴더·드라이브 경로·사용자 이름이 설정 예, 테스트 기대 값, 로그 예에 없는지. 경로는 설정 값이나
  상대 경로로 둔다.
- **개인 정보**: 이메일·실명·사내 주소가 예와 테스트에 없는지.
- **이식성**: 플러그인 폴더만 새 폴더에 복사해 `uv sync --find-links <wheelhouse>` → `uv run pytest`가 통과하는지.

서버 쪽 비밀 의심 규칙 패키지(`agent-console-secret-rules`)로 기본값·예 데이터를 훑어볼 수 있다. 결과는 위치와 이유만
담고 값은 담지 않는다.

```python
>>> from agent_console_secret_rules import SecretRules
>>> defaults = {"endpoint": "https://example.org", "headers": {"Authorization": "Bearer abc123456"}}
>>> [(f.path, f.reason) for f in SecretRules().find_suspected(defaults, path="/defaults")]
[('/defaults/headers/Authorization', 'key_name')]

```

소스 저장소 안 문서는 `uv run poe extdocs-check`가 같은 종류의 검사(내부 경로·이메일 등)를 문서와 예제 README에 건다.
