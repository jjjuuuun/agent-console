"""`poe schema-help-lint`(scripts/schema_help_lint.py): 번들 = 오류 0, 외부 플러그인 = 경고만."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def _script() -> ModuleType:
    path = ROOT / "scripts" / "schema_help_lint.py"
    spec = importlib.util.spec_from_file_location("schema_help_lint_script", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dist_of_reads_registry_source() -> None:
    lint = _script()
    src = "entry_point g:agent (pkg.mod:Agent) [agent-console-nodes-core 0.1.0]"
    assert lint.dist_of(src) == "agent-console-nodes-core"
    assert lint.dist_of("module pkg.mod:Thing") is None
    assert lint.dist_of(None) is None


def test_workspace_dists_come_from_root_sources() -> None:
    names = _script().workspace_dists(ROOT)
    assert {"agent-console-contracts", "agent-console-nodes-core"} <= names


def test_bundled_plugins_and_contract_have_no_errors() -> None:
    lint = _script()
    targets = lint.collect_targets()
    labels = {t.label.split("/", 1)[0] for t in targets}
    assert {"node-types", "edge-types", "backends", "resource-types", "usage-sources"} <= labels
    assert any(t.label.startswith("delegation-strategies/") for t in targets)
    assert any(t.label.startswith("modules/") and t.label.endswith("/options") for t in targets)
    errors, _ = lint.run(targets, lint.workspace_dists(ROOT))
    assert errors == [], "\n".join(f"{e.rule} {e.path}" for e in errors[:40])


def test_external_plugin_problems_are_warnings_only() -> None:
    lint = _script()
    bad = {"type": "object", "properties": {"n": {"type": "integer"}}}
    external = lint.Target("node-types/x/config_schema", bad, "someone-elses-plugin")
    unknown = lint.Target("resource-types/y/config_schema", bad, None)
    bundled = lint.Target("node-types/z/config_schema", bad, "agent-console-nodes-core")
    errors, warnings = lint.run(
        [external, unknown, bundled], {"agent-console-nodes-core"}, contract=False
    )
    assert {w.path.split("/")[1] for w in warnings} == {"x", "y"}
    assert {e.path.split("/")[1] for e in errors} == {"z"}


def test_bundled_warning_rules_stay_warnings() -> None:
    lint = _script()
    prop = {
        "type": "string",
        "title": "이름",
        "description": "비우면 위 층 값을 씁니다.",
        "x-ui": {"tier": "basic", "example": "x", "when": "바꾸고 싶을 때 바꾸세요."},
    }
    bundled = lint.Target(
        "node-types/z/config_schema",
        {"type": "object", "properties": {"n": prop}},
        "agent-console-nodes-core",
    )
    errors, warnings = lint.run([bundled], {"agent-console-nodes-core"}, contract=False)
    assert errors == []
    assert [w.rule for w in warnings] == ["hard-term"]


def test_module_option_schemas_are_collected_with_their_distribution() -> None:
    lint = _script()
    targets = lint.module_option_targets()
    assert len(targets) >= 3
    bundled = lint.workspace_dists(ROOT)
    assert all(t.dist in bundled for t in targets), [t.label for t in targets if t.dist is None]
    assert all(t.schema.get("type") == "object" for t in targets)


def test_bundled_object_descriptions_are_checked() -> None:
    """모델 docstring에서 온 객체 설명도 문구 규칙으로 본다(번들 = 오류, 외부 = 경고)."""
    lint = _script()
    schema = {
        "type": "object",
        "description": "`Agent.backend_options` 형식.",
        "properties": {},
    }
    bundled = lint.Target("backends/z/config_schema", schema, "agent-console-nodes-core")
    external = lint.Target("backends/x/config_schema", schema, "someone-elses-plugin")
    errors, warnings = lint.run([bundled, external], {"agent-console-nodes-core"}, contract=False)
    assert {e.path for e in errors} == {"backends/z/config_schema/description"}
    assert {w.path for w in warnings} == {"backends/x/config_schema/description"}
