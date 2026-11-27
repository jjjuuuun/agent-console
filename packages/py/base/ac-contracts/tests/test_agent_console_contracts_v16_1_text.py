"""계약 0.16.1(I.7e, design §I18N.13 I-15·I-16·I-18): 원문 틀 + 값·서버 원문 언어 — 더하기만.

- `common` 2.2.0: `TextTemplate{template, params}`(값 = JSON 스칼라 또는 중첩 틀),
  순수 함수 `render_text_template`·`render_text_parts`.
- `runs` 1.10.0: `text_templates`(`BackendReadiness`·`BackendProbeResult`·`BackendLoginSession`·
  `BackendLogoutResult`).
- `i18n` 1.1.0: `I18nInfo.source_language`.
- `logs` 2.1.0: `LogEvent.text_templates`(값이 섞인 로그 제목).
- 옛 응답(`text_templates`·`source_language` 없음)도 그대로 읽힌다.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_contracts import (
    CONTRACT_VERSIONS,
    BackendLoginSession,
    BackendLogoutResult,
    BackendProbeResult,
    BackendReadiness,
    I18nInfo,
    LogEvent,
    TextTemplate,
    render_text_parts,
    render_text_template,
)
from agent_console_contracts.schema import build_schema


def _t(template: str, **params: Any) -> TextTemplate:
    return TextTemplate(template=template, params=params)


def test_submodule_versions() -> None:
    assert CONTRACT_VERSIONS["common"] == "2.2.0"
    assert CONTRACT_VERSIONS["runs"] == "1.10.0"
    assert CONTRACT_VERSIONS["i18n"] == "1.1.0"
    assert CONTRACT_VERSIONS["logs"] == "2.1.0"


# ---------------------------------------------------------------- render_text_template 표


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        (_t("비밀 '{name}'", name="api_key"), "비밀 'api_key'"),  # 문자열
        (_t("{n}개", n=3), "3개"),  # 정수
        (_t("{seconds}초", seconds=20.0), "20초"),  # 정수인 실수 → 정수(지금 `:g`와 같음)
        (_t("{seconds}초", seconds=1.5), "1.5초"),  # 실수 그대로
        (_t("{minutes}분", minutes=0.5), "0.5분"),
        (_t("{seconds:g}초", seconds=20.0), "20초"),  # 설치자가 쓴 형식 지정자(서버 채우기)
        (_t("{seconds:g}초", seconds=1.5), "1.5초"),
        (_t("{on} {off} {none}", on=True, off=False, none=None), "true false "),
        (_t("{missing} 그대로", other="x"), "{missing} 그대로"),  # 없는 이름
        (_t("{a.b} {0} {}"), "{a.b} {0} {}"),  # 접근식·위치 인자도 그대로
        (_t("{x:d}", x="문자"), "{x:d}"),  # 값과 맞지 않는 형식 지정자 → 자리표시자 그대로
        (_t("{{괄호}} {v}", v=1), "{괄호} 1"),  # str.format 규칙
        (_t("짝 없는 {"), "짝 없는 {"),  # 깨진 틀 → 틀 그대로
        (_t("고정 문장"), "고정 문장"),  # 빈 params
        (_t("{v!r}", v="a"), "'a'"),
    ],
)
def test_render_text_template_table(template: TextTemplate, expected: str) -> None:
    assert render_text_template(template) == expected


def test_render_nested_template_first() -> None:
    state = _t("있음")
    note = _t("비밀 '{name}': {state}", name="k", state=state)
    assert render_text_template(note) == "비밀 'k': 있음"
    deeper = _t("[{inner}]", inner=_t("{x}초", x=2.0))
    assert render_text_template(deeper) == "[2초]"


def test_render_text_parts_joins_with_one_space() -> None:
    parts = [_t("첫 문장."), _t("자격 위치: {path}", path=".state/claude")]
    assert render_text_parts(parts) == "첫 문장. 자격 위치: .state/claude"
    assert render_text_parts([]) == ""


def test_text_template_reads_json_values() -> None:
    raw = {
        "template": "{a} {b} {c} {d} {e}",
        "params": {"a": "s", "b": 2, "c": 2.5, "d": True, "e": {"template": "낱말"}},
    }
    t = TextTemplate.model_validate(raw)
    assert isinstance(t.params["b"], int)
    assert not isinstance(t.params["b"], bool)
    assert t.params["d"] is True
    assert isinstance(t.params["e"], TextTemplate)
    assert render_text_template(t) == "s 2 2.5 true 낱말"
    assert TextTemplate.model_validate({"template": "x"}).params == {}
    dumped = t.model_dump(mode="json")
    assert dumped["params"]["e"] == {"template": "낱말", "params": {}}
    assert TextTemplate.model_validate(dumped) == t


# ---------------------------------------------------------------- 응답 칸 text_templates


def test_responses_carry_text_templates() -> None:
    parts = [_t("{seconds}초 안에 응답이 없었습니다.", seconds=20.0)]
    result = BackendProbeResult(
        backend_id="b",
        ok=False,
        reason="timeout",
        message=render_text_parts(parts),
        finished_at=1.0,
        text_templates={"/message": parts},
    )
    dumped = result.model_dump(mode="json")
    assert dumped["message"] == "20초 안에 응답이 없었습니다."
    assert dumped["text_templates"]["/message"][0]["params"] == {"seconds": 20.0}
    again = BackendProbeResult.model_validate(dumped)
    assert render_text_parts(again.text_templates["/message"]) == again.message


OLD_RESPONSES: list[tuple[type[Any], dict[str, Any]]] = [
    (BackendReadiness, {"backend_id": "b", "state": "x", "tone": "ok", "checked_at": 1.0}),
    (BackendProbeResult, {"backend_id": "b", "ok": True, "finished_at": 1.0}),
    (
        BackendLoginSession,
        {
            "session_id": "s",
            "backend_id": "b",
            "method_id": "m",
            "phase": "starting",
            "started_at": 1.0,
            "expires_at": 2.0,
        },
    ),
    (BackendLogoutResult, {"backend_id": "b", "ok": True, "finished_at": 1.0}),
]


@pytest.mark.parametrize(("model", "old"), OLD_RESPONSES)
def test_old_responses_without_text_templates_read(model: type[Any], old: dict[str, Any]) -> None:
    assert model.model_validate(old).text_templates == {}
    schema = build_schema()["$defs"][model.__name__]
    assert "text_templates" in schema["properties"]
    assert "text_templates" not in schema.get("required", [])


def test_i18n_info_source_language_optional() -> None:
    old = {"languages": [], "default_language": "ko", "fallback_language": "en"}
    assert I18nInfo.model_validate(old).source_language is None
    assert I18nInfo.model_validate({**old, "source_language": "ko"}).source_language == "ko"
    schema = build_schema()["$defs"]["I18nInfo"]
    assert "source_language" not in schema.get("required", [])


def test_text_template_in_common_submodule() -> None:
    modules = build_schema()["x-modules"]
    assert "TextTemplate" in modules["common"]


def test_log_event_text_templates_optional() -> None:
    old = {"uid": "u", "seq": 1, "source": "s", "observed_at": 1.0, "category": "system"}
    assert LogEvent.model_validate(old).text_templates == {}
    parts = [TextTemplate(template="실행 {status}", params={"status": "completed"})]
    event = LogEvent.model_validate(
        {**old, "title": "실행 completed", "text_templates": {"/title": parts}}
    )
    assert render_text_parts(event.text_templates["/title"]) == event.title
    schema = build_schema()["$defs"]["LogEvent"]
    assert "text_templates" not in schema.get("required", [])
