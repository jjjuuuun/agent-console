"""FU.14 2·3: 모르는 `title_sources` 이슈, 가린 본문을 다시 쓰는 쓰기 막기."""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_contracts.wiki import WikiAccessConfig, WikiAuthor, WikiRulesDefinition
from agent_console_wiki import (
    InMemoryWikiHistory,
    WikiIssueCodes,
    WikiRedactedContentError,
    WikiRepository,
    WikiSecretPolicy,
    WikiToolkit,
    check_rules,
    compile_syntax,
    compose_write,
    effective_syntax,
    load_tool_text,
    parse_page,
    redaction_marks,
    wiki_failure,
)
from agent_console_wiki.testing import FakeClock, MemoryWikiPages

SECRET = "sk-abcdefghijklmnop1234"
PAGE = f"# 설정\n\nAPI_KEY={SECRET}\n\n## 기타\n본문\n"
AGENT = WikiAuthor(kind="agent", agent_id="keeper", run_id="r1")


# ---------------------------------------------------------------- 2. title_sources


def test_unknown_title_source_is_a_warning_issue_and_skipped() -> None:
    compiled = compile_syntax(
        effective_syntax(rules=[("r", {"title_sources": ["nope", "file_name", "heading"]})])
    )
    found = [i for i in compiled.issues if i.code == WikiIssueCodes.UNKNOWN_TITLE_SOURCE]
    assert [(i.severity, i.path, i.details["value"]) for i in found] == [
        ("warning", "/title_sources/0", "nope"),
        ("warning", "/title_sources/2", "heading"),
    ]
    assert all("front_matter·first_heading·file_name" in i.message for i in found)
    assert compiled.title_sources == ("file_name",)
    assert compiled.effective.issues == compiled.issues
    assert parse_page("dir/name", "# 머리\n", compiled).title == "name"


def test_known_title_sources_give_no_issue() -> None:
    compiled = compile_syntax(effective_syntax())
    assert not [i for i in compiled.issues if i.code == WikiIssueCodes.UNKNOWN_TITLE_SOURCE]


def test_rules_check_reports_unknown_title_source_under_syntax() -> None:
    rules = WikiRulesDefinition.model_validate(
        {
            "kind": "wiki-rules",
            "id": "r",
            "name": "규칙",
            "syntax": {"title_sources": ["front_matter", "??"]},
        }
    )
    issues = check_rules(rules)
    assert [(i.code, i.path) for i in issues] == [
        (WikiIssueCodes.UNKNOWN_TITLE_SOURCE, "/syntax/title_sources/1")
    ]


# ---------------------------------------------------------------- 3. 가린 본문 다시 쓰기


def _repo(**kw: Any) -> WikiRepository:
    return WikiRepository(
        MemoryWikiPages(),
        wiki_id="notes",
        syntax=compile_syntax(effective_syntax()),
        history=InMemoryWikiHistory(),
        clock=FakeClock(),
        **kw,
    )


def _kit(repo: WikiRepository) -> WikiToolkit:
    access = WikiAccessConfig.model_validate(
        {"wikis": [{"wiki": "notes", "access": ["read", "write"]}]}
    )
    return WikiToolkit({"notes": repo}, access=access, author=AGENT)


def test_redaction_marks_handles_line_count_changes() -> None:
    assert redaction_marks("a\nb\n", "a\nb\n") == ()
    assert redaction_marks("x=1 k=SECRET y\n", "x=1 k=[가림] y\n") == ("[가림]",)
    # 여러 줄 비밀이 한 줄 표시로 바뀜, 전체 가림
    assert redaction_marks("앞\n-----BEGIN\nAAA\n-----END\n뒤\n", "앞\n[가림]\n뒤\n") == ("[가림]",)
    assert redaction_marks("# 제목\n본문\n", "[가림]") == ("[가림]",)


def test_policy_reports_new_lines_only_when_current_had_hidden_values() -> None:
    policy = WikiSecretPolicy()
    shown = policy.redact(PAGE)
    assert SECRET not in shown
    assert policy.reused_redactions(PAGE, shown + "추가\n") == [3]
    # 원문에 가릴 것이 없으면 가린 표시 같은 글자도 그냥 글이다
    plain = "표시 예: [REDACTED]\n"
    assert policy.reused_redactions(plain, plain + "[REDACTED]\n") == []
    # 원문에 이미 있던 표시 수만큼은 괜찮다
    assert policy.reused_redactions(PAGE, PAGE + "다른 줄\n") == []


