"""등록 시점 초기화: `project.yaml`과 `.gitignore`를 없을 때만 만든다."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Unpack

from agent_console_contracts import ProjectManifest

from ._errors import ManifestInvalid
from ._gitignore import default_gitignore_template
from ._manifest import ManifestRecord, read_manifest, write_manifest
from ._space import ProjectSpace, SpaceOptions, build_space

type ManifestState = Literal["created", "adopted", "invalid", "absent"]
"""`created` 새로 씀 · `adopted` 있던 것을 채택 · `invalid` 깨짐(아무것도 쓰지 않음) ·
`absent` 없는데 쓸 수 없어 못 만듦."""
type GitignoreState = Literal["created", "adopted", "skipped"]
"""`created` 새로 씀 · `adopted` 있던 것을 그대로 둠 · `skipped` 쓰지 않음
(깨진 매니페스트나 읽기 전용)."""


@dataclass(frozen=True)
class InitResult:
    """`init_space` 결과.

    Attributes:
        space: 열린 공간(`config_writable`은 실제로 쓰려다 실패한 것까지 반영한 값).
        manifest: 채택하거나 만든 매니페스트. 깨졌거나 못 만들었으면 None.
        manifest_state: `ManifestState`.
        manifest_issue: 깨진 이유(`manifest_state == "invalid"`일 때).
        gitignore_state: `GitignoreState`.
    """

    space: ProjectSpace
    manifest: ManifestRecord | None
    manifest_state: ManifestState
    manifest_issue: ManifestInvalid | None
    gitignore_state: GitignoreState

    @property
    def config_writable(self) -> bool:
        return self.space.config_writable


def init_space(
    folder: str | Path,
    *,
    manifest: ProjectManifest,
    gitignore_template: str | None = None,
    **options: Unpack[SpaceOptions],
) -> InitResult:
    """프로젝트 폴더를 공간으로 등록할 준비를 한다.

    - `project.yaml`이 없으면 `manifest`로 만들고, 있으면 **채택**한다(고치지 않는다).
    - `.gitignore`가 없으면 틀로 만들고, 있으면 그대로 둔다(사용자 파일 보존).
    - 매니페스트가 깨져 있으면 폴더에 아무것도 쓰지 않는다(`manifest_state == "invalid"`).
    - 쓸 수 없는 폴더(읽기 전용 등)는 예외 없이 `config_writable == False`로 돌려준다.

    Args:
        folder: 프로젝트 폴더.
        manifest: 매니페스트가 없을 때 쓸 내용(폴더 id·이름 등).
        gitignore_template: `.gitignore` 틀. 생략하면 패키지 데이터 `gitignore.template`.
        **options: `SpaceOptions`.

    Raises:
        FolderMissing, UnsafeConfigDir, ValueError: `open_space`와 같다.
        SecretRejected: 만들 매니페스트에 평문 비밀이 있다.
    """
    path = Path(folder)
    space = build_space(path, **options)
    try:
        existing = read_manifest(space)
    except ManifestInvalid as exc:
        return InitResult(space, None, "invalid", exc, "skipped")
    state: ManifestState
    if existing is not None:
        state = "adopted"
    elif space.config_writable:
        try:
            existing = write_manifest(space, manifest)
            state = "created"
        except OSError:
            space = build_space(path, writable=False, **options)
            return InitResult(space, None, "absent", None, "skipped")
    else:
        return InitResult(space, None, "absent", None, "skipped")

    git_state: GitignoreState = "adopted"
    try:
        has_file = space.files.read_bytes(space.gitignore_path) is not None
    except OSError:
        has_file = True  # 읽을 수 없는 파일은 건드리지 않는다
    if not has_file:
        if space.config_writable:
            template = gitignore_template or default_gitignore_template()
            try:
                created = space.files.create_bytes(space.gitignore_path, template.encode("utf-8"))
                git_state = "created" if created else "adopted"
            except OSError:
                space = build_space(path, writable=False, **options)
                git_state = "skipped"
        else:
            git_state = "skipped"
    return InitResult(space, existing, state, None, git_state)
