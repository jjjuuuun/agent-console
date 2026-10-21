"""정의 종류 `resource`: 본문 파일 동반 저장·삭제, 경로 탈출 거부, 해시에 본문 포함."""

import os
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts import Resource
from agent_console_store import (
    DefinitionCorrupt,
    DefinitionStore,
    FileDefinitionStore,
    InvalidContentPath,
    NotFound,
    VersionConflict,
    VersionRequired,
)


def doc(id: str = "team-md", file: str | None = "content.md", **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "kind": "resource",
        "id": id,
        "type": "instruction",
        "name": "팀 지침",
        "config": {"title": "CLAUDE.md"},
        **extra,
    }
    if file is not None:
        result["content"] = {"file": file, "media_type": "text/markdown"}
    return result


def test_resource_kind_is_registered_by_default(definitions: DefinitionStore) -> None:
    assert "resource" in definitions.kinds()


def test_create_without_body_then_write_content(definitions: DefinitionStore) -> None:
    created = definitions.create("resource", doc())
    assert definitions.read_content("resource", "team-md") is None  # 파일은 아직 없다
    written = definitions.write_content(
        "resource", "team-md", "# 지침\n한글".encode(), expected_version=created.version_hash
    )
    assert written.version_hash != created.version_hash
    assert definitions.read_content("resource", "team-md") == "# 지침\n한글".encode()
    assert written.document == created.document  # 문서는 그대로, 본문만 바뀜
    assert definitions.get("resource", "team-md").version_hash == written.version_hash


def test_version_hash_includes_body(definitions: DefinitionStore) -> None:
    v0 = definitions.create("resource", doc())
    v1 = definitions.write_content("resource", "team-md", b"A", expected_version=v0.version_hash)
    v2 = definitions.write_content("resource", "team-md", b"B", expected_version=v1.version_hash)
    v3 = definitions.write_content("resource", "team-md", b"A", expected_version=v2.version_hash)
    assert len({v0.version_hash, v1.version_hash, v2.version_hash}) == 3
    assert v3.version_hash == v1.version_hash  # 같은 문서 + 같은 본문 = 같은 버전
    hashes = {v.version_hash for v in definitions.list_versions("resource", "team-md")}
    assert {v0.version_hash, v1.version_hash, v2.version_hash} <= hashes


def test_write_content_needs_matching_if_match(definitions: DefinitionStore) -> None:
    created = definitions.create("resource", doc())
    with pytest.raises(VersionRequired):
        definitions.write_content("resource", "team-md", b"x")
    with pytest.raises(VersionConflict) as exc:
        definitions.write_content("resource", "team-md", b"x", expected_version="stale")
    assert exc.value.details.current_version_hash == created.version_hash
    assert definitions.read_content("resource", "team-md") is None  # 실패하면 쓰지 않는다
    with pytest.raises(NotFound):
        definitions.write_content("resource", "nope", b"x", expected_version="h")


def test_save_document_picks_up_existing_body_in_hash(definitions: DefinitionStore) -> None:
    created = definitions.create("resource", doc())
    withbody = definitions.write_content(
        "resource", "team-md", b"body", expected_version=created.version_hash
    )
    saved = definitions.save(
        "resource", doc(description="설명"), expected_version=withbody.version_hash
    )
    assert definitions.read_content("resource", "team-md") == b"body"
    assert saved.version_hash != withbody.version_hash
    assert definitions.get("resource", "team-md").version_hash == saved.version_hash


def test_write_content_can_set_the_file_name_and_move_it(definitions: DefinitionStore) -> None:
    created = definitions.create("resource", doc(file=None))
    with pytest.raises(InvalidContentPath):
        definitions.write_content(
            "resource", "team-md", b"x", expected_version=created.version_hash
        )
    first = definitions.write_content(
        "resource", "team-md", b"x", file="notes/a.md", expected_version=created.version_hash
    )
    assert first.document["content"] == {"file": "notes/a.md"}
    moved = definitions.write_content(
        "resource",
        "team-md",
        b"y",
        file="b.md",
        media_type="text/markdown",
        expected_version=first.version_hash,
    )
    assert moved.document["content"] == {"file": "b.md", "media_type": "text/markdown"}
    assert definitions.read_content("resource", "team-md") == b"y"


def test_summary_has_type_and_has_content(definitions: DefinitionStore) -> None:
    definitions.create("resource", doc("a"))
    definitions.create("resource", doc("b", file=None))
    by_id = {s.id: s for s in definitions.summaries("resource")}
    assert by_id["a"].has_content
    assert not by_id["b"].has_content
    assert by_id["a"].extra == {"type": "instruction"}


def test_delete_removes_body_and_keeps_history(definitions: DefinitionStore) -> None:
    created = definitions.create("resource", doc())
    written = definitions.write_content(
        "resource", "team-md", b"x", expected_version=created.version_hash
    )
    definitions.delete("resource", "team-md")
    with pytest.raises(NotFound):
        definitions.get("resource", "team-md")
    definitions.create("resource", doc())  # 같은 id를 다시 만들면 이전 본문이 남아 있지 않다
    assert definitions.read_content("resource", "team-md") is None
    assert definitions.get_version("resource", "team-md", written.version_hash) is not None