def test_compose_write_rejects_replace_with_redacted_body_and_keeps_other_modes() -> None:
    repo = _repo()
    repo.write("cfg", PAGE)
    shown = repo.secrets.redact(PAGE)
    with pytest.raises(WikiRedactedContentError) as caught:
        compose_write(repo, "cfg", content=shown.replace("본문", "고친 본문"), mode="replace")
    assert caught.value.code == "wiki.redacted_content"
    assert caught.value.details == {"path": "cfg", "lines": [3]}
    assert SECRET not in str(caught.value)
    assert wiki_failure(caught.value).code == "wiki.redacted_content"
    # 다른 절만 고치기·덧붙이기는 실제 비밀을 그대로 둔다
    plan = compose_write(repo, "cfg", content="고친 본문\n", mode="section", section="기타")
    assert SECRET in plan.content
    assert SECRET in compose_write(repo, "cfg", content="- 메모\n", mode="append").content
    # 가린 절 본문을 그대로 넣으면 막는다
    with pytest.raises(WikiRedactedContentError):
        compose_write(repo, "cfg", content="API_KEY=[REDACTED]\n", mode="section", section="설정")


def test_new_page_with_mark_like_text_is_allowed() -> None:
    repo = _repo()
    plan = compose_write(repo, "new", content="예: API_KEY=[REDACTED]\n", mode="replace")
    assert plan.content.endswith("[REDACTED]\n")


async def test_tool_read_warns_and_write_back_is_rejected_without_changing_page() -> None:
    repo = _repo()
    repo.write("cfg", PAGE)  # 사람 쓰기(기본 설정은 경고만)
    kit = _kit(repo)
    read = await kit.call("read", {"path": "cfg"})
    assert not read.is_error
    assert SECRET not in read.text
    notice = load_tool_text().line("read_redacted", {})
    assert notice
    assert read.text.startswith(notice)
    shown = repo.secrets.redact(PAGE)
    out = await kit.call("write", {"path": "cfg", "content": shown + "덧붙임\n"})
    assert out.is_error
    assert (out.code, out.event.status) == ("wiki.redacted_content", "secret_rejected")
    assert out.text.startswith("[wiki.redacted_content]")
    assert "줄 3" in out.text
    current = repo.current("cfg")
    assert current is not None
    assert current.text == PAGE
    # 기본 설정(에이전트 reject)에서는 비밀이 든 페이지의 다른 절 고치기도 비밀 검사가 막는다
    section = {"path": "cfg", "mode": "section", "section": "기타", "content": "새"}
    blocked = await kit.call("write", section)
    assert blocked.code == "wiki.secret_rejected"
    # 가린 줄을 지우는 것은 가린 표시를 넣는 것이 아니라 막지 않는다(비밀 검사도 통과)
    removed = await kit.call("write", {"path": "cfg", "content": "# 설정\n\n## 기타\n본문\n"})
    assert not removed.is_error
    assert repo.current("cfg") is not None


async def test_section_write_keeps_real_secret_when_agent_mode_is_warn() -> None:
    repo = _repo(secrets=WikiSecretPolicy(modes={"user": "warn", "agent": "warn"}))
    repo.write("cfg", PAGE)
    kit = _kit(repo)
    section = {"path": "cfg", "mode": "section", "section": "기타", "content": "새"}
    ok = await kit.call("write", section)
    assert not ok.is_error
    after = repo.current("cfg")
    assert after is not None
    assert SECRET in after.text
    assert after.text.endswith("## 기타\n새")
    back = await kit.call("write", {"path": "cfg", "content": repo.secrets.redact(after.text)})
    assert back.code == "wiki.redacted_content"


async def test_read_without_hidden_values_has_no_notice() -> None:
    repo = _repo()
    repo.write("plain", "# 평범\n본문\n")
    read = await _kit(repo).call("read", {"path": "plain"})
    assert load_tool_text().line("read_redacted", {}) not in read.text


def test_failing_scanner_does_not_block_writes() -> None:
    class Broken:
        def scan(self, text: str) -> Any:
            raise RuntimeError("x")

        def redact(self, text: str) -> str:
            raise RuntimeError("x")

    policy = WikiSecretPolicy(modes={}, scanner=Broken())
    assert policy.reused_redactions(PAGE, "[REDACTED]") == []
