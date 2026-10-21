"""프리셋 적용 = 항목 정의를 정의 저장소(`DefinitionStore`)로 복사한다.

파일을 직접 복사하지 않고 저장소 API(`create`/`save`)를 거친다 —
모델 검증, 버전 스냅샷, If-Match 규칙을
그대로 따르게 하기 위함이다. 저장소 구현(파일·메모리)은 호출자가 넘긴다.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import ValidationError

from agent_console_store import (
    DEFAULT_KINDS,
    DefinitionCorrupt,
    DefinitionKind,
    DefinitionStore,
    NotFound,
    StoreError,
)

from ._manifest import Preset, PresetError, read_yaml_mapping

ConflictPolicy = Literal["skip", "overwrite", "rename"]
"""같은 종류·id 정의가 이미 있을 때: 건너뜀 / 덮어씀 / 새 id(`<id>-2`, `<id>-3`, …)로 만듦."""

ItemAction = Literal["created", "overwritten", "renamed", "skipped", "failed"]

RenameMap = Mapping[tuple[str, str], str]
"""(종류, 프리셋 안 id) → 새 id."""

ReferenceRewriter = Callable[[str, dict[str, Any], RenameMap], dict[str, Any]]
"""`(종류, 문서, 이름 바꾼 목록) -> 문서`.
다른 정의를 가리키는 참조(예: 노드 config의 에이전트 id)를
고친다. 참조 형식은 노드 타입 등이 정하므로 이 패키지는 모른다 — 앱이 주입한다."""

ItemValidator = Callable[[str, Mapping[str, Any]], Sequence[str]]
"""`(종류, 쓸 문서) -> 오류 목록`. 비어 있지 않으면 그 항목을 쓰지 않고 `failed`로 남긴다.

모델 검증 밖의 규칙(예: 리소스 종류 검사의 평문 비밀 금지)은 앱이 안다 — 앱이 주입한다.
오류 문자열은 보고서·로그에 그대로 나가므로 값(비밀)을 넣지 않는다."""

ItemDependencies = Callable[[str, Mapping[str, Any]], Iterable[tuple[str, str]]]
"""`(종류, 문서) -> 이 문서가 쓰는 (종류, id) 목록`. 적용 순서를 정한다(쓰는 정의를 먼저 쓴다).

무엇이 무엇을 쓰는지(예: 팀 구성 → 에이전트·자식 팀 구성)는 노드 타입 등이 정하므로 이 패키지는
모른다 — 앱이 주입한다. 프리셋 밖 정의를 가리키는 값은 무시한다."""

Stamp = Mapping[str, Any]
"""만든·덮어쓴 항목 문서의 최상위 필드에 그대로 찍을 값(예: `{"project": "app"}`, design §UX-P.4).

