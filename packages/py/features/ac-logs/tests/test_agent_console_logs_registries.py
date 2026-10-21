from importlib.metadata import EntryPoint

from agent_console_logs import (
    LOG_CLASSIFIERS_EXTENSION,
    LOG_CLASSIFIERS_GROUP,
    LOG_SOURCES_EXTENSION,
    LOG_SOURCES_GROUP,
    LogClassifier,
    LogRegistries,
    LogSource,
    as_log_classifier,
    as_log_source,
)
from agent_console_logs.plugins import NormalizedV1Classifier, NormalizedV1Source
from agent_console_registry import Registry


def test_installed_entry_points() -> None:
    regs = LogRegistries()
    reports = regs.load()
    assert all(r.ok for group in reports.values() for r in group)
    # 워크스페이스에는 다른 패키지의 플러그인(ac-logs-claude·ac-hook-probe 등)도 설치돼 있다.
    assert {"mapped-jsonl", "normalized-v1"} <= {d.id for d in regs.source_descriptors()}
    assert {"mapped-jsonl", "normalized-v1"} <= {d.id for d in regs.classifier_descriptors()}


def test_injected_entry_points_and_failures() -> None:
    eps = [
        EntryPoint(
            "mine", "agent_console_logs.plugins.normalized:NormalizedV1Source", LOG_SOURCES_GROUP
        ),
        EntryPoint("bad", "agent_console_logs:bounded", LOG_SOURCES_GROUP),
        EntryPoint(
            "c",
            "agent_console_logs.plugins.normalized:NormalizedV1Classifier",
            LOG_CLASSIFIERS_GROUP,
        ),
    ]
    regs = LogRegistries()
    reports = regs.load(entry_points=eps, enabled_classifiers={"other"})
    status = {r.key: r.status for r in reports["log_sources"]}
    assert status == {"bad": "failed", "mine": "loaded"}
    assert [r.status for r in reports["log_classifiers"]] == ["skipped"]
    assert [d.id for d in regs.source_descriptors()] == ["mine"]  # id = key


def test_module_paths() -> None:
    regs = LogRegistries()
    reports = regs.load(
        entry_points=[],
        source_modules=["x=agent_console_logs.plugins.mapped:MappedJsonlSource"],
        classifier_modules=["agent_console_logs.plugins.mapped:MappedJsonlClassifier"],
    )
    assert [r.key for r in reports["log_sources"]] == ["x"]
    assert "MappedJsonlClassifier" in regs.classifiers


def test_validators_idempotent() -> None:
    src = as_log_source(NormalizedV1Source)
    assert as_log_source(src) is src
    cls = as_log_classifier(NormalizedV1Classifier())
    assert as_log_classifier(cls) is cls


def test_injected_empty_registries_are_used_not_replaced() -> None:
    """빈 레지스트리(거짓 값)를 주입해도 그것에 로드한다(호스트 묶음 확장 공유, 4R.10)."""
    sources: Registry[LogSource] = Registry(LOG_SOURCES_EXTENSION, validator=as_log_source)
    classifiers: Registry[LogClassifier] = Registry(
        LOG_CLASSIFIERS_EXTENSION, validator=as_log_classifier
    )
    registries = LogRegistries(sources=sources, classifiers=classifiers)
    assert registries.sources is sources
    assert registries.classifiers is classifiers
    registries.load()
    assert "normalized-v1" in sources
    assert "normalized-v1" in classifiers
