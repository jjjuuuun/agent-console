"""값이 섞인 칸의 원문 틀 + 값(``text_templates``).

S1이 틀을 원문으로 보고 덮인 칸 값을 빼며, 뽑기가 틀을 더한다(가짜 패키지 + 가짜 서버 훑기).
"""

from __future__ import annotations

from typing import Any

from i18n_crawl import CrawlResult, collect, expand_text_templates
from i18n_testkit import RESPONSES, Repo, fake_crawl
from i18n_tool import analyze, main

GAMMA_PY = '''\
"""감마 패키지."""

DETAIL = "자격 위치: {path}"
STATE = "있음"
NOTE = "비밀 '{name}': {state}"


def status(path: str) -> dict[str, object]:
    return {"detail": DETAIL.format(path=path)}
'''

TEMPLATED: dict[str, Any] = {
    "detail": "자격 위치: .state",
    "checks": [{"title": "고정 제목", "note": "비밀 'k': 있음"}],
    "text_templates": {
        "/detail": [{"template": "자격 위치: {path}", "params": {"path": ".state"}}],
        "/checks/0/note": [
            {
                "template": "비밀 '{name}': {state}",
                "params": {"name": "k", "state": {"template": "있음"}},
            }
        ],
    },
}


def _responses() -> dict[str, Any]:
    openapi = {"paths": {**RESPONSES["/openapi.json"]["paths"], "/status": {"get": {}}}}
    return {**RESPONSES, "/openapi.json": openapi, "/status": TEMPLATED}


def _repo(repo: Repo) -> Repo:
    repo.package("gamma", "agent-console-gamma", {"gamma": GAMMA_PY}, registered=True)
    return repo


def test_expand_replaces_covered_fields_with_templates() -> None:
    out = expand_text_templates(TEMPLATED, "text_templates")
    assert out["detail"] is None
    assert out["checks"][0] == {"title": "고정 제목", "note": None}
    assert out["text_templates"] == ["자격 위치: {path}", "비밀 '{name}': {state}", "있음"]
    assert TEMPLATED["detail"] == "자격 위치: .state"  # 원본은 그대로
    plain = {"detail": "x"}
    assert expand_text_templates(plain, "text_templates") is plain
    assert expand_text_templates({"text_templates": {}}, "text_templates") == {"text_templates": {}}


def test_collect_reads_templates_not_filled_values(repo: Repo) -> None:
    result = CrawlResult()
    collect({"items": [TEMPLATED]}, "/status", repo.config(), result)
    assert set(result.texts) == {"고정 제목", "자격 위치: {path}", "비밀 '{name}': {state}", "있음"}


def test_analyze_asks_for_the_template_and_reports_no_dynamic_text(repo: Repo) -> None:
    _repo(repo)
    result = analyze(repo.root, repo.config(), crawl_fn=fake_crawl(_responses()))
    found = {(f.rule, f.key, f.package) for f in result.findings}
    assert ("missing_text", "자격 위치: {path}", "gamma") in found
    assert ("missing_text", "있음", "gamma") in found
    assert not any("자격 위치: .state" in key or "'k'" in key for _rule, key, _pkg in found)


def test_extract_adds_templates_as_text_keys(repo: Repo) -> None:
    _repo(repo)
    argv = ["--root", str(repo.root), "--config", str(repo.config_path)]
    assert main([*argv, "extract", "--lang", "en"], crawl_fn=fake_crawl(_responses())) == 0
    text = repo.catalog("gamma", "gamma", "en")["text"]
    assert {"자격 위치: {path}", "비밀 '{name}': {state}", "있음"} <= set(text)
