"""`project.yaml` 매니페스트 읽기·쓰기(If-Match)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agent_console_contracts import PROJECT_MANIFEST_FORMAT, ProjectManifest, VersionConflictDetails
from agent_console_store import (
    DefinitionCorrupt,
    NotFound,
    VersionConflict,
    VersionRequired,
    default_hash,
    dump_yaml,
    load_yaml_text,
    merge_into,
    to_plain,
    wrap_value,
)

from ._errors import ConfigReadonly, ManifestInvalid, SecretRejected
from ._space import ProjectSpace, scan_secrets


@dataclass(frozen=True, slots=True)
class ManifestRecord:
    """읽은 매니페스트와 그 버전(`If-Match`에 쓰는 해시)."""

    manifest: ProjectManifest
    version: str


def _parse(data: bytes) -> tuple[dict[str, Any], Any]:
    """(일반 dict, ruamel 객체). 못 읽으면 `ManifestInvalid`."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ManifestInvalid("not_utf8") from exc
    try:
        loaded = load_yaml_text(text, "project.yaml")
    except DefinitionCorrupt as exc:
        raise ManifestInvalid("yaml", str(exc)) from exc
    return to_plain(loaded), loaded


def _record(plain: dict[str, Any]) -> ManifestRecord:
    try:
        manifest = ProjectManifest.model_validate(plain)
    except ValidationError as exc:
        issues = tuple(sorted({"/" + "/".join(str(p) for p in e["loc"]) for e in exc.errors()}))
        raise ManifestInvalid("schema", ", ".join(issues), issues=issues) from exc
    return ManifestRecord(manifest, default_hash(plain))


def _read_raw(space: ProjectSpace) -> tuple[bytes, dict[str, Any], Any] | None:
    try:
        data = space.files.read_bytes(space.manifest_path)
    except OSError as exc:
        raise ManifestInvalid("unreadable", exc.__class__.__name__) from exc
    if data is None:
        return None
    plain, loaded = _parse(data)
    return data, plain, loaded


def read_manifest(space: ProjectSpace) -> ManifestRecord | None:
    """폴더의 `project.yaml`을 읽는다. 모르는 키는 `manifest.model_extra`에 보존된다.

    Returns:
        `ManifestRecord`. 파일이 없으면 None.

    Raises:
        ManifestInvalid: 읽을 수 없다(`reason`: unreadable·not_utf8·yaml·schema).
    """
    raw = _read_raw(space)
    return None if raw is None else _record(raw[1])


def _dump(manifest: ProjectManifest) -> dict[str, Any]:
    data: dict[str, Any] = manifest.model_dump(mode="json", exclude_unset=True)
    data.setdefault("format", PROJECT_MANIFEST_FORMAT)
    return data


def write_manifest(
    space: ProjectSpace, manifest: ProjectManifest, *, expected_version: str | None = None
) -> ManifestRecord:
    """`project.yaml`을 쓴다(원자적, 기존 주석·키 순서 보존, 모르는 키 왕복).

    파일이 이미 있으면 `expected_version`(마지막으로 읽은 `ManifestRecord.version`)이 필요하다.
    없으면 새로 만든다(이때 `expected_version`을 주면 `NotFound`).

    Raises:
        ConfigReadonly: 구성 폴더에 쓸 수 없다.
        SecretRejected: 평문 비밀로 보이는 값이 있다(`secret://` 참조만 허용).
        ManifestInvalid: 기존 파일이 깨졌거나 더 새로운 형식이다(고치려면 `reset_manifest`).
        VersionRequired, VersionConflict: If-Match 규칙.
        NotFound: 파일이 없는데 `expected_version`을 줬다.
        OSError: 파일을 쓰지 못했다.
    """
    if not space.config_writable:
        raise ConfigReadonly("project.yaml: the project folder is read-only")
    data = _dump(manifest)
    findings = scan_secrets(space.secret_rules, data)
    if findings:
        raise SecretRejected(tuple(findings))
    existing = _read_raw(space)
    target: Any
    if existing is None:
        if expected_version is not None:
            raise NotFound("project.yaml")
        target = wrap_value(data)
    else:
        _, plain, loaded = existing
        current = _record(plain)
        if current.manifest.format > PROJECT_MANIFEST_FORMAT:
            raise ManifestInvalid("newer_format", f"format {current.manifest.format}")
        if expected_version is None:
            raise VersionRequired("project.yaml: expected_version is required")
        if expected_version != current.version:
            raise VersionConflict(VersionConflictDetails(current_version_hash=current.version))
        target = merge_into(loaded, data)
    space.files.write_bytes(space.manifest_path, dump_yaml(target).encode("utf-8"))
    written = read_manifest(space)
    assert written is not None
    return written


def reset_manifest(
    space: ProjectSpace, manifest: ProjectManifest, *, now: datetime | None = None
) -> Path | None:
    """깨진(또는 아무) `project.yaml`을 백업하고 `manifest`로 새로 쓴다.

    옛 파일은 `<state_dir>/backups/project-<UTC 시각>.yaml`로 보관한다(같은 초에 두 번이면
    `-2`, `-3`…). 파일이 없었으면 백업 없이 새로 만든다.

    Returns:
        백업 경로. 옛 파일이 없었으면 None.

    Raises:
        ConfigReadonly, SecretRejected, OSError: `write_manifest`와 같다.
    """
    if not space.config_writable:
        raise ConfigReadonly("project.yaml: the project folder is read-only")
    data = _dump(manifest)
    findings = scan_secrets(space.secret_rules, data)
    if findings:
        raise SecretRejected(tuple(findings))
    try:
        old = space.files.read_bytes(space.manifest_path)
    except OSError as exc:
        raise ManifestInvalid("unreadable", exc.__class__.__name__) from exc
    backup: Path | None = None
    if old is not None:
        stamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        folder = space.state_dir / "backups"
        stem = f"project-{stamp}"
        backup = folder / f"{stem}.yaml"
        n = 1
        while space.files.read_bytes(backup) is not None:
            n += 1
            backup = folder / f"{stem}-{n}.yaml"
        space.files.write_bytes(backup, old)
    space.files.write_bytes(space.manifest_path, dump_yaml(wrap_value(data)).encode("utf-8"))
    return backup