BAD_PATHS = [
    "../x.md",
    "a/../../x.md",
    "/etc/passwd",
    "C:/x.md",
    "C:\\x.md",
    "a\\b.md",
    "",
    ".",
    "a//b",
    "a/",
    "a/./b",
    "x\x00y",
]


@pytest.mark.parametrize("bad", BAD_PATHS)
def test_content_path_escape_is_rejected_everywhere(definitions: DefinitionStore, bad: str) -> None:
    with pytest.raises(InvalidContentPath):
        definitions.create("resource", doc(file=bad))
    created = definitions.create("resource", doc())
    with pytest.raises(InvalidContentPath):
        definitions.save("resource", doc(file=bad), expected_version=created.version_hash)
    with pytest.raises(InvalidContentPath):
        definitions.write_content(
            "resource", "team-md", b"x", file=bad, expected_version=created.version_hash
        )


def test_non_mapping_content_is_rejected(definitions: DefinitionStore) -> None:
    with pytest.raises(InvalidContentPath):
        definitions.create("resource", {**doc(file=None), "content": "../x"})


def test_resource_model_validation_still_applies(definitions: DefinitionStore) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        definitions.create("resource", {"id": "x", "name": "no type"})
    stored = definitions.create("resource", doc("ok"))
    assert stored.model(Resource).content is not None


# ---- 파일 저장소 전용 ---------------------------------------------------------
def test_body_lives_next_to_the_definition_file(tmp_path: Path) -> None:
    store = FileDefinitionStore(tmp_path)
    created = store.create("resource", doc())
    store.write_content("resource", "team-md", b"hi", expected_version=created.version_hash)
    assert (tmp_path / "resources" / "team-md.yaml").is_file()
    assert (tmp_path / "resources" / "team-md" / "content.md").read_bytes() == b"hi"


def test_delete_removes_body_files_but_not_untracked_ones(tmp_path: Path) -> None:
    """여러 파일 종류(v3)에서 본문 폴더의 파일은 모두 정의의 본문이다. 이 저장소가 다루지 않는
    것(링크, 만들 수 없는 이름)만 건드리지 않는다."""
    store = FileDefinitionStore(tmp_path)
    created = store.create("resource", doc(file="sub/content.md"))
    store.write_content("resource", "team-md", b"hi", expected_version=created.version_hash)
    folder = tmp_path / "resources" / "team-md"
    (folder / "mine.txt").write_text("본문 폴더의 파일", encoding="utf-8")
    odd = folder / "odd:name.txt"  # 리눅스에서만 만들 수 있는 이름
    odd.write_text("건드리지 않음", encoding="utf-8")
    store.delete("resource", "team-md")
    assert not (folder / "sub").exists()
    assert not (folder / "mine.txt").exists()
    assert odd.read_text(encoding="utf-8") == "건드리지 않음"
    assert not (tmp_path / "resources" / "team-md.yaml").exists()


def test_delete_cleans_up_folder_when_nothing_else_is_there(tmp_path: Path) -> None:
    store = FileDefinitionStore(tmp_path)
    created = store.create("resource", doc())
    store.write_content("resource", "team-md", b"hi", expected_version=created.version_hash)
    store.delete("resource", "team-md")
    assert not (tmp_path / "resources" / "team-md").exists()


def test_hand_edited_body_changes_the_version_and_is_snapshotted(tmp_path: Path) -> None:
    store = FileDefinitionStore(tmp_path)
    created = store.create("resource", doc())
    first = store.write_content("resource", "team-md", b"a", expected_version=created.version_hash)
    (tmp_path / "resources" / "team-md" / "content.md").write_bytes(b"edited by hand!")
    now = store.get("resource", "team-md")
    assert now.version_hash != first.version_hash
    assert store.get_version("resource", "team-md", now.version_hash).message == "외부 변경 감지"


def test_hand_edited_escaping_path_is_corrupt_not_read(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("비밀", encoding="utf-8")
    folder = tmp_path / "ws" / "resources"
    folder.mkdir(parents=True)
    (folder / "evil.yaml").write_text(
        "id: evil\ntype: instruction\nname: e\ncontent: {file: ../../../secret.txt}\n",
        encoding="utf-8",
    )
    store = FileDefinitionStore(tmp_path / "ws")
    with pytest.raises(DefinitionCorrupt):
        store.get("resource", "evil")
    with pytest.raises(DefinitionCorrupt):
        store.read_content("resource", "evil")
    assert store.summaries("resource") == []  # 목록에서는 건너뛴다
    store.delete("resource", "evil")  # 삭제는 되지만 밖의 파일은 건드리지 않는다
    assert secret.read_text(encoding="utf-8") == "비밀"


@pytest.mark.skipif(os.name == "nt", reason="심볼릭 링크 권한")
def test_symlink_pointing_outside_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("비밀", encoding="utf-8")
    store = FileDefinitionStore(tmp_path / "ws")
    created = store.create("resource", doc())
    folder = tmp_path / "ws" / "resources" / "team-md"
    folder.mkdir(parents=True)
    try:
        (folder / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink not permitted")
    with pytest.raises(InvalidContentPath):
        store.write_content(
            "resource",
            "team-md",
            b"x",
            file="link/secret.txt",
            expected_version=created.version_hash,
        )
    assert (outside / "secret.txt").read_text(encoding="utf-8") == "비밀"
