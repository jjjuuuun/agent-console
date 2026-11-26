"""시험용 임시 저장소: 가짜 패키지 두 개와 설정, 가짜 서버 훑기."""

from __future__ import annotations

import json
import textwrap
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from i18n_common import Config, parse_config
from i18n_crawl import CrawlResult, HttpPort, crawl

CONFIG: dict[str, Any] = {
    "targets": ["packages/*"],
    "groups": [{"name": "all", "paths": ["packages/*"]}],
    "source_language": "ko",
    "source_pattern": "[\\uac00-\\ud7a3]",
    "languages": ["ko", "en"],
    "sources": {
        "python": ["src/**/*.py"],
        "data": ["src/**/*.yaml", "src/**/*.json"],
        "exclude": ["src/**/testing.py"],
    },
    "codes": {
        "pattern": "^[a-z][a-z0-9_]*(?:\\.[a-z0-9_]+)*$",
        "class_pattern": "Codes$",
        "exclude": ["i18n\\.missing_key"],
    },
    "texts": {"exclude": ["무시할"], "skip_keys": ["$comment"], "prefer_owners": []},
    "issue": {"code": "code", "message": "message", "details": "details"},
    "severity": {
        "missing_text": "warning",
        "missing_code": "warning",
        "dynamic_text": "warning",
        "unowned_text": "warning",
        "unowned_code": "warning",
    },
    "server": {
        "openapi": "/openapi.json",
        "seeds": [{"method": "POST", "path": "/things", "body": {"id": "t1"}}],
        "params": {"thing_id": {"from": "/things", "select": "/*/id"}},
        "skip_paths": ["/secret/*"],
    },
}

ALPHA_PY = '''\
"""알파 패키지."""

from typing import Final


class AlphaCodes:
    BROKEN: Final = "alpha.broken"
    NOT_A_CODE: Final = 3


class Model:
    """알파 설정

    여러 줄 설명."""


def issue(n: int) -> dict[str, object]:
    make(code=AlphaCodes.BROKEN, details={"name": n})
    return {"title": f"파일 {n}개"}


def make(**kw: object) -> None:
    return None
'''

BETA_PY = '''\
"""베타 패키지."""

LOCAL_CODE = "beta.local"


def fail(p: str) -> dict[str, object]:
    other(code=LOCAL_CODE)
    return {"code": "beta.failed", "message": "실패", "details": {"path": p}}


def other(**kw: object) -> None:
    return None
'''


class Repo:
    """임시 저장소(``packages/alpha``·``packages/beta``)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.config_path = root / "i18n.yaml"
        self.write_config(CONFIG)
        self.package(
            "alpha",
            "agent-console-alpha",
            {"alpha": ALPHA_PY},
            registered=True,
            locales={
                "en": {
                    "text": {"알파 설정\n\n여러 줄 설명.": "Alpha settings"},
                    "codes": {"alpha.broken": "Broken {name}"},
                },
                "ko": {"codes": {"alpha.broken": "{name} 깨짐"}},
            },
        )
        self.package(
            "beta",
            "agent-console-beta",
            {"beta": BETA_PY},
            data={"beta/defaults.yaml": "label: 베타 이름\nnested: [{name: 기본 범주}]\n"},
        )

    def write_config(self, data: Mapping[str, Any]) -> None:
        self.config_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def config(self) -> Config:
        return parse_config(json.loads(self.config_path.read_text(encoding="utf-8")))

    def package(
        self,
        folder: str,
        dist: str,
        modules: Mapping[str, str],
        *,
        registered: bool = False,
        locales: Mapping[str, Any] | None = None,
        data: Mapping[str, str] | None = None,
    ) -> Path:
        root = self.root / "packages" / folder
        (root / "src").mkdir(parents=True)
        pyproject = f'[project]\nname = "{dist}"\nversion = "0.1.0"\n\n'
        if registered:
            import_name = next(iter(modules))
            pyproject += (
                '[project.entry-points."agent_console.message_catalogs"]\n'
                f'{folder} = "{import_name}"\n\n'
            )
        pyproject += '[build-system]\nrequires = ["uv_build"]\n\n[tool.ruff]\nline-length = 100\n'
        (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
        for name, source in modules.items():
            pkg = root / "src" / name
            pkg.mkdir()
            (pkg / "__init__.py").write_text(textwrap.dedent(source), encoding="utf-8")
            (pkg / "testing.py").write_text('X = "시험 전용 문구"\n', encoding="utf-8")
        for rel, text in (data or {}).items():
            path = root / "src" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        for lang, doc in (locales or {}).items():
            path = root / "src" / next(iter(modules)) / "locales" / f"{lang}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return root

    def catalog(self, folder: str, import_name: str, lang: str) -> dict[str, Any]:
        path = self.root / "packages" / folder / "src" / import_name / "locales" / f"{lang}.json"
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data


RESPONSES: dict[str, Any] = {
    "/openapi.json": {
        "paths": {
            "/schema": {"get": {}},
            "/things": {"get": {}, "post": {}},
            "/things/{thing_id}": {"get": {}},
            "/missing/{other_id}": {"get": {}},
            "/secret/{thing_id}": {"get": {}},
            "/write-only": {"post": {}},
        }
    },
    "/schema": {
        "title": "알파 설정\n\n여러 줄 설명.",
        "properties": {"label": {"title": "베타 이름", "$comment": "주석 한국어"}},
        "x-ui": {"when": "파일 3개"},
        "warnings": [
            {"code": "beta.failed", "message": "서버 원문 메시지", "details": {"path": "/a"}},
            {"code": "runtime.only", "message": "응답에만 있는 코드"},
        ],
    },
    "/things": [{"id": "t1"}],
    "/things/t1": {"name": "t1", "note": "어디에도 없음", "skip": "무시할 문구"},
}


def fake_http(
    responses: Mapping[str, Any] = RESPONSES, sent: list[tuple[str, str, Any]] | None = None
) -> HttpPort:
    def get(path: str) -> tuple[int, Any | None]:
        if path in responses:
            return 200, responses[path]
        return 404, {"error": {"code": "not_found"}}

    def send(method: str, path: str, body: Any) -> int:
        if sent is not None:
            sent.append((method, path, body))
        return 201

    return HttpPort(get, send)


def fake_crawl(responses: Mapping[str, Any] = RESPONSES) -> Callable[[Config], CrawlResult]:
    def run(config: Config) -> CrawlResult:
        http = fake_http(responses)
        return crawl(responses["/openapi.json"], http, config)

    return run
