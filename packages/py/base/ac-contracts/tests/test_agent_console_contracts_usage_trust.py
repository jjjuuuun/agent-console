"""`UsageTrust`는 열린 문자열이다(R0, 1R.13). 알려진 값은 문서 상수로만 둔다."""

from agent_console_contracts import KnownUsageTrust, UsageSourceDescriptor, build_schema

KNOWN = {
    KnownUsageTrust.OFFICIAL,
    KnownUsageTrust.OBSERVED,
    KnownUsageTrust.ESTIMATED,
    KnownUsageTrust.UNOFFICIAL,
}


def test_trust_is_open_string_in_schema() -> None:
    defs = build_schema()["$defs"]
    trust = defs["UsageTrust"]
    assert trust["type"] == "string"
    assert not {"enum", "const", "default"} & trust.keys()


def test_plugin_can_declare_new_trust() -> None:
    desc = UsageSourceDescriptor(id="x", title="X", trust="community-verified")
    assert desc.trust == "community-verified"
    for value in KNOWN:
        assert UsageSourceDescriptor(id="x", title="X", trust=value).trust == value


def test_known_trust_values_not_exported_as_constants() -> None:
    text = repr(build_schema()["x-constants"])
    for value in KNOWN:
        assert f"'{value}'" not in text, value
