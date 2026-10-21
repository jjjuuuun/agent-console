# agent-console-mod-resources

Agent Console 리소스 기능 모듈(design §3R.1.3, R12·R13.1). 리소스 라이브러리 경로와 리소스 종류·병합 전략 목록을
서버에 꽂고, 다른 모듈이 쓰는 리소스 조회·종류 포트를 낸다.

- 경로: `/resources`·`/resources/{id}`(CRUD, 종류 검사 error는 422), `/resources/{id}/content`(본문),
  `/resources/{id}/files[/{path}]`(여러 파일 본문, 종류 `content.multi_file`일 때만 쓰기), `/resource-types`, `/merge-strategies`.
  파일 경로의 한 칸이 예약 이름(설정 `reserved_file_names`, 기본 `.git`·`_bundle`, 대소문자 무시)이면 저장은 하고
  `X-Console-Issues` 헤더로 warning 이슈 `resource.reserved_file_name`(`path` = JSON Pointer `/files/<파일 경로>`, `details = {path, name}`, 메시지에 파일 경로)을 돌려준다.
  붙은 곳(`/resources/{id}/usages`)은 `link-definitions-teams`가 붙인다.
- 필수 포트: `definitions.store`. 선택 포트: `definitions.usages`(목록 `usage_count`, 없으면 null).
- 제공 포트: `resources.lookup`(`ac-resources.ResourceLookup` + `FileContentLookup`), `resources.types`(종류 레지스트리).
- 종류 레지스트리는 호스트 기본 서비스 `registries`의 `resource_types` 확장. 없으면(단독 실행) entry point와
  워크스페이스 `resource-types/*.yaml`을 직접 읽는다. 본문 크기 한도는 정의 저장소(`mod-definitions`)가 건다.
- 설정 `modules.options.mod-resources`: `types_extension`, `declarative_dir`, `content_files`(형식 → 본문 파일 이름),
  `default_content_file`, `reserved_file_names`(경고할 경로 칸 이름, 빈 목록이면 경고 없음).
- 웹 역할: `definitions:resource`.

## 설치

```bash
pip install agent-console-mod-resources
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-mod-resources
```

## 최소 사용

정의 저장소를 주는 모듈과 함께 조립하면 리소스 조회 포트가 저장소를 읽는다.

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_modkit import assemble
>>> from agent_console_mod_resources import RESOURCES_LOOKUP, module
>>> from agent_console_mod_resources.testing import local_definitions_module
>>> workspace = Path(tempfile.mkdtemp())
>>> assembly = assemble([module, local_definitions_module(workspace=workspace)])
>>> lookup = assembly.port(RESOURCES_LOOKUP)
>>> lookup.get_resource("guide") is None
True
>>> (workspace / "resources").mkdir()
>>> _ = (workspace / "resources" / "guide.yaml").write_text(
...     "id: guide\ntype: instruction\nname: 안내\nconfig: {}\n", encoding="utf-8")
>>> lookup.get_resource("guide").name
'안내'

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```

단독 실행. `--with`를 주지 않으면 `testing.local_definitions_module`(워크스페이스 파일 저장소)을 붙인다.

```bash
python -m agent_console_mod_resources [--with ID] [--config PATH] [--port 0] [--check]
```
