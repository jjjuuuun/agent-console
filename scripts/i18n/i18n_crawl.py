"""S1: 서버 GET 응답에서 원문 문구와 이슈 코드를 모은다(design §I18N.10 S1).

HTTP는 주입 함수(``HttpPort``)로 받는다. 조립 서버는 ``assembled_server``가 만든다
(``agent_console_server.testing`` — fake 백엔드, 빈 작업 공간, 실제 ``~/.claude`` 대신 빈 폴더).
"""

from __future__ import annotations

import fnmatch
import itertools
import os
import re
import tempfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final
from urllib.parse import quote

from i18n_common import Config, ParamSource, ServerConfig

_PARAM: Final = re.compile(r"\{(\w+)\}")

type GetFn = Callable[[str], tuple[int, Any | None]]
"""경로 → (상태 코드, JSON 값 — JSON이 아니면 None)."""
type SendFn = Callable[[str, str, Any, Mapping[str, str]], int]
"""(메서드, 경로, 본문, 머리글) → 상태 코드."""


@dataclass(frozen=True, slots=True)
class HttpPort:
    """훑기에 쓰는 HTTP 함수 둘(테스트는 가짜를 넘긴다)."""

    get: GetFn
    send: SendFn


@dataclass(frozen=True, slots=True)
class IssueSeen:
    """응답에서 본 오류·이슈 객체 하나."""

    code: str
    where: str
    details: frozenset[str] | None


@dataclass(slots=True)
class CrawlResult:
    """훑은 결과."""

    texts: dict[str, list[str]] = field(default_factory=dict)
    """원문 문구 → 나온 경로(경로 틀) 목록."""
    issues: list[IssueSeen] = field(default_factory=list)
    visited: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)
    """경로 틀 → 건너뛴 이유."""
    seed_failures: list[str] = field(default_factory=list)


def select(doc: Any, path: str) -> list[Any]:
    """``/a/*/b`` 꼴 경로로 값을 고른다(``*`` = 목록 항목·사전 값 전부).

    >>> select({"profiles": [{"id": "a"}, {"id": "b"}]}, "/profiles/*/id")
    ['a', 'b']
    >>> select([{"id": 1}], "/*/id")
    [1]
    """
    nodes = [doc]
    for part in [p for p in path.split("/") if p]:
        nxt: list[Any] = []
        for node in nodes:
            if part == "*":
                if isinstance(node, list):
                    nxt.extend(node)
                elif isinstance(node, Mapping):
                    nxt.extend(node.values())
            elif isinstance(node, Mapping) and part in node:
                nxt.append(node[part])
            elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
                nxt.append(node[int(part)])
        nodes = nxt
    return nodes


def collect(doc: Any, where: str, config: Config, result: CrawlResult) -> None:
    """응답 값 하나에서 원문 문구(``result.texts``)와 이슈(``result.issues``)를 모은다.

    이슈 모양 객체(``issue.code``·``issue.message``가 문자열)의 ``message``는 S2(코드)로 보므로
    문구로 모으지 않는다. ``texts.skip_keys``의 키 값은 들어가지 않는다. 다만
    ``texts.keep_keys_in``의 부모 키 바로 안에서는 그 키의 문자열을 모은다(예: ``x-ui``의
    ``example`` — 웹이 화면 언어로 옮기는 예시 글자. 스키마 ``examples``·``default``는
    데이터라 뺀다).
    ``texts.name_maps`` 키(``properties`` 등)의 바로 안 키는 이름이라 건너뛰지 않는다.
    ``texts.templates_key``(``text_templates``) 표가 있는 객체는 그 틀(중첩 포함)을 문구로 모으고,
    틀이 덮은 칸(JSON Pointer) 값은 모으지 않는다(값이 섞인 문장 — 화면이 틀로 번역한다).
    """
    shape = config.issue
    skip = set(config.skip_keys)
    keep_in = config.keep_keys_in
    name_maps = set(config.name_maps)

    def walk(node: Any, parent: str | None = None) -> None:
        if isinstance(node, Mapping):
            node = expand_text_templates(node, config.templates_key)
            code = node.get(shape.code)
            is_issue = isinstance(code, str) and isinstance(node.get(shape.message), str)
            if is_issue and isinstance(code, str):
                details = node.get(shape.details)
                keys = frozenset(str(k) for k in details) if isinstance(details, Mapping) else None
                result.issues.append(IssueSeen(code, where, keys))
            kept = keep_in.get(parent, ()) if parent is not None else ()
            names = parent in name_maps
            for key, value in node.items():
                if is_issue and key == shape.message:
                    continue
                if names:
                    walk(value)  # 속성 이름은 데이터 키가 아니다(``properties.default`` 등)
                    continue
                if key in skip:
                    if key in kept and isinstance(value, str):
                        walk(value)
                    continue
                walk(value, str(key))
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, str) and config.is_source_text(node):
            paths = result.texts.setdefault(node, [])
            if where not in paths:
                paths.append(where)

    walk(doc)


