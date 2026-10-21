# agent-console-example-log-source

새 **로그 출처(X5)** 와 **로그 분류기(X6)** 를 플러그인 패키지 하나로 추가하는 예제(R0.3·R10.4).
엔진·서버·웹 코드를 고치지 않고, 설치하면 로그 출처 목록(`GET /api/v1/logs/sources`)과 분류기 목록에
나타나고 제거하면 사라진다.

출처·분류기 `example.text_log`(텍스트 로그)
- 형식: 한 줄에 `<ISO 8601 시각> <수준> [<스레드>] <메시지>`(`[스레드]`는 생략 가능).
- 출처는 `JsonlFileSource`를 상속하고 `parse_line`만 바꾼다. 증분 읽기(바이트 오프셋 커서)·끝나지 않은 줄 보류·
  파일 회전 감지·읽기 전용 열기는 기반 클래스가 한다. 형식이 틀린 줄은 버리지 않고 진단 이벤트가 된다.
- 분류기는 행 단위 무상태다. 수준 → 범주 대응은 설정 데이터(`level_categories`, 기본 `ERROR`·`FATAL` → `error`,
  나머지 `default_category` = `system`)라 코드를 고치지 않고 바꾼다. 세션 = 파일, 상태 = 수준 소문자.
- 원본 파일은 읽기만 한다(테스트가 `no_writes_under`·`tree_digest`로 확인).

이 패키지는 uv workspace 멤버가 아니다. 설치하지 않으면 아무 동작도 바꾸지 않는다.

## 최소 코드

출처는 `parse_line`(줄 → 값), 분류기는 `classify`(값 → 정규화 이벤트 초안)만 쓰면 된다.

```python
>>> from typing import ClassVar
>>> from agent_console_contracts.logs import LogClassifierDescriptor, LogSourceDescriptor
>>> from agent_console_logs import JSONL_CONFIG_SCHEMA, JsonlFileSource, LogEventDraft

>>> class TinySource(JsonlFileSource):
...     descriptor: ClassVar[LogSourceDescriptor] = LogSourceDescriptor(
...         id="tiny", title="한 줄 텍스트", format="tiny", config_schema=JSONL_CONFIG_SCHEMA
...     )
...     def parse_line(self, line):
...         level, _, message = line.decode("utf-8").partition(" ")
...         return {"level": level, "message": message}

>>> class TinyClassifier:
...     descriptor = LogClassifierDescriptor(id="tiny", formats=["tiny"], title="한 줄 텍스트")
...     def classify(self, record, ctx):
...         row = record.data
...         category = "error" if row["level"] == "ERROR" else "system"
...         return [LogEventDraft(category=category, title=row["message"], session=ctx.ref.ref)]

```

실제 구현은 `src/agent_console_example_log_source/text_log.py`(시각 해석, 순수 함수 `parse_text_line`,
설정 스키마로 수준 → 범주 대응). 아래는 그 구현을 entry point로 등록한 것처럼 로드해 수집하는 예다.

```python
>>> import tempfile
>>> from importlib.metadata import EntryPoint
>>> from pathlib import Path
>>> from agent_console_contracts.logs import LogSettings
>>> from agent_console_logs import (
...     LOG_CLASSIFIERS_GROUP, LOG_SOURCES_GROUP, LogFilter, LogIngestor, LogRegistries, query_context,
... )
>>> from agent_console_logs.testing import MemoryLogIndex

>>> value = "agent_console_example_log_source:"
>>> eps = [
...     EntryPoint("example.text_log", value + "TextLogSource", LOG_SOURCES_GROUP),
...     EntryPoint("example.text_log", value + "TextLogClassifier", LOG_CLASSIFIERS_GROUP),
... ]
>>> registries = LogRegistries()
>>> _ = registries.load(entry_points=eps)        # 설치했으면 load()만 부른다
>>> [d.id for d in registries.source_descriptors()]
['example.text_log']

>>> folder = Path(tempfile.mkdtemp())
>>> _ = (folder / "app.log").write_text(
...     "2026-10-17T09:00:00Z INFO [worker] 작업 시작\n"
...     "2026-10-17T09:00:02Z ERROR [worker] 연결 실패\n",
...     encoding="utf-8",
... )
>>> index = MemoryLogIndex()
>>> ingestor = LogIngestor(index, registries)
>>> settings = LogSettings.model_validate(
...     {"sources": [{"id": "example.text_log", "enabled": True, "config": {"roots": [str(folder)]}}]}
... )
>>> ingestor.scan(settings).new_events
2
>>> [(e.category, e.title, e.status) for e in index.query_events(LogFilter(), query_context(settings)).items]
[('system', '작업 시작', 'info'), ('error', '연결 실패', 'error')]

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 등록과 설정

```toml
[project.entry-points."agent_console.log_sources"]       # agent_console_logs.LOG_SOURCES_GROUP
"example.text_log" = "agent_console_example_log_source:TextLogSource"

[project.entry-points."agent_console.log_classifiers"]   # agent_console_logs.LOG_CLASSIFIERS_GROUP
"example.text_log" = "agent_console_example_log_source:TextLogClassifier"
```

출처 디스크립터의 `format`이 기본 분류기 id다. 설정 `logs.sources[].config.classifier.id`로 다른 분류기를, `classifier.config`로 분류기 설정을 준다.
설치하지 않은 모듈은 `LogRegistries.load(source_modules=["example.text_log=agent_console_example_log_source:TextLogSource"],
classifier_modules=[...])`로 읽는다(같은 검사기를 거친다).

워크스페이스 설정(설정 화면 또는 `settings.yaml`). 루트를 정해야 하므로 기본은 꺼져 있다.

```yaml
logs:
  sources:
    - id: example.text_log
      enabled: true
      config:
        roots: ["~/my-app/logs"]           # 기본 포함 패턴 **/*.log
        classifier:                        # {id?, config?} — id를 비우면 출처의 format
          config:
            level_categories: {ERROR: error, WARN: error}
            default_category: system
```

## 설치·제거

```bash
export UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=$HOME/.cache/agent-console-wsl-venv   # WSL만
uv pip install --python "$UV_PROJECT_ENVIRONMENT" -e examples/extensions/agent-console-example-log-source   # 설치
uv pip uninstall --python "$UV_PROJECT_ENVIRONMENT" agent-console-example-log-source                        # 제거
```

설치·제거 뒤 **서버를 재시작**한다.
- 설치: `GET /api/v1/logs/sources`에 `example.text_log`가 나온다(꺼진 상태). 위 설정을 넣고 수집하면 세션 목록에 파일마다 세션이 보인다.
- 제거: 출처 목록에서 사라진다. 설정의 `logs.sources` 항목과 이미 색인한 이벤트는 남지만 새로 수집하지 않는다.
- 설치한 채로 끄기: 설정 항목에 `enabled: false`, 또는 서버 설정 `plugins.enabled`(허용 목록)에서 뺀다.

주의: `uv sync`는 lock에 없는 패키지를 지운다. 예제를 설치한 채 동기화하려면 `uv sync --all-packages --inexact`.

## 테스트

```bash
cd examples/extensions/agent-console-example-log-source
uv run --project ../../.. python -m pytest
```

설치 없이 돈다(`pythonpath = ["src"]`). 루트 `uv run poe check`의 `examples` 단계가 이 폴더 설정으로 mypy·pytest를 돌린다(`uv run poe examples`).
