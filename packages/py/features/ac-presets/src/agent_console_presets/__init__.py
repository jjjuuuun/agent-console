"""agent-console-presets: 프리셋(데이터 묶음) 읽기·탐색·적용.

프리셋 = 폴더 + `preset.yaml`(매니페스트) + 정의 YAML 항목. 적용은 항목을 정의 저장소
(`agent_console_store.DefinitionStore`)로 복사하는 것이다. 시스템은 프리셋 존재를 가정하지 않는다.
설계: specs/agent-console/design.md §2.2(Preset).

공개 API:
    - 읽기: ``load_preset``, ``Preset``, ``PresetManifest``, ``PresetItemRef``, ``PresetSample``,
      ``MANIFEST_FILE``, ``PresetError``
    - 탐색: ``discover_presets``, ``PresetDiscovery``, ``PresetProblem``
    - 적용: ``apply_preset``, ``load_items``, ``PresetItem``, ``ApplyReport``, ``AppliedItem``,
      ``ConflictPolicy``, ``ItemAction``, ``ReferenceRewriter``, ``RenameMap``,
      ``ItemValidator``(앱이 주입하는 추가 검사), ``ITEM_INVALID``,
      ``ItemDependencies``·``order_items``(쓰는 정의를 먼저 쓰는 적용 순서, 의존 함수는 앱이 주입),
      ``Stamp``·``stamp_fields``·``apply_stamp``(만든 항목에 찍는 최상위 필드, 예: 프로젝트 범위)
    - 훑기: ``collect_values``(항목 문서가 가리키는 값, 예: 쓰는 실행 백엔드 이름)
"""

from ._apply import (
    ITEM_INVALID,
    AppliedItem,
    ApplyReport,
    ConflictPolicy,
    ItemAction,
    ItemDependencies,
    ItemValidator,
    PresetItem,
    ReferenceRewriter,
    RenameMap,
    Stamp,
    apply_preset,
    apply_stamp,
    load_items,
    order_items,
    stamp_fields,
)
from ._discovery import PresetDiscovery, PresetProblem, discover_presets
from ._manifest import (
    MANIFEST_FILE,
    Preset,
    PresetError,
    PresetItemRef,
    PresetManifest,
    PresetSample,
    load_preset,
)
from ._scan import collect_values

__all__ = [
    "ITEM_INVALID",
    "MANIFEST_FILE",
    "AppliedItem",
    "ApplyReport",
    "ConflictPolicy",
    "ItemAction",
    "ItemDependencies",
    "ItemValidator",
    "Preset",
    "PresetDiscovery",
    "PresetError",
    "PresetItem",
    "PresetItemRef",
    "PresetManifest",
    "PresetProblem",
    "PresetSample",
    "ReferenceRewriter",
    "RenameMap",
    "Stamp",
    "apply_preset",
    "apply_stamp",
    "collect_values",
    "discover_presets",
    "load_items",
    "load_preset",
    "order_items",
    "stamp_fields",
]