def _template_texts(parts: Any) -> list[str]:
    """틀 목록(``[{template, params}]``)의 원문 틀 — params의 중첩 틀까지."""
    out: list[str] = []

    def one(item: Any) -> None:
        if not isinstance(item, Mapping) or not isinstance(item.get("template"), str):
            return
        out.append(item["template"])
        params = item.get("params")
        if isinstance(params, Mapping):
            for value in params.values():
                one(value)

    for part in parts if isinstance(parts, list) else []:
        one(part)
    return out


def _blank(doc: Any, pointer: str) -> Any:
    """``pointer``(JSON Pointer) 자리의 문자열을 뺀 얕은 사본(경로만 복사)."""
    if not pointer.startswith("/"):
        return doc
    head, _, rest = pointer[1:].partition("/")
    key = head.replace("~1", "/").replace("~0", "~")
    sub = "/" + rest if rest else ""

    def changed(value: Any) -> Any:
        if sub:
            return _blank(value, sub)
        return None if isinstance(value, str) else value

    if isinstance(doc, Mapping) and key in doc:
        return {**doc, key: changed(doc[key])}
    if isinstance(doc, list) and key.isdigit() and int(key) < len(doc):
        i = int(key)
        return [*doc[:i], changed(doc[i]), *doc[i + 1 :]]
    return doc


