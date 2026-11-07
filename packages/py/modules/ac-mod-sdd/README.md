# agent-console-mod-sdd

Agent Console 스펙(SDD) 서버 모듈(`mod-sdd`). `ac-sdd`(작업 문법·파싱·계획·추적·
스펙 저장소)를 서버에 붙인다. 실행·프로젝트를 모르고, 둘 다 연동 모듈이 포트로 붙인다.

- REST `/sdd/*`(스펙 목록·만들기·보기·저장·삭제, 문서 본문·상태, 작업·고치기, 계획·추적·입력 변수·
  유효 문법, 작업 연동 동작·한꺼번에 시작·자동 진행, 틀로 저장, 폴더에서 가져오기·내보내기, 화면 정보
  `GET /sdd/info`). 모든 경로가 `?project=<공간 이름>`을 받는다.
- 문서 틀 하나(`template_routes`): `POST /sdd/templates`(빈 틀), `GET·PUT·DELETE /sdd/templates/{id}`
  (`ETag`·`If-Match` = 정의 버전), 뼈대 파일 `…/files[/{path}]`, 버전 `…/versions…`·`…/restore`. 저장소는 틀
  목록과 같다(라이브러리 → 없으면 단독 루트, `?project=` = 그 공간). `variables`·`check`는 틀 id로 쓸 수 없다.
- `GET /sdd/import/files?path=`: 그 폴더의 마크다운 파일과 바로 아래 하위 폴더(`dirs`, 숨김·링크·예약 제외).
- WS 토픽 `sdd.changed`(본문 없음 — 화면은 다시 읽는다).
- 정의 종류 기여(`definitions.kind_contributions`): 문서 틀(라이브러리·프로젝트, 실행 프로필의
  팀 구성 참조 추출)과 스펙(`library=False`). 종류 이름·폴더 이름은 설치자 옵션(기본값은 패키지 데이터
  `data/defaults.json`).
- 사용자 설정 섹션 `sdd`(`include_default_syntax`·`syntax`·`secret_scan`·`verification_sources`).
  모르는 키는 보존하고, 깨진 부분만 빼고 `server.warnings`에 `sdd.settings_invalid`로 알린다.
- 공간: `sdd.spaces`(선택, `link-projects-sdd`가 준다). 공간 이름이 없는 요청은 단독 루트
  (`standalone_root`, 기본 워크스페이스 안 `sdd/`). 이름이 왔는데 연동이 없으면 409
  `sdd.spaces_unavailable`(앱 workspace에 대신 만들지 않는다). 공간 이름이 없는 문서 틀 요청은 앱
  라이브러리(`definitions.store`)를 읽고, 라이브러리가 없으면 단독 루트의 틀을 읽는다.
- 확장 지점: 작업 연동(`sdd.integrations`, 여러 제공자), 검증 결과 출처
  (`sdd.verification_sources` 포트 + entry point `agent_console.sdd_verification_sources`, 플러그인
  출처는 사용자 설정으로 켠다). 화면 능력 `SddInfo.capabilities`는 포트 유무로 계산한다.
- 실행 라벨 표시 규칙: 설치자 접두(`run_label_prefix`, 기본 `sdd.`)를 붙여
  `ModuleParts.label_display`로 낸다 → `GET /modules`의 `label_display`.
- 파싱 캐시(공간·스펙·정의 버전·본문 해시·유효 문법 키, LRU)와 문서 본문 비밀 검사(`secret_scan`:
  off·warn·reject).

## 의존성: 무엇을 / 왜 / 대안

- 사내: `agent-console-sdd`(SDD 핵심), `agent-console-store`(정의 저장소·버전), `agent-console-conditions`
  (관문 연산자 레지스트리), `agent-console-registry`(검증 출처 플러그인), `agent-console-secret-rules`
  (본문 비밀 검사), `agent-console-modkit[host]`(모듈·호스트). 새 외부 의존 없음(FastAPI·pydantic은
  다른 모듈과 같다).

## 설치

```bash
pip install agent-console-mod-sdd
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-mod-sdd
```

## 최소 사용 (모듈 하나 + 단독 루트)

```python
>>> import tempfile
>>> from pathlib import Path
>>> from fastapi.testclient import TestClient
>>> from agent_console_mod_sdd import module
>>> from agent_console_modkit import BaseServices, Paths, assemble
>>> from agent_console_modkit.host import SecurityPolicy, create_host_app

>>> tmp = Path(tempfile.mkdtemp())
>>> base = BaseServices(paths=Paths(base_dir=tmp, workspace=tmp / "ws", state=tmp / "state"))
>>> assembly = assemble([module], base=base)
>>> policy = SecurityPolicy.for_bind("127.0.0.1", 0, token="t" * 32, allowed_hosts=["testserver"])
>>> client = TestClient(create_host_app(assembly, policy=policy))
>>> client.headers["X-Console-Token"] = "t" * 32
>>> with client:
...     print(client.get("/api/v1/sdd/specs").json())
...     made = client.post("/api/v1/sdd/specs", json={"name": "Demo"}).json()
...     print(made["spec"]["id"], made["directory"])
[]
demo specs/demo

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

단독 실행: `python -m agent_console_mod_sdd [--with ID] [--config PATH] [--port 0] [--check]`. 사용자
설정은 워크스페이스 `settings.yaml`의 `sdd` 섹션.

## 포트

| 포트 | 방향 | 모양 |
| --- | --- | --- |
| `sdd.service` | 제공 | `SddServicePort`: `label_key(name)`·`secret_findings(text)`·`secret_mode()`·`notify(space, spec_id)` (+ 구현 `SddService`의 `scope(space)`·`context(scope, loaded)`) |
| `definitions.kind_contributions` | 제공(여러) | `KindContribution(DefinitionKind, references, title, delete)` 두 개(`delete` = 자기 삭제 경로와 같은 일, 종류 공통 삭제가 부른다) |
| `server.warnings` | 제공(여러) | 사용자 설정 형식 문제 |
| `sdd.spaces` | 선택 | `SddSpaces.open(name) -> SddSpace{store, files, config_writable, config_dir?, max_content_bytes?}` |
| `sdd.integrations` | 선택(여러) | `agent_console_sdd.TaskIntegration` (+ 선택 속성 `link_kinds`, 능력 `ProfileChecker`·`AutomationControl`) |
| `sdd.verification_sources` | 선택(여러) | `agent_console_sdd.VerificationSource` |
| `workspace.settings`·`secrets.rules`·`definitions.store` | 선택 | 사용자 설정·비밀 규칙·라이브러리 저장소 |

- 연동의 `link_kinds`(예: `("run",)`)에 `run`이 있으면 `capabilities.runs=true`. 자동 진행은
  `AutomationControl`을 구현한 연동이 있을 때만(`capabilities.automation`, 경로 `…/automation/{stop|
  resume}`는 없으면 404).
- 테스트·다른 앱용 가짜: `agent_console_mod_sdd.testing`(`SimpleSpace`·`spaces_module`·
  `integration_module`·`verification_module`·`library_module`·`static_settings_module`).

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
