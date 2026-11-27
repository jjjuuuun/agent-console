"""S1 보완 테스트: 정적 출처(계약 스키마·데이터 파일), x-ui 예시, 질의 변수·씨앗 머리글.

I.13에서 영어 화면에 남은 한글 약 170개를 ``--strict``가 0으로 놓쳤다. 서버 응답만 훑어 웹이
계약 스키마(설정·스펙·위키 폼)에서 그리는 설명·제목, x-ui ``example``, 데이터를 만들어야만 보이는
값(스펙 작업 문법·프로젝트 가져오기 출처·버전 메시지)을 보지 못했기 때문이다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from i18n_common import DEFAULT_CONFIG, I18nToolError, load_config, parse_config
from i18n_crawl import CrawlResult, HttpPort, collect, crawl, with_tmp
from i18n_static import collect_static
from i18n_testkit import CONFIG, Repo, fake_crawl
from i18n_tool import analyze, main

SCHEMA_DOC: dict[str, Any] = {
    "$defs": {
        "Settings": {
            "title": "감마 설정",
            "properties": {
                "default": {"$ref": "#/$defs/Inner", "description": "기본이라는 이름의 속성"},
                "count": {
                    "type": "integer",
                    "description": "횟수 설명",
                    "default": 3,
                    "x-ui": {"unit": "번", "example": "예시 글자", "when": "바꿀 때"},
                },
                "mode": {"enum": ["a", "b"], "examples": ["데이터 예시"]},
            },
        },
        "Inner": {"description": "안쪽 설명", "x-ui": {"example": 5}},
        "Unused": {"description": "쓰지 않는 모델"},
    }
}

GAMMA_PY = '''\
"""감마 계약."""


class Settings:
    """감마 설정"""

    TEXTS = ("기본이라는 이름의 속성", "횟수 설명", "번", "예시 글자", "바꿀 때", "안쪽 설명")
'''


def _static_repo(repo: Repo, *, models: list[str] | None = None) -> None:
    repo.package("gamma", "agent-console-gamma", {"gamma": GAMMA_PY}, registered=True)
    (repo.root / "schema.json").write_text(json.dumps(SCHEMA_DOC, ensure_ascii=False), "utf-8")
    web = repo.root / "web" / "src"
    web.mkdir(parents=True)
    (web / "form.tsx").write_text('const s = getContractSchema("Settings");\n', "utf-8")
    (web / "form.test.tsx").write_text('getContractSchema("Unused");\n', "utf-8")
    (web / "other.ts").write_text("getContractSchema('NoSuchModel');\n", "utf-8")
    data = repo.root / "packages/beta/src/beta/syntax.yaml"
    data.write_text(
        "task:\n  statuses:\n    - {id: todo, label: 할 일, note: 안 보이는 메모}\n", "utf-8"
    )
    repo.write_config(
        {
            **CONFIG,
            "texts": {
                **CONFIG["texts"],
                "skip_keys": ["$comment", "default", "enum", "examples", "example"],
                "keep_keys_in": {"x-ui": ["example"]},
                "name_maps": ["properties", "$defs"],
            },
            "static": {
                "schemas": [
                    {
                        "document": "schema.json",
                        "models": models or [],
                        "discover": {
                            "files": ["web/src/**/*.tsx", "web/src/**/*.ts"],
                            "exclude": ["**/*.test.tsx"],
                            "pattern": "getContractSchema\\(\\s*[\"'](\\w+)[\"']",
                        },
                    }
                ],
                "data": [
                    {
                        "files": ["packages/beta/src/beta/syntax.yaml"],
                        "select": ["/*/statuses/*/label"],
                    }
                ],
            },
        }
    )


# ---------------------------------------------------------------- collect


def test_collect_keeps_x_ui_example_and_walks_property_names(repo: Repo) -> None:
    config = parse_config(
        {
            **CONFIG,
            "texts": {
                "skip_keys": ["default", "example", "examples"],
                "keep_keys_in": {"x-ui": ["example"]},
                "name_maps": ["properties"],
            },
        }
    )
    result = CrawlResult()
    doc = {
        "properties": {"default": {"title": "기본 속성 제목"}},
        "x-ui": {"example": "화면 예시"},
        "example": "응답 예시 데이터",
        "default": "기본값 데이터",
        "examples": ["예시 데이터"],
        "nested": {"x-ui": {"example": {"값": "객체 예시"}}},
    }
    collect(doc, "/r", config, result)
    assert set(result.texts) == {"기본 속성 제목", "화면 예시"}


def test_config_rejects_discover_pattern_without_group() -> None:
    with pytest.raises(I18nToolError, match="needs a group"):
        parse_config(
            {
                **CONFIG,
                "static": {
                    "schemas": [{"document": "x.json", "discover": {"files": [], "pattern": "x"}}]
                },
            }
        )


# ---------------------------------------------------------------- 정적 출처


def test_static_schema_follows_refs_and_discovers_models(repo: Repo) -> None:
    _static_repo(repo)
    out = collect_static(repo.root, repo.config())
    assert out.models == ["Settings", "Inner"]  # 테스트 파일의 Unused는 빠지고 $ref는 따라감
    assert out.unknown_models == ["NoSuchModel"]
    texts = out.result.texts
    assert {
        "감마 설정",
        "기본이라는 이름의 속성",
        "횟수 설명",
        "번",
        "예시 글자",
        "바꿀 때",
    } <= set(texts)
    assert texts["안쪽 설명"] == ["schema:Settings"]
    assert "데이터 예시" not in texts  # examples는 데이터
    assert "쓰지 않는 모델" not in texts
    # 데이터 파일은 select 경로만
    assert texts["할 일"] == ["data:packages/beta/src/beta/syntax.yaml"]
    assert "안 보이는 메모" not in texts


def test_static_texts_are_checked_without_server(repo: Repo) -> None:
    _static_repo(repo)
    result = analyze(repo.root, repo.config(), crawl_fn=None)
    rules = {(f.rule, f.key, f.package) for f in result.findings}
    assert ("missing_text", "횟수 설명", "gamma") in rules
    assert ("missing_text", "예시 글자", "gamma") in rules
    assert ("missing_text", "할 일", "beta") in rules
    where = {f.key: f.where for f in result.findings}
    assert where["안쪽 설명"].startswith("schema:Settings; packages/gamma/")


def test_static_sources_reported_and_extracted(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    _static_repo(repo)
    argv = ["--root", str(repo.root), "--config", str(repo.config_path)]
    assert main([*argv, "check", "--no-server"], crawl_fn=fake_crawl()) == 0
    out = capsys.readouterr().out
    assert "S1 static sources: 2 schema models, 1 data files" in out
    assert "models not in the schema document: NoSuchModel" in out
    assert main([*argv, "extract", "--lang", "en", "--no-server"], crawl_fn=fake_crawl()) == 0
    assert repo.catalog("gamma", "gamma", "en")["text"]["번"] == ""


def test_static_missing_document_is_a_config_error(repo: Repo) -> None:
    _static_repo(repo)
    (repo.root / "schema.json").unlink()
    with pytest.raises(I18nToolError, match=r"cannot read schema\.json"):
        collect_static(repo.root, repo.config())


# ---------------------------------------------------------------- 서버 훑기 보완


def test_crawl_query_params_and_if_match_seed(repo: Repo) -> None:
    config = parse_config(
        {
            **CONFIG,
            "server": {
                "seeds": [
                    {
                        "method": "PUT",
                        "path": "/doc/content",
                        "body": "본문",
                        "if_match": {"from": "/doc/versions", "select": "/0/version_hash"},
                    }
                ],
                "query_params": {"project": {"values": ["p1"]}},
            },
        }
    )
    openapi = {
        "paths": {
            "/sources": {"get": {"parameters": [{"name": "project", "in": "query"}]}},
            "/plain": {"get": {}},
        }
    }
    responses: dict[str, Any] = {
        "/doc/versions": [{"version_hash": "v1"}],
        "/sources": [{"name": "기본 출처"}],
        "/sources?project=p1": [{"name": "프로젝트 출처"}],
        "/plain": {"x": "평범"},
        "/plain?project=p1": {"x": "읽으면 안 됨"},
    }
    sent: list[tuple[str, str, Any, dict[str, str]]] = []

    def get(path: str) -> tuple[int, Any | None]:
        return (200, responses[path]) if path in responses else (404, None)

    def send(method: str, path: str, body: Any, headers: Any) -> int:
        sent.append((method, path, body, dict(headers)))
        return 200

    result = crawl(openapi, HttpPort(get, send), config)
    assert sent == [("PUT", "/doc/content", "본문", {"If-Match": '"v1"'})]
    assert set(result.texts) == {"기본 출처", "프로젝트 출처", "평범"}


def test_with_tmp_replaces_nested_strings() -> None:
    assert with_tmp({"a": ["{tmp}/x", 1], "b": "{tmp}"}, "/t") == {"a": ["/t/x", 1], "b": "/t"}


# ---------------------------------------------------------------- 저장소 설정 회귀


def test_repository_static_sources_cover_reported_texts() -> None:
    """I.13에서 놓친 종류(계약 스키마 제목·x-ui 단위·데이터 값)가 저장소 설정으로 잡힌다."""
    repo_root = Path(__file__).resolve().parents[3]
    config = load_config(DEFAULT_CONFIG)
    document = repo_root / config.static.schemas[0].document
    if not document.is_file():
        pytest.skip("contracts schema document is not in this checkout")
    out = collect_static(repo_root, config)
    for model in (
        "SpecDefinition",
        "WikiDefinition",
        "UsageIndicatorSettings",
        "WorkspaceSettings",
    ):
        assert model in out.models
    for text in (
        "문서 상태",
        "작업 문법",
        "링크 규칙",
        "사용량 표시기 보이기",
        "브라우저 알림",
        "번",
        "할 일",
    ):
        assert text in out.result.texts, text
