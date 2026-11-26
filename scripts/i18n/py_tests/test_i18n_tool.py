"""i18n 검사·뽑기 도구 테스트(가짜 패키지 두 개 + 가짜 서버 훑기)."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
from i18n_common import (
    DEFAULT_CONFIG,
    I18nToolError,
    discover_packages,
    load_config,
    parse_config,
)
from i18n_crawl import CrawlResult, collect, crawl, select
from i18n_scan import scan_packages
from i18n_testkit import CONFIG, RESPONSES, Repo, fake_crawl, fake_http
from i18n_tool import analyze, main, register_catalog


def _rules(repo: Repo) -> set[tuple[str, str, str | None, str | None]]:
    result = analyze(repo.root, repo.config(), crawl_fn=fake_crawl())
    return {(f.rule, f.key, f.package, f.language) for f in result.findings}


# ---------------------------------------------------------------- 설정


def test_repository_config_parses() -> None:
    config = load_config(DEFAULT_CONFIG)
    assert config.source_language in config.languages
    assert config.is_source_text("한국어")
    assert not config.is_source_text("English only")
    assert config.is_code("logs.source_failed")
    assert not config.is_code("i18n.missing_key")


def test_config_rejects_unknown_rule_and_severity() -> None:
    with pytest.raises(I18nToolError, match="unknown rules"):
        parse_config({**CONFIG, "severity": {"no_such_rule": "error"}})
    with pytest.raises(I18nToolError, match="must be one of"):
        parse_config({**CONFIG, "severity": {"missing_text": "fatal"}})


# ---------------------------------------------------------------- 소스 훑기


def test_scan_finds_texts_templates_and_codes(repo: Repo) -> None:
    config = repo.config()
    scan = scan_packages(discover_packages(repo.root, config.targets), config)
    # 독스트링은 cleandoc한 꼴도(Pydantic 설명), 데이터 파일 문자열도 원문이다.
    assert "alpha" in scan.owners("알파 설정\n\n여러 줄 설명.")
    assert "beta" in scan.owners("베타 이름")
    assert "beta" in scan.owners("기본 범주")
    # testing 모듈은 제외 glob으로 빠진다.
    assert not scan.owners("시험 전용 문구")
    # f-string 틀
    template = scan.template_for("파일 12개")
    assert template is not None
    assert template.package == "alpha"
    codes = {(s.code, s.package, s.definition) for s in scan.codes}
    assert ("alpha.broken", "alpha", True) in codes  # *Codes 클래스 정의
    assert ("alpha.broken", "alpha", False) in codes  # code=AlphaCodes.BROKEN
    assert ("beta.failed", "beta", False) in codes  # {"code": ..., "message": ...}
    assert ("beta.local", "beta", False) in codes  # code=모듈 상수
    details = {s.code: s.details for s in scan.codes if not s.definition}
    assert details["alpha.broken"] == frozenset({"name"})
    assert details["beta.failed"] == frozenset({"path"})
    assert details["beta.local"] is None


# ---------------------------------------------------------------- 서버 훑기


def test_select_paths() -> None:
    assert select({"profiles": [{"id": "a"}, {"id": "b"}]}, "/profiles/*/id") == ["a", "b"]
    assert select([{"id": 1}], "/*/id") == [1]
    assert select({"a": [10, 20]}, "/a/1") == [20]
    assert select({"a": 1}, "/b") == []


def test_crawl_seeds_params_skips_and_issue_messages(repo: Repo) -> None:
    config = repo.config()
    sent: list[tuple[str, str, object]] = []
    result = crawl(RESPONSES["/openapi.json"], fake_http(sent=sent), config)
    assert sent == [("POST", "/things", {"id": "t1"})]
    assert set(result.visited) == {"/schema", "/things", "/things/{thing_id}"}
    assert result.skipped["/missing/{other_id}"] == "no value for other_id"
    assert result.skipped["/secret/{thing_id}"] == "skip_paths"
    assert "/write-only" not in result.skipped
    texts = set(result.texts)
    assert {"베타 이름", "파일 3개", "어디에도 없음"} <= texts
    assert "주석 한국어" not in texts  # skip_keys
    assert "서버 원문 메시지" not in texts  # 이슈 message는 S2
    assert "무시할 문구" not in texts  # texts.exclude
    assert {(i.code, i.details) for i in result.issues} == {
        ("beta.failed", frozenset({"path"})),
        ("runtime.only", None),
    }


def test_collect_records_route_once_per_text(repo: Repo) -> None:
    result = CrawlResult()
    collect(["같은 문구", {"x": "같은 문구"}], "/r", repo.config(), result)
    assert result.texts == {"같은 문구": ["/r"]}


# ---------------------------------------------------------------- 검사 규칙


def test_analyze_reports_missing_dynamic_unowned_and_codes(repo: Repo) -> None:
    rules = _rules(repo)
    assert ("missing_text", "베타 이름", "beta", "en") in rules
    assert ("dynamic_text", "파일 3개", "alpha", None) in rules
    assert ("unowned_text", "어디에도 없음", None, None) in rules
    # 원문 언어(ko)의 text는 보지 않고, 번역된 문구는 나오지 않는다.
    assert not any(r[0] == "missing_text" and r[3] == "ko" for r in rules)
    assert not any(r[1].startswith("알파 설정") for r in rules)
    for lang in ("ko", "en"):
        assert ("missing_code", "beta.failed", "beta", lang) in rules
        assert ("missing_code", "beta.local", "beta", lang) in rules
        assert ("missing_code", "alpha.broken", "alpha", lang) not in rules
    assert ("unowned_code", "runtime.only", None, None) in rules
    assert not any(r[0] in {"placeholder_mismatch", "unknown_placeholder"} for r in rules)


def test_placeholders_must_match_between_languages_and_details(repo: Repo) -> None:
    folder = repo.root / "packages/alpha/src/alpha/locales"
    (folder / "ko.json").write_text(
        json.dumps({"codes": {"alpha.broken": "{other} 깨짐"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    rules = _rules(repo)
    assert ("placeholder_mismatch", "alpha.broken", "alpha", "en") in rules
    assert ("unknown_placeholder", "alpha.broken", "alpha", "ko") in rules


def test_unregistered_and_invalid_catalogs(repo: Repo) -> None:
    folder = repo.root / "packages/beta/src/beta/locales"
    folder.mkdir()
    (folder / "en.json").write_text("{not json", encoding="utf-8")
    rules = _rules(repo)
    assert ("catalog_unregistered", "beta", "beta", None) in rules
    assert any(r[0] == "catalog_invalid" and r[2] == "beta" for r in rules)


def test_stale_code_in_catalog(repo: Repo) -> None:
    path = repo.root / "packages/alpha/src/alpha/locales/en.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["codes"]["alpha.gone"] = "Gone"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert ("stale_code", "alpha.gone", "alpha", "en") in _rules(repo)


# ---------------------------------------------------------------- 명령


def _main(repo: Repo, *args: str) -> int:
    argv = ["--root", str(repo.root), "--config", str(repo.config_path), *args]
    return main(argv, crawl_fn=fake_crawl())


def test_check_warning_mode_strict_and_package_filter(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(repo, "check") == 0  # 빠진 문구·코드는 경고
    out = capsys.readouterr().out
    assert "missing_text[en]: 1" in out
    assert "missing_code[ko]: 2" in out
    assert _main(repo, "check", "--strict") == 1
    capsys.readouterr()
    # alpha만 보면 dynamic_text 하나뿐이다.
    assert _main(repo, "check", "--package", "alpha", "--list") == 0
    listed = [line for line in capsys.readouterr().out.splitlines() if line.startswith("warning")]
    assert len(listed) == 1
    assert "dynamic_text" in listed[0]
    assert _main(repo, "check", "--package", "nope") == 2


def test_check_fails_on_error_rules(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    (repo.root / "packages/beta/src/beta/locales").mkdir()
    (repo.root / "packages/beta/src/beta/locales/en.json").write_text("{}", encoding="utf-8")
    assert _main(repo, "check", "--no-server") == 1
    assert "catalog_unregistered" in capsys.readouterr().out


def test_extract_adds_empty_values_registers_and_keeps_existing(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(repo, "extract", "--lang", "en", "--dry-run") == 0
    assert not (repo.root / "packages/beta/src/beta/locales").exists()
    assert "would add 3" in capsys.readouterr().out

    assert _main(repo, "extract", "--lang", "en") == 0
    out = capsys.readouterr().out
    assert "added 3 empty entries for 'en'" in out
    assert "not extracted: dynamic_text 1" in out
    assert repo.catalog("beta", "beta", "en") == {
        "text": {"베타 이름": ""},
        "codes": {"beta.failed": "", "beta.local": ""},
    }
    pyproject = tomllib.loads(
        (repo.root / "packages/beta/pyproject.toml").read_text(encoding="utf-8")
    )
    assert pyproject["project"]["entry-points"]["agent_console.message_catalogs"] == {
        "beta": "beta"
    }
    # 원문 언어(ko)는 codes만 더한다. 이미 있는 alpha 값은 그대로다.
    assert _main(repo, "extract", "--lang", "ko") == 0
    assert repo.catalog("beta", "beta", "ko") == {"codes": {"beta.failed": "", "beta.local": ""}}
    assert repo.catalog("alpha", "alpha", "ko") == {"codes": {"alpha.broken": "{name} 깨짐"}}
    # 빈 값은 "아직 번역 안 함"으로 보인다.
    rules = _rules(repo)
    assert ("untranslated_text", "베타 이름", "beta", "en") in rules
    assert ("untranslated_code", "beta.failed", "beta", "ko") in rules
    assert not any(r[0] in {"missing_text", "missing_code", "catalog_unregistered"} for r in rules)
    # 다시 뽑아도 더할 것이 없다.
    capsys.readouterr()
    assert _main(repo, "extract", "--lang", "en") == 0
    assert "added 0 empty entries" in capsys.readouterr().out


def test_extract_new_language_and_package_filter(repo: Repo) -> None:
    assert _main(repo, "extract", "--lang", "ja", "--package", "agent-console-alpha") == 0
    # 새 언어는 원문 언어가 아니므로 text도 더한다.
    assert repo.catalog("alpha", "alpha", "ja") == {
        "text": {"알파 설정\n\n여러 줄 설명.": ""},
        "codes": {"alpha.broken": ""},
    }
    assert not (repo.root / "packages/beta/src/beta/locales").exists()


def test_register_catalog_places_table_and_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text(
        '[project]\nname = "x"\n\n[project.entry-points."agent_console.server_modules"]\n'
        'mod-x = "x.module:module"\n\n[dependency-groups]\ndev = []\n\n[tool.ruff]\n',
        encoding="utf-8",
    )
    assert register_catalog(path, "ac-x", "x") is True
    text = path.read_text(encoding="utf-8")
    assert text.index("agent_console.message_catalogs") < text.index("[dependency-groups]")
    assert register_catalog(path, "ac-x", "x") is False
    assert path.read_text(encoding="utf-8") == text
    # 표가 이미 있으면 그 표에 줄을 더한다.
    assert register_catalog(path, "ac-y", "y") is True
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    assert data["project"]["entry-points"]["agent_console.message_catalogs"] == {
        "ac-x": "x",
        "ac-y": "y",
    }