def expand_text_templates(node: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    """``key`` 표가 있으면: 덮인 칸 값을 빼고 표 자리에 원문 틀 목록을 둔 사본. 없으면 그대로.

    >>> doc = {"detail": "자격 위치: .x", "text_templates": {"/detail": [
    ...     {"template": "자격 위치: {path}", "params": {"path": ".x"}}]}}
    >>> expand_text_templates(doc, "text_templates")
    {'detail': None, 'text_templates': ['자격 위치: {path}']}
    """
    table = node.get(key)
    if not isinstance(table, Mapping) or not table:
        return node
    out: dict[str, Any] = dict(node)
    texts: list[str] = []
    for pointer, parts in table.items():
        found = _template_texts(parts)
        if not found:
            continue
        texts.extend(t for t in found if t not in texts)
        out = dict(_blank(out, str(pointer)))
    out[key] = texts
    return out


def _param_values(
    name: str,
    server: ServerConfig,
    http: HttpPort,
    cache: dict[str, list[str]],
    specs: Mapping[str, ParamSource] | None = None,
) -> list[str]:
    if name in cache:
        return cache[name]
    spec = (server.params if specs is None else specs).get(name)
    values: list[str] = []
    if spec is not None:
        values.extend(spec.values)
        if spec.source:
            status, doc = http.get(spec.source)
            if status == 200 and doc is not None:
                values.extend(str(v) for v in select(doc, spec.select) if isinstance(v, str | int))
    cache[name] = list(dict.fromkeys(values))[: server.max_param_values]
    return cache[name]


def crawl(openapi: Mapping[str, Any], http: HttpPort, config: Config) -> CrawlResult:
    """OpenAPI의 GET 경로를 모두 훑는다(경로 변수는 ``server.params``, 씨앗은 ``server.seeds``).

    200 JSON 응답만 모은다. 값이 없는 경로 변수가 있거나 ``skip_paths``에 맞는 경로는
    ``skipped``에 이유와 함께 적는다. 경로가 선언한 질의 변수 중 ``server.query_params``에 값이 있는
    것은 값마다 ``?이름=값``을 붙여 한 번 더 읽는다(예: 프로젝트 공간 ``project``).
    """
    server = config.server
    result = CrawlResult()
    for seed in server.seeds:
        headers: dict[str, str] = {}
        if seed.if_match is not None and seed.if_match.source:
            got, doc = http.get(seed.if_match.source)
            found = select(doc, seed.if_match.select) if got == 200 else []
            if found and isinstance(found[0], str):
                headers["If-Match"] = f'"{found[0]}"'
        status = http.send(seed.method, seed.path, seed.body, headers)
        if status >= 400:
            result.seed_failures.append(f"{seed.method} {seed.path} -> {status}")
    cache: dict[str, list[str]] = {}
    query_cache: dict[str, list[str]] = {}
    paths = openapi.get("paths", {})
    for template in sorted(paths):
        ops = paths[template]
        if not isinstance(ops, Mapping) or "get" not in ops:
            continue
        if any(fnmatch.fnmatchcase(template, p) for p in server.skip_paths):
            result.skipped[template] = "skip_paths"
            continue
        names = _PARAM.findall(template)
        choices: list[list[str]] = []
        missing = []
        for name in names:
            values = _param_values(name, server, http, cache)
            if not values:
                missing.append(name)
            choices.append(values)
        if missing:
            result.skipped[template] = f"no value for {', '.join(missing)}"
            continue
        queries = [
            f"{name}={quote(value, safe='')}"
            for name in _query_names(ops["get"])
            for value in _param_values(name, server, http, query_cache, server.query_params)
        ]
        for combo in itertools.product(*choices):
            base = template
            for name, value in zip(names, combo, strict=True):
                base = base.replace("{" + name + "}", value, 1)
            for url in [base, *(f"{base}?{q}" for q in queries)]:
                status, doc = http.get(url)
                if status != 200 or doc is None:
                    if url == base:
                        reason = f"status {status}" if status != 200 else "not JSON"
                        result.skipped.setdefault(template, reason)
                    continue
                result.skipped.pop(template, None)
                if template not in result.visited:
                    result.visited.append(template)
                collect(doc, template, config, result)
    return result


def _query_names(op: Any) -> list[str]:
    """OpenAPI 작업이 선언한 질의 변수 이름."""
    if not isinstance(op, Mapping):
        return []
    return [
        str(p["name"])
        for p in op.get("parameters") or []
        if isinstance(p, Mapping) and p.get("in") == "query" and isinstance(p.get("name"), str)
    ]


@contextmanager
def _environ(values: Mapping[str, str]) -> Iterator[None]:
    old = {k: os.environ.get(k) for k in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def with_tmp(value: Any, tmp: str) -> Any:
    """값 안 문자열의 ``{tmp}``를 바꾼 복사본(사전·목록은 따라 들어감).

    >>> with_tmp({"folder": "{tmp}/p", "n": [1, "{tmp}"]}, "/t")
    {'folder': '/t/p', 'n': [1, '/t']}
    """
    if isinstance(value, str):
        return value.replace("{tmp}", tmp)
    if isinstance(value, Mapping):
        return {k: with_tmp(v, tmp) for k, v in value.items()}
    if isinstance(value, list):
        return [with_tmp(v, tmp) for v in value]
    return value


@contextmanager
def assembled_server(server: ServerConfig) -> Iterator[tuple[HttpPort, Mapping[str, Any]]]:
    """설치된 모듈 전부로 조립한 서버(빈 작업 공간, 임시 폴더)와 그 OpenAPI 문서.

    서버 환경은 ``server.env``(값의 ``{tmp}`` = 임시 폴더, 그 폴더는 만들어 둔다). ``server.dirs``
    폴더도 만들고, 씨앗 본문 문자열의 ``{tmp}``도 임시 폴더로 바꾼다. 문자열 본문은
    ``text/plain``으로 보낸다. 비밀 값은 넘기지 않는다. 외부 호출을 하는 경로는 ``skip_paths``로
    뺀다(실행 백엔드는 fake 씨앗만 쓴다).
    """
    from agent_console_server.testing import make_settings
    from agent_console_server.testing import server as start_server

    with tempfile.TemporaryDirectory(prefix="ac-i18n-check-") as tmp:
        base = Path(tmp)
        env: dict[str, str] = {}
        for key, value in server.env.items():
            resolved = value.replace("{tmp}", tmp)
            if "{tmp}" in value:
                Path(resolved).mkdir(parents=True, exist_ok=True)
            env[key] = resolved
        for folder in server.dirs:
            Path(folder.replace("{tmp}", tmp)).mkdir(parents=True, exist_ok=True)
        with _environ(env):
            settings = make_settings(base, options=server.options)
            with start_server(settings, environ=env) as client:

                def get(path: str) -> tuple[int, Any | None]:
                    response = client.get(path)
                    kind = response.headers.get("content-type", "")
                    if "json" not in kind:
                        return response.status_code, None
                    return response.status_code, response.json()

                def send(method: str, path: str, body: Any, headers: Mapping[str, str]) -> int:
                    body = with_tmp(body, tmp)
                    if isinstance(body, str):
                        plain = {**headers, "content-type": "text/plain; charset=utf-8"}
                        return client.request(
                            method, path, content=body.encode("utf-8"), headers=plain
                        ).status_code
                    return client.request(
                        method, path, json=body, headers=dict(headers)
                    ).status_code

                status, openapi = get(server.openapi)
                if status != 200 or not isinstance(openapi, Mapping):
                    raise RuntimeError(f"cannot read OpenAPI document {server.openapi}: {status}")
                yield HttpPort(get, send), openapi


def crawl_server(config: Config) -> CrawlResult:
    """조립 서버를 띄워 훑고 닫는다."""
    with assembled_server(config.server) as (http, openapi):
        return crawl(openapi, http, config)


__all__ = [
    "CrawlResult",
    "GetFn",
    "HttpPort",
    "IssueSeen",
    "SendFn",
    "assembled_server",
    "collect",
    "crawl",
    "crawl_server",
    "select",
    "with_tmp",
]
