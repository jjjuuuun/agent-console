"""S1 정적 출처: 서버 응답 밖에서 화면에 가는 원문을 모은다(서버를 띄우지 않는다).

웹은 서버 응답만이 아니라 계약 JSON Schema 문서(설정·스펙·위키 편집 폼)와 패키지 데이터 값도
서버 문구 묶음으로 화면 언어에 옮긴다. 이 문구는 GET 훑기로는 보이지 않으므로 ``i18n.yaml``
``static``에 적은 출처에서 바로 읽는다.

- ``static.schemas``: JSON Schema 문서 하나 + 화면이 그리는 모델 이름(``models``와, 웹 소스에서
  ``discover`` 정규식으로 찾은 이름). 모델에서 ``$ref``를 따라간 정의까지 서버 응답과 같은 규칙
  (``collect`` — ``skip_keys``·``keep_keys_in``)으로 모은다.
- ``static.data``: 패키지 데이터 파일(YAML·JSON)과 ``select`` 경로(``/a/*/b``, 없으면 파일 전체).

결과는 ``CrawlResult``와 같은 모양이고, 나온 곳은 ``schema:<모델>``·``data:<파일>``로 적는다.
"""

from __future__ import annotations

import fnmatch
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from i18n_common import Config, I18nToolError, SchemaSource
from i18n_crawl import CrawlResult, collect, select
from ruamel.yaml import YAML


@dataclass(slots=True)
class StaticResult:
    """정적 출처에서 모은 것."""

    result: CrawlResult = field(default_factory=CrawlResult)
    models: list[str] = field(default_factory=list)
    """읽은 모델(``$ref``로 따라간 정의 포함)."""
    unknown_models: list[str] = field(default_factory=list)
    """이름은 찾았지만 문서에 없는 모델(웹 테스트용 가짜 이름 등)."""
    files: list[str] = field(default_factory=list)


def _glob(repo: Path, patterns: tuple[str, ...], exclude: tuple[str, ...] = ()) -> Iterator[Path]:
    seen: set[Path] = set()
    for pattern in patterns:
        for path in sorted(repo.glob(pattern)):
            rel = path.relative_to(repo).as_posix()
            if path in seen or not path.is_file():
                continue
            if any(fnmatch.fnmatchcase(rel, p) for p in exclude):
                continue
            seen.add(path)
            yield path


def _read_data(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    return YAML(typ="safe", pure=True).load(text)


def discover_models(repo: Path, source: SchemaSource) -> list[str]:
    """``models``와 ``discover`` 규칙으로 찾은 모델 이름(순서대로, 중복 없음)."""
    names = list(source.models)
    rule = source.discover
    if rule is not None:
        for path in _glob(repo, rule.files, rule.exclude):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            names.extend(m.group(1) for m in rule.pattern.finditer(text))
    return list(dict.fromkeys(names))


def _refs(node: Any, config: Config, prefix: str, parent: str | None = None) -> Iterator[str]:
    """``$ref``가 ``prefix``로 시작하는 정의 이름.

    데이터 키 안은 보지 않는다(``collect``와 같은 규칙)."""
    if isinstance(node, Mapping):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith(prefix):
            yield ref[len(prefix) :]
        names = parent in config.name_maps
        for key, value in node.items():
            if names or key not in config.skip_keys:
                yield from _refs(value, config, prefix, None if names else str(key))
    elif isinstance(node, list):
        for item in node:
            yield from _refs(item, config, prefix, parent)


def collect_schema(
    doc: Mapping[str, Any],
    models: list[str],
    config: Config,
    out: StaticResult,
    *,
    defs_key: str = "$defs",
) -> None:
    """모델과 ``$ref``로 닿는 정의의 화면 문구를 모은다(나온 곳 = ``schema:<처음 모델>``)."""
    defs = doc.get(defs_key)
    if not isinstance(defs, Mapping):
        return
    prefix = f"#/{defs_key}/"
    seen: set[str] = set()
    for model in models:
        if model not in defs:
            out.unknown_models.append(model)
            continue
        queue = [model]
        while queue:
            name = queue.pop()
            if name in seen or name not in defs:
                continue
            seen.add(name)
            out.models.append(name)
            collect(defs[name], f"schema:{model}", config, out.result)
            queue.extend(_refs(defs[name], config, prefix))


def collect_static(repo: Path, config: Config) -> StaticResult:
    """``static`` 설정의 출처를 모두 읽는다.

    Raises:
        I18nToolError: 스키마 문서가 없거나 JSON이 아닐 때, 데이터 파일 glob이 아무것도 못 찾을 때
            (설정이 낡았다는 뜻이라 조용히 넘기지 않는다).
    """
    out = StaticResult()
    for source in config.static.schemas:
        path = repo / source.document
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise I18nToolError(f"static.schemas: cannot read {source.document}: {exc}") from exc
        if not isinstance(doc, Mapping):
            raise I18nToolError(f"static.schemas: {source.document} must be a JSON object")
        collect_schema(doc, discover_models(repo, source), config, out, defs_key=source.defs)
    for data in config.static.data:
        paths = list(_glob(repo, data.files))
        if not paths:
            raise I18nToolError(f"static.data: no file matches {list(data.files)}")
        for path in paths:
            rel = path.relative_to(repo).as_posix()
            try:
                value = _read_data(path)
            except Exception as exc:  # 깨진 데이터 파일은 설정 오류로 알린다
                raise I18nToolError(f"static.data: cannot read {rel}: {exc}") from exc
            out.files.append(rel)
            picked = (
                [value] if not data.select else [v for s in data.select for v in select(value, s)]
            )
            for item in picked:
                collect(item, f"data:{rel}", config, out.result)
    return out


__all__ = ["StaticResult", "collect_schema", "collect_static", "discover_models"]
