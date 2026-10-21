"""프리셋 매니페스트(`preset.yaml`) 형식과 읽기.

프리셋 = 폴더 하나 + 매니페스트 + 항목 파일(정의 YAML). 무엇이 들어 있는지는 전부 데이터다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from ruamel.yaml import YAML

MANIFEST_FILE = "preset.yaml"
"""프리셋 폴더 안 매니페스트 파일 이름의 기본값(`load_preset(manifest_file=...)`로 바꿀 수 있다)."""

_SLUG = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"


class PresetError(ValueError):
    """프리셋을 읽거나 해석할 수 없음(매니페스트·항목 파일 형식 오류, 경로 위반 등)."""


class PresetItemRef(BaseModel):
    """항목 하나. `kind`를 생략하면 경로의 첫 폴더 이름으로 정의 종류를 찾는다."""

    model_config = ConfigDict(extra="forbid")

    file: str = Field(min_length=1, description="프리셋 폴더 기준 상대 경로.")
    kind: str | None = Field(default=None, description="정의 종류 이름(예: 저장소의 kind).")


class PresetSample(BaseModel):
    """시연용 입력 예시. 화면의 "예시 입력"과 프리셋 자기 검사에 쓴다."""

    model_config = ConfigDict(extra="allow")

    input: str = Field(description="사용자 메시지(채팅 입력).")
    graph: str | None = Field(default=None, description="실행할 그래프 id. 생략하면 default_entry.")
    description: str = ""
    responses: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "실행 중 열리는 상호작용(되묻기·승인·검토)에 순서대로 줄 응답. "
            "응답 모양은 상호작용 종류의 response_schema를 따른다(시연·자기 검사용 데이터)."
        ),
    )


class PresetManifest(BaseModel):
    """`preset.yaml`. 모르는 최상위 필드는 보존한다(손으로 고친 파일·새 버전 호환)."""

    model_config = ConfigDict(extra="allow")

    kind: Literal["preset"] = "preset"
    id: str = Field(pattern=_SLUG)
    schema_version: int = 1
    name: str = Field(min_length=1)
    description: str = ""
    labels: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    items: list[str | PresetItemRef] = Field(
        default_factory=list, description="적용할 항목 파일(프리셋 폴더 기준 상대 경로)."
    )
    default_entry: str | None = Field(
        default=None,
        description="대표 그래프 id. 예시(`samples`)의 `graph`를 생략하면 이 값을 쓴다.",
    )
    samples: list[PresetSample] = Field(default_factory=list)
    # 5.2R.6: 화면 "바로 시작" 줄에 쓰는 선택 키(전부 데이터, 프리셋 이름을 코드에 두지 않는다).
    featured: int | None = Field(
        default=None,
        description="'바로 시작' 순서(작을수록 앞). 생략 = 바로 시작에 두지 않는다.",
    )
    badges: list[str] = Field(
        default_factory=list, description="카드에 보일 짧은 배지 글자(예: 추천)."
    )
    start_graph: str | None = Field(
        default=None,
        description=(
            "적용한 뒤 바로 대화를 열 팀 구성 id(프리셋 안 id). 키를 생략하면 `default_entry`, "
            "`null`이면 열지 않는다."
        ),
    )

    def item_refs(self) -> list[PresetItemRef]:
        """`items`를 모두 `PresetItemRef`로 바꿔 돌려준다."""
        return [PresetItemRef(file=i) if isinstance(i, str) else i for i in self.items]

    def start_graph_id(self) -> str | None:
        """적용 뒤 열 팀 구성 id.

        `start_graph` 키가 있으면 그 값(null 포함), 없으면 `default_entry`.
        """
        if "start_graph" in self.model_fields_set:
            return self.start_graph
        return self.default_entry


@dataclass(frozen=True, slots=True)
class Preset:
    """읽어 들인 프리셋: 매니페스트와 그 폴더."""

    manifest: PresetManifest
    directory: Path

    @property
    def id(self) -> str:
        return self.manifest.id

    def resolve(self, relative: str) -> Path:
        """항목 경로를 프리셋 폴더 안의 실제 경로로. 절대 경로·폴더 밖(`..`)이면 `PresetError`."""
        if Path(relative).is_absolute() or "\\" in relative:
            raise PresetError(f"{self.id}: item path must be relative with '/': {relative!r}")
        root = self.directory.resolve()
        target = (root / relative).resolve()
        if not target.is_relative_to(root):
            raise PresetError(f"{self.id}: item path escapes the preset folder: {relative!r}")
        return target


def read_yaml_mapping(path: Path) -> dict[str, Any]:
    """YAML 파일을 dict로 읽는다(안전 로더). 없거나 객체가 아니면 `PresetError`."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PresetError(f"{path.name}: cannot read ({type(exc).__name__})") from exc
    try:
        data = YAML(typ="safe").load(text)
    except Exception as exc:
        raise PresetError(f"{path.name}: invalid YAML ({type(exc).__name__})") from exc
    if not isinstance(data, dict):
        raise PresetError(f"{path.name}: top level must be a mapping")
    return data


def load_preset(directory: str | Path, *, manifest_file: str = MANIFEST_FILE) -> Preset:
    """프리셋 폴더 하나를 읽는다.

    Args:
        directory: 프리셋 폴더(매니페스트가 있는 곳).
        manifest_file: 매니페스트 파일 이름.

    Returns:
        `Preset`. 항목 파일은 아직 읽지 않는다(`apply_preset`/`load_items`가 읽는다).

    Raises:
        PresetError: 매니페스트가 없거나 형식이 틀림.
    """
    folder = Path(directory)
    path = folder / manifest_file
    if not path.is_file():
        raise PresetError(f"{folder.name}: no {manifest_file}")
    try:
        manifest = PresetManifest.model_validate(read_yaml_mapping(path))
    except ValidationError as exc:
        raise PresetError(f"{folder.name}/{manifest_file}: {exc}") from exc
    return Preset(manifest=manifest, directory=folder)