값이 `None`이면 그 필드를 문서에서 뺀다(생략 = 기본값, 예: 공용). 종류 모델이 선언하지 않은 필드는
찍지 않고 `warnings`에 남긴다(모델이 없는 종류는 모두 찍는다). 필드의 뜻은 이 패키지가 모른다."""

ITEM_INVALID = "validation_failed"
"""`validate_item`이 거부한 항목의 `AppliedItem.error` 접두어."""

_MAX_ID = 128


@dataclass(frozen=True, slots=True)
class PresetItem:
    """읽어서 검증한 항목 하나."""

    kind: str
    source: str
    id: str
    document: dict[str, Any]
    content: bytes | None = None
    """본문 파일 내용(종류에 `content_field`가 있고 문서가 본문을 가리킬 때)."""


@dataclass(frozen=True, slots=True)
class AppliedItem:
    """항목 하나의 적용 결과.

    Attributes:
        source: 프리셋 폴더 기준 항목 경로.
        kind: 정의 종류.
        id: 프리셋 안의 id.
        target_id: 워크스페이스에 쓴(또는 건너뛴) id. 이름을 바꿨으면 새 id.
        action: created | overwritten | renamed | skipped | failed.
        error: 실패 사유(`failed`일 때).
    """

    source: str
    kind: str
    id: str
    target_id: str
    action: ItemAction
    error: str | None = None


@dataclass(slots=True)
class ApplyReport:
    """`apply_preset` 결과."""

    preset_id: str
    items: list[AppliedItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """실패한 항목이 없으면 True(건너뜀 포함)."""
        return all(i.action != "failed" for i in self.items)

    def renames(self) -> dict[tuple[str, str], str]:
        return {(i.kind, i.id): i.target_id for i in self.items if i.action == "renamed"}


def _kind_maps(
    kinds: Iterable[DefinitionKind],
) -> tuple[dict[str, DefinitionKind], dict[str, DefinitionKind]]:
    by_name: dict[str, DefinitionKind] = {}
    by_dir: dict[str, DefinitionKind] = {}
    for kind in kinds:
        by_name[kind.name] = kind
        if kind.directory and not kind.is_singleton:
            by_dir.setdefault(kind.directory, kind)
    return by_name, by_dir


def load_items(
    preset: Preset, *, kinds: Iterable[DefinitionKind] = DEFAULT_KINDS
) -> list[PresetItem]:
    """매니페스트의 항목 파일을 읽고 종류 모델로 검증한다(아무것도 쓰지 않는다).

    종류는 `{file, kind}`의 `kind`, 없으면 경로의 첫 폴더 이름과 같은
    `DefinitionKind.directory`로 정한다.
    단일 문서 종류(settings 등)는 항목이 될 수 없다 — 사용자 설정을 덮어쓰지 않기 위함이다.

    Raises:
        PresetError: 경로 위반, 종류를 알 수 없음, 파일·모델 형식 오류, 프리셋 안 중복 id.
    """
    by_name, by_dir = _kind_maps(kinds)
    items: list[PresetItem] = []
    seen: set[tuple[str, str]] = set()
    for ref in preset.manifest.item_refs():
        path = preset.resolve(ref.file)
        if ref.kind is not None:
            kind = by_name.get(ref.kind)
        else:
            parts = PurePosixPath(ref.file).parts
            kind = by_dir.get(parts[0]) if len(parts) > 1 else None
        if kind is None:
            raise PresetError(f"{preset.id}: cannot tell the definition kind of {ref.file!r}")
        if kind.is_singleton:
            raise PresetError(f"{preset.id}: {kind.name!r} cannot be a preset item ({ref.file})")
        if not path.is_file():
            raise PresetError(f"{preset.id}: missing item file {ref.file!r}")
        document = read_yaml_mapping(path)
        if kind.model is not None:
            # 검증만 한다. 문서는 원본 그대로 쓴다 — 모델로 다시 직렬화하면 생략한 필드가 null로
            # 채워져 "생략 = 상속"(design §R2.2)이 "이 층에서 비움"으로 바뀐다.
            try:
                kind.model.model_validate(document)
            except ValidationError as exc:
                raise PresetError(f"{preset.id}/{ref.file}: {exc}") from exc
        item_id = document.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise PresetError(f"{preset.id}/{ref.file}: document has no string 'id'")
        if (kind.name, item_id) in seen:
            raise PresetError(f"{preset.id}: duplicate {kind.name} id {item_id!r}")
        seen.add((kind.name, item_id))
        content = _read_content(preset, ref.file, kind, item_id, document)
        items.append(PresetItem(kind.name, ref.file, item_id, document, content))
    return items


def _read_content(
    preset: Preset, source: str, kind: DefinitionKind, item_id: str, document: dict[str, Any]
) -> bytes | None:
    """본문 파일: 항목 파일 옆 `<id>/<content.file>`(저장소 배치와 같다). 없으면 `PresetError`."""
    if kind.content_field is None:
        return None
    ref = document.get(kind.content_field)
    if ref is None:
        return None
    file = ref.get("file") if isinstance(ref, Mapping) else None
    if not isinstance(file, str) or not file:
        raise PresetError(f"{preset.id}/{source}: {kind.content_field} needs a 'file'")
    parent = PurePosixPath(source).parent
    path = preset.resolve(str(parent / item_id / file))
    try:
        return path.read_bytes()
    except OSError as exc:
        raise PresetError(
            f"{preset.id}/{source}: cannot read content file {file!r} ({type(exc).__name__})"
        ) from exc


def order_items(
    items: Sequence[PresetItem],
    dependencies: ItemDependencies | None,
    *,
    warnings: list[str] | None = None,
) -> list[PresetItem]:
    """쓰는 정의가 먼저 오도록 항목을 늘어놓는다(같은 프리셋 안만, 나머지는 매니페스트 순서).

    매니페스트 순서로 돌며 깊이 우선으로 의존을 먼저 놓는 정렬이다(의존이 없으면 순서 그대로).
    순환이면 이미 방문 중인 의존을 건너뛰어 고리를 끊는다.
    `dependencies`가 예외를 내면 그 항목은 의존 없음으로 보고 `warnings`에 종류·id만 남긴다
    (문서 값은 담지 않는다).

    Args:
        items: `load_items` 결과(매니페스트 순서).
        dependencies: 의존 함수. None이면 매니페스트 순서 그대로.
        warnings: 경고를 덧붙일 목록(선택).

    Returns:
        새 목록.
    """
    if dependencies is None:
        return list(items)
    index = {(i.kind, i.id): i for i in items}
    done: set[tuple[str, str]] = set()
    visiting: set[tuple[str, str]] = set()
    out: list[PresetItem] = []

    def uses(item: PresetItem) -> list[tuple[str, str]]:
        try:
            found = [(str(k), str(v)) for k, v in dependencies(item.kind, item.document)]
        except Exception as exc:  # 주입 함수 오류는 순서만 포기한다(적용은 계속)
            if warnings is not None:
                warnings.append(
                    f"dependency check failed for {item.kind}/{item.id} ({type(exc).__name__})"
                )
            return []
        return [key for key in found if key in index and key != (item.kind, item.id)]

    def visit(item: PresetItem) -> None:
        key = (item.kind, item.id)
        if key in done or key in visiting:
            return
        visiting.add(key)
        for dep in uses(item):
            visit(index[dep])
        visiting.discard(key)
        done.add(key)
        out.append(item)

    for item in items:
        visit(item)
    return out


def stamp_fields(kind: DefinitionKind | None, stamp: Stamp) -> tuple[dict[str, Any], list[str]]:
    """`stamp` 중 `kind`에 찍을 수 있는 필드와 찍지 못하는 필드 이름.

    찍을 수 있다 = 종류 모델이 없거나 모델이 그 필드를 선언했다(`model_fields`). `id`는 찍지 않는다.
    """
    model = kind.model if kind is not None else None
    ok: dict[str, Any] = {}
    skipped: list[str] = []
    for name, value in stamp.items():
        if name == "id" or (model is not None and name not in model.model_fields):
            skipped.append(name)
        else:
            ok[name] = value
    return ok, skipped


def apply_stamp(document: dict[str, Any], fields: Mapping[str, Any]) -> dict[str, Any]:
    """`fields`를 `document`에 찍은 새 문서(값 `None` = 필드 빼기). 원본은 바꾸지 않는다."""
    out = dict(document)
    for name, value in fields.items():
        if value is None:
            out.pop(name, None)
        else:
            out[name] = copy.deepcopy(value)
    return out


def _exists(store: DefinitionStore, kind: str, id: str) -> bool:
    try:
        store.get(kind, id)
    except NotFound:
        return False
    except DefinitionCorrupt:
        return True
    return True


def _free_id(store: DefinitionStore, kind: str, id: str, taken: set[tuple[str, str]]) -> str:
    n = 2
    while True:
        suffix = f"-{n}"
        candidate = id[: _MAX_ID - len(suffix)] + suffix
        if (kind, candidate) not in taken and not _exists(store, kind, candidate):
            return candidate
        n += 1


def apply_preset(
    preset: Preset,
    store: DefinitionStore,
    *,
    kinds: Iterable[DefinitionKind] = DEFAULT_KINDS,
    on_conflict: ConflictPolicy = "skip",
    rewrite_references: ReferenceRewriter | None = None,
    validate_item: ItemValidator | None = None,
    dependencies: ItemDependencies | None = None,
    message: str | None = None,
    stamp: Stamp | None = None,
) -> ApplyReport:
    """프리셋 항목을 저장소에 복사한다.

    모든 항목을 먼저 읽고 검증한 뒤(`load_items`) 쓰기 시작한다 —
    형식 오류가 있으면 아무것도 쓰지 않는다.
    쓰기 중 저장소 오류는 그 항목만 `failed`로 남기고 계속한다.

    Args:
        preset: `load_preset`/`discover_presets`로 읽은 프리셋.
        store: 대상 정의 저장소.
        kinds: 항목 경로 → 정의 종류 해석에 쓸 종류 목록(저장소에 등록된 것과 같아야 한다).
        on_conflict: 같은 id가 이미 있을 때의 정책(기본 skip = 사용자 정의를 건드리지 않음).
        rewrite_references: 이름을 바꾼 정의를 가리키는 참조를 고치는 함수. 없고 이름을 바꿨으면
            `warnings`에 남긴다.
        validate_item: 쓰기 직전(참조를 고친 뒤) 문서마다 부르는 추가 검사. 오류가 있으면 그 항목은
            저장하지 않고 `failed`(`error = "validation_failed: ..."`)로 남긴다. 덮어쓰기면 기존
            정의는 그대로 둔다. 없으면 모델 검증만 한다.
        dependencies: 항목이 쓰는 정의를 알려 주는 함수(`ItemDependencies`). 주면 쓰는 정의를 먼저
            쓴다(`order_items`, 예: 에이전트 → 자식 팀 구성 → 팀 구성). 없으면 매니페스트 순서.
            보고서 `items`도 쓴 순서다.
        message: 버전 스냅샷 메시지. 기본 `"preset <id>"`.
        stamp: 쓰는 항목(만듦·덮어씀·이름 바꿈)마다 찍을 최상위 필드(`Stamp`, 예: 프로젝트 범위
            `{"project": "app"}`). 건너뛴 항목에는 찍지 않는다. 찍은 뒤 `validate_item`이 본다.
            없으면 프리셋 문서 그대로(지금과 같음).

    Returns:
        `ApplyReport`.

    Raises:
        PresetError: 항목 형식 오류(아무것도 쓰지 않은 상태).
    """
    if on_conflict not in ("skip", "overwrite", "rename"):
        raise ValueError(f"unknown conflict policy: {on_conflict!r}")
    kinds = list(kinds)
    note = message if message is not None else f"preset {preset.id}"
    report = ApplyReport(preset_id=preset.id)
    items = order_items(load_items(preset, kinds=kinds), dependencies, warnings=report.warnings)

    # 1) 계획: 항목마다 동작과 대상 id를 정한다.
    taken: set[tuple[str, str]] = set()
    plan: list[tuple[PresetItem, ItemAction, str]] = []
    for item in items:
        action: ItemAction = "created"
        target = item.id
        if _exists(store, item.kind, item.id):
            if on_conflict == "skip":
                action = "skipped"
            elif on_conflict == "overwrite":
                action = "overwritten"
            else:
                action = "renamed"
                target = _free_id(store, item.kind, item.id, taken)
        taken.add((item.kind, target))
        plan.append((item, action, target))
    renames = {(i.kind, i.id): t for i, a, t in plan if a == "renamed"}
    by_name, _ = _kind_maps(kinds)
    stamps: dict[str, dict[str, Any]] = {}
    if stamp:
        for name in dict.fromkeys(i.kind for i, a, _t in plan if a != "skipped"):
            stamps[name], skipped = stamp_fields(by_name.get(name), stamp)
            if skipped:
                report.warnings.append(f"stamp fields not in {name}: {', '.join(skipped)}")
    if renames and rewrite_references is None:
        listed = ", ".join(f"{k}/{old}->{new}" for (k, old), new in renames.items())
        report.warnings.append(f"renamed without rewriting references: {listed}")

    # 2) 쓰기.
    for item, action, target in plan:
        if action == "skipped":
            report.items.append(AppliedItem(item.source, item.kind, item.id, target, action))
            continue
        document = copy.deepcopy(item.document)
        document["id"] = target
        if stamps.get(item.kind):
            document = apply_stamp(document, stamps[item.kind])
        if renames and rewrite_references is not None:
            document = rewrite_references(item.kind, document, renames)
        problems = list(validate_item(item.kind, document)) if validate_item is not None else []
        if problems:
            error = f"{ITEM_INVALID}: " + "; ".join(problems)
            report.items.append(
                AppliedItem(item.source, item.kind, item.id, target, "failed", error)
            )
            continue
        try:
            if action == "overwritten":
                current = store.get(item.kind, item.id)
                stored = store.save(
                    item.kind, document, expected_version=current.version_hash, message=note
                )
            else:
                stored = store.create(item.kind, document, message=note)
            if item.content is not None:
                store.write_content(
                    item.kind,
                    target,
                    item.content,
                    expected_version=stored.version_hash,
                    message=note,
                )
        except (StoreError, ValidationError) as exc:
            code = exc.code if isinstance(exc, StoreError) else "validation_failed"
            report.items.append(
                AppliedItem(item.source, item.kind, item.id, target, "failed", f"{code}: {exc}")
            )
            continue
        report.items.append(AppliedItem(item.source, item.kind, item.id, target, action))

    return report
