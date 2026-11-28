"""S1 정적 출처: 서버 응답 밖에서 화면에 가는 원문을 모은다(서버를 띄우지 않는다).

웹은 서버 응답만이 아니라 계약 JSON Schema 문서(설정·스펙·위키 편집 폼)와 패키지 데이터 값도
서버 문구 묶음으로 화면 언어에 옮긴다. 이 문구는 GET 훑기로는 보이지 않으므로 ``i18n.yaml``
``static``에 적은 출처에서 바로 읽는다.

- ``static.schemas``: JSON Schema 문서 하나 + 화면이 그리는 모델 이름(``models``와, 웹 소스에서
  ``discover`` 정규식으로 찾은 이름). 모델에서 ``$ref``를 따라간 정의까지 서버 응답과 같은 규칙
  (``collect`` — ``skip_keys``·``keep_keys_in``)으로 모은다.
- ``static.data``: 패키지 데이터 파일(YAML·JSON)과 ``select`` 경로(``/a/*/b``, 없으면 파일 전체).
  ``pointer_slots``이면 ``{/포인터}`` 자리 표시 틀을 화면 키 꼴(``{이름}``)로 바꿔 모은다(로그
  분류기 설정의 제목·요약 틀처럼, 출처가 채운 값과 함께 응답 ``text_templates``로 싣는 틀).
- ``static.python``: 파이썬 소스에서 정한 호출의 키워드 인자·사전 키 값(코드가 정한 이벤트 제목
  등 — 응답에 나오려면 실제 기록이 있어야 해서 서버 훑기로는 보이지 않는 글자).

결과는 ``CrawlResult``와 같은 모양이고, 나온 곳은 ``schema:<모델>``·``data:<파일>``·
``python:<파일>:<줄>``로 적는다.
"""

from __future__ import annotations

import ast
import fnmatch
import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from i18n_common import Config, I18nToolError, PythonSource, SchemaSource
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
    """읽은 데이터 파일."""
    python_files: list[str] = field(default_factory=list)
    """읽은 파이썬 소스(``static.python``)."""


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


_POINTER_SLOT = re.compile(r"\{(/[^{}|]*)(?:\|(\w+))?\}")


def _slot_name(pointer: str, mode: str | None) -> str:
    pieces = [p.replace("~1", "/").replace("~0", "~") for p in pointer.split("/") if p]
    base = re.sub(r"\W", "_", pieces[-1]) if pieces else ""
    if not base:
        base = "value"
    elif not (base[0].isalpha() or base[0] == "_"):
        base = f"v{base}"
    return f"{base}_{mode}" if mode else base


def pointer_key(template: str) -> str:
    """``{/포인터}`` 자리 표시 틀 → 화면 번역 키(이름 자리 표시 틀). 바꿀 수 없으면 그대로.

    규칙(``agent_console_logs_claude.pointer_text_template``과 같다): 이름 = 포인터 마지막 조각
    (``\\W`` → ``_``, 숫자로 시작하면 ``v``, 빈 조각 ``value``) + ``|방식``이면 ``_방식``. 자리 밖
    글자의 ``{``·``}``는 두 번 쓴다. 자리 표시가 없거나, 자리 밖에 글자(문자)가 없거나, 서로 다른
    자리가 같은 이름이면 그대로 둔다(출처도 틀을 싣지 않는다 — 그대로면 묶음 키가 될 수 없어
    빠진 문구로 보고된다).

    >>> pointer_key("hook 요약 · {/hookCount}개")
    'hook 요약 · {hookCount}개'
    >>> pointer_key("{/output/0/type} 블록 {/output|count}개")
    '{type} 블록 {output_count}개'
    >>> pointer_key("{/a/name}와 {/b/name}")
    '{/a/name}와 {/b/name}'
    """
    matches = list(_POINTER_SLOT.finditer(template))
    if not matches or not any(ch.isalpha() for ch in _POINTER_SLOT.sub("", template)):
        return template
    names = {(m.group(1), m.group(2)): _slot_name(m.group(1), m.group(2)) for m in matches}
    if len(set(names.values())) != len(names):
        return template
    out: list[str] = []
    last = 0
    for m in matches:
        out.append(template[last : m.start()].replace("{", "{{").replace("}", "}}"))
        out.append("{" + names[(m.group(1), m.group(2))] + "}")
        last = m.end()
    out.append(template[last:].replace("{", "{{").replace("}", "}}"))
    return "".join(out).strip()


def _pointer_keys(value: Any) -> Any:
    if isinstance(value, str):
        return pointer_key(value)
    if isinstance(value, Mapping):
        return {k: _pointer_keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_pointer_keys(v) for v in value]
    return value


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _expr_texts(node: ast.expr) -> Iterator[str]:
    """값 식 안의 글자: 문자열 상수, 조건식·``or``·``and`` 양쪽, f-string(값 자리 ``{…}``)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.value
    elif isinstance(node, ast.JoinedStr):
        yield "".join(
            v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else "{…}"
            for v in node.values
        )
    elif isinstance(node, ast.IfExp):
        yield from _expr_texts(node.body)
        yield from _expr_texts(node.orelse)
    elif isinstance(node, ast.BoolOp):
        for value in node.values:
            yield from _expr_texts(value)


def python_texts(tree: ast.AST, source: PythonSource) -> Iterator[tuple[str, int]]:
    """소스 트리 하나에서 ``source`` 규칙에 맞는 글자와 줄.

    >>> tree = ast.parse('D(title="가" if x else f"나 {y}", other="다"); {"title": z or "라"}')
    >>> src = PythonSource(files=("*",), calls=("D",), keywords=("title",), dict_keys=("title",))
    >>> [t for t, _ in python_texts(tree, src)]
    ['가', '나 {…}', '라']
    """
    calls, keywords, keys = set(source.calls), set(source.keywords), set(source.dict_keys)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node.func) in calls:
            for kw in node.keywords:
                if kw.arg in keywords:
                    for text in _expr_texts(kw.value):
                        yield text, kw.value.lineno
        elif isinstance(node, ast.Dict) and keys:
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value in keys:
                    for text in _expr_texts(value):
                        yield text, value.lineno


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
                if data.pointer_slots:
                    item = _pointer_keys(item)
                collect(item, f"data:{rel}", config, out.result)
    for py in config.static.python:
        paths = list(_glob(repo, py.files))
        if not paths:
            raise I18nToolError(f"static.python: no file matches {list(py.files)}")
        for path in paths:
            rel = path.relative_to(repo).as_posix()
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
            except (OSError, SyntaxError, UnicodeDecodeError, ValueError) as exc:
                raise I18nToolError(f"static.python: cannot read {rel}: {exc}") from exc
            out.python_files.append(rel)
            for text, line in python_texts(tree, py):
                if config.is_source_text(text):
                    where_list = out.result.texts.setdefault(text, [])
                    where = f"python:{rel}:{line}"
                    if where not in where_list:
                        where_list.append(where)
    return out


__all__ = [
    "StaticResult",
    "collect_schema",
    "collect_static",
    "discover_models",
    "pointer_key",
    "python_texts",
]
