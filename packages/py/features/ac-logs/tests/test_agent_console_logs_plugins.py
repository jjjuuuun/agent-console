"""기본 플러그인 normalized-v1·mapped-jsonl."""

from typing import Any

import pytest

from agent_console_logs import ClassifyContext, RawRecord, SourceRef, effective_config
from agent_console_logs.plugins import (
    MappedJsonlClassifier,
    MappedJsonlSource,
    NormalizedV1Classifier,
    NormalizedV1Source,
)


def _cctx(classifier: Any, config: dict[str, Any] | None = None) -> ClassifyContext:
    cfg = effective_config(classifier.descriptor.config_schema, config)
    return ClassifyContext(source_id="s", ref=SourceRef(ref="f"), config=cfg)


def _rec(data: Any) -> RawRecord:
    return RawRecord(origin="f", offset=0, data=data)


def test_normalized_requires_v1_fields() -> None:
    c = NormalizedV1Classifier()
    for bad in ({"category": "x", "title": "t"}, {"schema_version": 1, "title": "t"}, [1]):
        with pytest.raises(ValueError, match=r"events\.jsonl"):
            c.classify(_rec(bad), _cctx(c))


def test_normalized_maps_fields_and_defaults() -> None:
    c = NormalizedV1Classifier()
    row = {
        "schema_version": 1,
        "id": "ignored",
        "seq": 9,
        "category": "handoff",
        "title": "넘김",
        "thread": "t1",
        "role": "planner",
        "from": ["a"],
        "to": "b",
        "time": "1970-01-01T00:00:05Z",
        "study": {"correlation": {"task": ["x", ""]}},
        "documents": [{"path": "SPEC.md", "kind": "spec"}],
        "usage": {"output_tokens": 4},
    }
    [draft] = c.classify(_rec(row), _cctx(c))
    assert draft.actor == "t1"
    assert draft.from_ == ("a",)
    assert draft.to == ("b",)
    assert draft.time == 5.0
    assert draft.correlation == {"task": ["x"]}
    assert draft.documents[0].kind == "spec"
    assert draft.usage is not None
    assert draft.usage.output_tokens == 4
    assert draft.agent is not None
    assert draft.agent.label == "planner"
    assert "id" not in draft.detail
    assert "seq" not in draft.detail
    [plain] = c.classify(_rec({"schema_version": 1, "category": "x", "title": "t"}), _cctx(c))
    assert plain.actor == "controller"
    [custom] = c.classify(
        _rec({"schema_version": 1, "category": "x", "title": "t"}), _cctx(c, {"default_actor": ""})
    )
    assert custom.actor == ""


def test_mapped_pointer_mapping() -> None:
    c = MappedJsonlClassifier()
    cfg = {
        "fields": {
            "category": "/level",
            "title": "/msg",
            "time": "/ts",
            "session": "/ctx/sid",
            "tags": "/tags",
        },
        "value_maps": {"category": {"ERROR": "error", "INFO": "system"}},
        "correlation": {"request": "/req"},
        "usage": {"output_tokens": "/usage/out"},
    }
    row = {
        "level": "ERROR",
        "msg": "실패",
        "ts": 7,
        "ctx": {"sid": "S"},
        "tags": ["a"],
        "req": "r1",
        "usage": {"out": 5},
    }
    [d] = c.classify(_rec(row), _cctx(c, cfg))
    assert (d.category, d.title, d.time, d.session, d.tags) == ("error", "실패", 7.0, "S", ("a",))
    assert d.correlation == {"request": "r1"}
    assert d.usage is not None
    assert d.usage.output_tokens == 5
    assert d.raw == row
    [other] = c.classify(_rec({"msg": "x"}), _cctx(c, cfg))
    assert other.category == "other"  # defaults.category
    assert c.classify(_rec({"msg": "x"}), _cctx(c, {**cfg, "skip_if_missing": ["/level"]})) == []
    with pytest.raises(ValueError, match="category"):
        c.classify(_rec({}), _cctx(c, {"defaults": {}}))


def test_mapped_schema_rejects_unknown_field() -> None:
    from agent_console_logs import ConfigError

    with pytest.raises(ConfigError):
        effective_config(
            MappedJsonlClassifier.descriptor.config_schema, {"fields": {"bogus": "/x"}}
        )


def test_descriptors_default_disabled() -> None:
    assert NormalizedV1Source.descriptor.default_enabled is False
    assert MappedJsonlSource.descriptor.default_enabled is False
    assert NormalizedV1Source.descriptor.format == "normalized-v1"
