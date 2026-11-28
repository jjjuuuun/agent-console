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


# ---------------------------------------------------------------- 로그 출처 글자(I.14)
# 영어 화면에 파서가 만든 한글 이벤트 제목이 남았는데 ``--strict``가 0이었다. 크롤 서버에는 세션
# 기록이 없어 이벤트 응답이 비고, 분류기 기본 설정의 제목·요약 틀은 스키마 ``default``(데이터)이며,
# 코드가 정한 제목은 소유자 찾기에만 쓰였기 때문이다.

EVENTS_PY = """\
from x import LogEventDraft, TextTemplate


def make(failed, kind, value, fields):
    a = LogEventDraft(title="빈 행", summary=None)
    b = LogEventDraft(title="실패한 행" if failed else "성공한 행")
    c = LogEventDraft(title=f"값 섞인 제목 {kind}")
    d = TextTemplate(template="틀 제목 · {kind}", params={"kind": kind})
    fields.update(title=value or "이름 없는 행")
    e = {"title": "사전 제목", "other": "안 보는 글자"}
    f = LogEventDraft(category="안 보는 키워드")
    return a, b, c, d, e, f
"""

RULES_JSON: dict[str, Any] = {
    "rules": [
        {"title": "고정 제목"},
        {"title": "hook 요약 · {/hookCount}개"},
        {"title": "{/output/0/type} 블록 {/output|count}개"},
        {"title": "{/a/name}와 {/b/name}"},
        {"title": "{/only}"},
    ]
}


def _events_repo(repo: Repo) -> None:
    repo.package("gamma", "agent-console-gamma", {"gamma": EVENTS_PY}, registered=True)
    data = repo.root / "packages/beta/src/beta/rules.json"
    data.write_text(json.dumps(RULES_JSON, ensure_ascii=False), "utf-8")
    repo.write_config(
        {
            **CONFIG,
            "static": {
                "data": [
                    {
                        "files": ["packages/beta/src/beta/rules.json"],
                        "select": ["/rules/*/title"],
                        "pointer_slots": True,
                    }
                ],
                "python": [
                    {
                        "files": ["packages/gamma/src/**/*.py"],
                        "calls": ["LogEventDraft", "TextTemplate", "update"],
                        "keywords": ["title", "template"],
                        "dict_keys": ["title"],
                    }
                ],
            },
        }
    )


def test_pointer_key_matches_the_classifier_naming() -> None:
    from i18n_static import pointer_key

    assert pointer_key("hook 실행 · {/data/hookName}") == "hook 실행 · {hookName}"
    assert pointer_key("{/output/0/type} 블록 {/output|count}개") == "{type} 블록 {output_count}개"
    assert pointer_key("목록 {/0} {x}") == "목록 {v0} {{x}}"
    assert pointer_key("{/a/name}와 {/b/name}") == "{/a/name}와 {/b/name}"  # 이름 겹침
    assert pointer_key("고정") == "고정"


def test_static_python_and_pointer_slots_collect_event_texts(repo: Repo) -> None:
    _events_repo(repo)
    out = collect_static(repo.root, repo.config())
    texts = out.result.texts
    assert {
        "빈 행",
        "실패한 행",
        "성공한 행",
        "값 섞인 제목 {…}",
        "틀 제목 · {kind}",
        "이름 없는 행",
        "사전 제목",
    } <= set(texts)
    assert "안 보는 글자" not in texts
    assert "안 보는 키워드" not in texts
    assert texts["빈 행"][0].startswith("python:packages/gamma/src/gamma/__init__.py:")
    assert "packages/gamma/src/gamma/__init__.py" in out.python_files
    assert {"고정 제목", "hook 요약 · {hookCount}개", "{type} 블록 {output_count}개"} <= set(texts)
    assert "{/a/name}와 {/b/name}" in texts  # 바꿀 수 없는 틀은 그대로(빠진 문구로 보고)
    assert "hook 요약 · {/hookCount}개" not in texts


def test_static_event_texts_are_findings(repo: Repo) -> None:
    _events_repo(repo)
    result = analyze(repo.root, repo.config(), crawl_fn=None)
    rules = {(f.rule, f.key) for f in result.findings}
    assert ("missing_text", "빈 행") in rules
    assert ("missing_text", "틀 제목 · {kind}") in rules
    assert ("dynamic_text", "값 섞인 제목 {…}") in rules  # f-string → 틀 + 값으로 바꾸라는 뜻
    assert ("missing_text", "고정 제목") in rules
    # 바꾼 틀은 소스 글자가 아니라 소유자를 모른다(뽑기 대상 아님 — 묶음에 손으로 넣는다)
    assert ("unowned_text", "hook 요약 · {hookCount}개") in rules


def test_static_python_config_errors(repo: Repo) -> None:
    with pytest.raises(I18nToolError, match="needs calls"):
        parse_config({**CONFIG, "static": {"python": [{"files": ["x"], "calls": ["A"]}]}})
    with pytest.raises(I18nToolError, match="pointer_slots"):
        parse_config({**CONFIG, "static": {"data": [{"files": ["x"], "pointer_slots": "yes"}]}})
    _events_repo(repo)
    config = repo.config()
    for path in (repo.root / "packages/gamma/src").rglob("*.py"):
        path.unlink()
    with pytest.raises(I18nToolError, match=r"static\.python: no file matches"):
        collect_static(repo.root, config)


def test_repository_static_sources_cover_log_event_texts() -> None:
    """I.14: 분류기·출처의 이벤트 제목·요약 틀이 저장소 설정으로 잡힌다."""
    repo_root = Path(__file__).resolve().parents[3]
    config = load_config(DEFAULT_CONFIG)
    if not (repo_root / config.static.schemas[0].document).is_file():
        pytest.skip("contracts schema document is not in this checkout")
    texts = collect_static(repo_root, config).result.texts
    for text in (
        "내부 추론",
        "내부 추론 본문 생략",
        "위임 작업 수신",
        "서브에이전트 결과 (오류)",
        "서브에이전트 위임 · {value}",
        "로그 형식 해석 실패",
        "hook 요약 · {hookCount}개",
        "hook 실행 · {hookName}",
        "MCP 진행 · {serverName}/{toolName} · {status}",
        "{label} 시작",
    ):
        assert text in texts, text
