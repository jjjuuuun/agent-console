"""여러 프리셋 디렉터리에서 프리셋을 찾는다. 경로는 호출자(앱 설정)가 넘긴다."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from ._manifest import MANIFEST_FILE, Preset, PresetError, load_preset


@dataclass(frozen=True, slots=True)
class PresetProblem:
    """찾는 중 건너뛴 폴더 하나와 그 사유(화면·로그에 그대로 보일 수 있는 값만)."""

    path: str
    error: str


@dataclass(slots=True)
class PresetDiscovery:
    """`discover_presets` 결과. 문제가 있는 폴더는 건너뛰고 `problems`에 남긴다."""

    presets: list[Preset] = field(default_factory=list)
    problems: list[PresetProblem] = field(default_factory=list)

    def get(self, preset_id: str) -> Preset | None:
        return next((p for p in self.presets if p.id == preset_id), None)


def discover_presets(
    search_paths: Iterable[str | Path], *, manifest_file: str = MANIFEST_FILE
) -> PresetDiscovery:
    """각 경로의 바로 아래 폴더 중 매니페스트가 있는 것을 프리셋으로 읽는다.

    - 없는 경로·빈 경로는 문제가 아니다(프리셋이 하나도 없어도 된다).
    - 같은 id가 여러 번 나오면 먼저 나온 경로가 이기고 나머지는 `problems`에 남긴다.
    - 폴더 이름 순으로 결정적이다.

    Args:
        search_paths: 프리셋 디렉터리 목록(앞쪽이 우선).
        manifest_file: 매니페스트 파일 이름.
    """
    result = PresetDiscovery()
    seen: dict[str, Path] = {}
    for base in search_paths:
        root = Path(base)
        if not root.is_dir():
            continue
        for folder in sorted(p for p in root.iterdir() if p.is_dir()):
            if folder.name.startswith(".") or not (folder / manifest_file).is_file():
                continue
            try:
                preset = load_preset(folder, manifest_file=manifest_file)
            except PresetError as exc:
                result.problems.append(PresetProblem(str(folder), str(exc)))
                continue
            if preset.id in seen:
                result.problems.append(
                    PresetProblem(str(folder), f"duplicate preset id {preset.id!r} (shadowed)")
                )
                continue
            seen[preset.id] = folder
            result.presets.append(preset)
    return result
