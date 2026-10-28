"""마크다운 zip 내보내기·가져오기(5.7R.11).

왕복, 충돌 정책, 미리보기, 경로 공격·zip 폭탄·비밀 거부.
"""

from __future__ import annotations

import doctest
import io
import json
import stat
import struct
import zipfile
from types import ModuleType
from typing import Any

import pytest

from agent_console_contracts.memory import MemoryEntry, MemoryScopeRef
from agent_console_memory import (
    EntryScanner,
    InMemoryMemoryStore,
    InvalidArchiveError,
    MemoryPolicy,
    MemorySecretGuard,
    MemoryTransferCodes,
    MemoryTransferLimits,
    TooLargeError,
    _transfer,
    entry_archive_path,
    export_markdown,
    import_markdown,
    iter_entries,
    parse_archive_path,
    parse_markdown,
    render_markdown,
    write_markdown_archive,
)
from agent_console_memory.testing import FakeClock, _entries, sample_entry, user_author

SECRET = "sk-ant-api03-" + "A1b2C3d4E5f6G7h8" * 3
NOTES = MemoryScopeRef(kind="notes", id="g1")
SHARED = MemoryScopeRef(kind="board", id="")
ODD = MemoryScopeRef(kind="journal", id="g1/agent a")
UNDERSCORE = MemoryScopeRef(kind="journal", id="_")
DOTS = MemoryScopeRef(kind="journal", id="..")


def _store(**kw: Any) -> InMemoryMemoryStore:
    return InMemoryMemoryStore(clock=FakeClock(1_700_000_000.0, step=1.0), **kw)


def _shape(store: InMemoryMemoryStore) -> list[tuple[Any, ...]]:
    out = []
    for summary in iter_entries(store):
        entry = store.get(summary.id)
        assert entry is not None
        out.append(
            (
                entry.scope.kind,
                entry.scope.id,
                entry.key,
                entry.content,
                tuple(entry.tags),
                entry.pinned,
                entry.archived,
                entry.content_type,
            )
        )
    return sorted(out)


def _zip(files: dict[str, str | bytes], **infos: Any) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_DEFLATED
            for attr, value in infos.get(name, {}).items():
                setattr(info, attr, value)
            archive.writestr(info, data.encode("utf-8") if isinstance(data, str) else data)
    return buffer.getvalue()


def _filled() -> InMemoryMemoryStore:
    store = _store()
    me = user_author()
    store.write(NOTES, "결정/api-버전", "v2로 고정\n", author=me, tags=["결정", "api"])
    store.write(NOTES, "회의/10-28", "---\n머리처럼 보이는 본문\n---\n끝", author=me, pinned=True)
    store.write(SHARED, "공지", "", author=me)
    store.write(ODD, "a/b/c", "  앞뒤 공백  ", author=me, content_type="application/json")
    store.write(UNDERSCORE, "u", "밑줄 범위", author=me)
    store.write(DOTS, "d", "점 범위", author=me)
    archived = store.write(NOTES, "옛/기록", "보관된 기록", author=me, tags=["tmp"]).entry
    store.archive(archived.id, author=me)
    gone = store.write(NOTES, "지운/기록", "지운 기록", author=me).entry
    store.delete(gone.id, author=me)
    return store


# ---- 왕복 ------------------------------------------------------------------------------------


def test_round_trip_into_empty_store_gives_same_entries() -> None:
    source = _filled()
    data = export_markdown(source)
    target = _store()
    result = import_markdown(target, data)
    assert (result.created, result.skipped, result.errors) == (7, 0, [])
    assert _shape(target) == _shape(source)
    assert all(s.version >= 1 for s in iter_entries(target))
    any_entry = next(iter_entries(target))
    assert any_entry.created_by.kind == "system"


def test_export_layout_and_front_matter() -> None:
    data = export_markdown(_filled())
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = sorted(archive.namelist())
        sample = archive.read("notes/g1/결정/api-버전.md").decode("utf-8")
    assert names == sorted(
        [
            "notes/g1/결정/api-버전.md",
            "notes/g1/회의/10-28.md",
            "notes/g1/옛/기록.md",
            "board/_/공지.md",
            "journal/g1%2Fagent%20a/a/b/c.md",
            "journal/%5F/u.md",
            "journal/%2E%2E/d.md",
        ]
    )
    assert "지운" not in "".join(names)
    meta, body = parse_markdown(sample)
    assert body == "v2로 고정\n"
    assert meta["tags"] == ["결정", "api"]
    assert set(meta) == {
        "id",
        "content_type",
        "tags",
        "pinned",
        "archived",
        "version",
        "created_at",
        "created_by",
        "updated_at",
        "updated_by",
    }


def test_export_scope_filter_and_archived_switch() -> None:
    store = _filled()
    only = export_markdown(store, [SHARED])
    with zipfile.ZipFile(io.BytesIO(only)) as archive:
        assert archive.namelist() == ["board/_/공지.md"]
    live = export_markdown(store, include_archived=False)
    with zipfile.ZipFile(io.BytesIO(live)) as archive:
        assert "notes/g1/옛/기록.md" not in archive.namelist()
    target = io.BytesIO()
    assert write_markdown_archive(store, target) == 7


def test_render_and_parse_are_inverse() -> None:
    entry = sample_entry(content="---\n본문 안 구분선\n---\n", tags=["a"], pinned=True)
    meta, body = parse_markdown(render_markdown(entry))
    assert body == entry.content
    assert (meta["tags"], meta["pinned"], meta["id"]) == (["a"], True, entry.id)
    assert parse_archive_path(entry_archive_path(ODD, "x/y")) == (ODD, "x/y")


def test_plain_markdown_without_front_matter_is_imported() -> None:
    store = _store()
    result = import_markdown(store, _zip({"notes/g1/메모.md": "그냥 본문"}))
    assert result.created == 1
    entry = store.find(NOTES, "메모")
    assert entry is not None
    assert entry.content == "그냥 본문"
    assert entry.tags == []


def test_file_object_input() -> None:
    store = _store()
    assert import_markdown(store, io.BytesIO(export_markdown(_filled()))).created == 7


# ---- 충돌 정책·미리보기 ------------------------------------------------------------------------


def _one(content: str, **meta: Any) -> bytes:
    front = "".join(f"{k}: {json.dumps(v, ensure_ascii=False)}\n" for k, v in meta.items())
    return _zip({"notes/g1/k.md": f"---\n{front}---\n{content}"})


def test_policy_skip_overwrite_rename() -> None:
    store = _store()
    first = store.write(NOTES, "k", "원래", author=user_author(), tags=["old"]).entry

    skipped = import_markdown(store, _one("새 본문"), policy="skip")
    assert (skipped.skipped, skipped.created) == (1, 0)
    assert store.find(NOTES, "k") == first

    over = import_markdown(store, _one("새 본문", tags=["new"], archived=True), policy="overwrite")
    assert over.overwritten == 1
    now = store.find(NOTES, "k")
    assert now is not None
    assert (now.id, now.content, now.tags, now.archived) == (first.id, "새 본문", ["new"], True)
    assert [v.op for v in store.history(first.id)] == ["create", "update", "archive"]
    assert now.updated_by.kind == "system"

    renamed = import_markdown(store, _one("다른 본문"), policy="rename")
    renamed2 = import_markdown(store, _one("또 다른 본문"), policy="rename")
    assert (renamed.renamed, renamed2.renamed) == (1, 1)
    assert store.find(NOTES, "k (2)") is not None
    third = store.find(NOTES, "k (3)")
    assert third is not None
    assert third.content == "또 다른 본문"

    custom = import_markdown(store, _one("x"), policy="rename", rename_format="{key}-copy{n}")
    assert custom.renamed == 1
    assert store.find(NOTES, "k-copy2") is not None


def test_overwrite_keeps_fields_missing_from_front_matter() -> None:
    store = _store()
    store.write(NOTES, "k", "원래", author=user_author(), tags=["keep"], pinned=True)
    import_markdown(store, _zip({"notes/g1/k.md": "머리 없는 새 본문"}), policy="overwrite")
    entry = store.find(NOTES, "k")
    assert entry is not None
    assert (entry.content, entry.tags, entry.pinned) == ("머리 없는 새 본문", ["keep"], True)


def test_dry_run_counts_like_real_run_and_writes_nothing() -> None:
    data = export_markdown(_filled())
    target = _store()
    target.write(NOTES, "결정/api-버전", "이미 있음", author=user_author())
    before = _shape(target)
    for policy in ("skip", "overwrite", "rename"):
        preview = import_markdown(target, data, policy=policy, dry_run=True)
        assert preview.dry_run
        assert _shape(target) == before
        copy = _store()
        copy.write(NOTES, "결정/api-버전", "이미 있음", author=user_author())
        real = import_markdown(copy, data, policy=policy)
        assert not real.dry_run
        assert preview.model_dump(exclude={"dry_run"}) == real.model_dump(exclude={"dry_run"})


def test_rename_dry_run_reserves_names_inside_archive() -> None:
    store = _store()
    store.write(NOTES, "k", "a", author=user_author())
    store.write(NOTES, "k (2)", "b", author=user_author())
    data = _zip({"notes/g1/k.md": "c", "notes/g1/k (3).md": "d"})
    preview = import_markdown(store, data, policy="rename", dry_run=True)
    real = import_markdown(store, data, policy="rename")
    # k → "k (3)"(빈 이름), 그다음 "k (3)"은 방금 쓴 이름과 겹쳐 "k (3) (2)".
    assert (real.renamed, real.created, real.errors) == (2, 0, [])
    assert preview.model_dump(exclude={"dry_run"}) == real.model_dump(exclude={"dry_run"})
    assert store.find(NOTES, "k (3) (2)") is not None


def test_unknown_policy_is_rejected() -> None:
    with pytest.raises(ValueError, match="정책"):
        import_markdown(_store(), _one("x"), policy="merge")  # type: ignore[arg-type]


# ---- 안전: 경로 공격 -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "../notes/g1/x.md",
        "notes/../../x.md",
        "notes/g1/../x.md",
        "notes/./g1/x.md",
        "/notes/g1/x.md",
        "notes\\g1\\x.md",
        "C:notes/g1/x.md",
        "notes//g1/x.md",
        "notes/g1/x\x01.md",
    ],
)
def test_path_attacks_are_rejected_but_safe_files_still_import(name: str) -> None:
    store = _store()
    data = _zip({name: "공격", "notes/g1/ok.md": "정상"})
    result = import_markdown(store, data)
    assert result.created == 1
    assert [(e.code) for e in result.errors] == [MemoryTransferCodes.UNSAFE_PATH]
    assert [s.key for s in iter_entries(store)] == ["ok"]


def test_symlink_member_is_rejected() -> None:
    link = {"external_attr": (stat.S_IFLNK | 0o777) << 16}
    data = _zip(
        {"notes/g1/link.md": "/etc/passwd", "notes/g1/ok.md": "정상"}, **{"notes/g1/link.md": link}
    )
    result = import_markdown(_store(), data)
    assert [e.code for e in result.errors] == [MemoryTransferCodes.UNSAFE_PATH]
    assert result.created == 1


# ---- 안전: 크기·zip 폭탄 ------------------------------------------------------------------------


def test_zip_bomb_member_rejects_whole_archive_without_writing() -> None:
    store = _store()
    bomb = _zip({"notes/g1/ok.md": "정상", "notes/g1/bomb.md": b"\0" * (8 * 1024 * 1024)})
    assert len(bomb) < 64 * 1024
    with pytest.raises(TooLargeError) as caught:
        import_markdown(store, bomb)
    assert caught.value.limit == "max_file_bytes"
    assert caught.value.code == "memory.too_large"
    assert list(iter_entries(store)) == []


def test_total_size_file_count_and_archive_size_limits() -> None:
    many = _zip({f"notes/g1/k{i}.md": "x" * 1000 for i in range(20)})
    with pytest.raises(TooLargeError) as total:
        import_markdown(_store(), many, limits=MemoryTransferLimits(max_total_bytes=10_000))
    assert total.value.limit == "max_total_bytes"
    with pytest.raises(TooLargeError) as count:
        import_markdown(_store(), many, limits=MemoryTransferLimits(max_files=10))
    assert count.value.limit == "max_files"
    with pytest.raises(TooLargeError) as size:
        import_markdown(_store(), many, limits=MemoryTransferLimits(max_archive_bytes=100))
    assert size.value.limit == "max_archive_bytes"
    # 같은 묶음이 기본 상한에서는 들어간다.
    assert import_markdown(_store(), many).created == 20


def _lie_about_size(data: bytes, name: str, fake_size: int) -> bytes:
    """zip 머리(지역·중앙)의 풀린 크기를 `fake_size`로 바꾼다(폭탄이 크기를 속이는 경우)."""
    raw = bytearray(data)
    encoded = name.encode("utf-8")
    local = raw.find(b"PK\x03\x04")
    while local != -1:
        name_len = struct.unpack_from("<H", raw, local + 26)[0]
        if bytes(raw[local + 30 : local + 30 + name_len]) == encoded:
            struct.pack_into("<I", raw, local + 22, fake_size)
        local = raw.find(b"PK\x03\x04", local + 4)
    central = raw.find(b"PK\x01\x02")
    while central != -1:
        name_len = struct.unpack_from("<H", raw, central + 28)[0]
        if bytes(raw[central + 46 : central + 46 + name_len]) == encoded:
            struct.pack_into("<I", raw, central + 24, fake_size)
        central = raw.find(b"PK\x01\x02", central + 4)
    return bytes(raw)


def test_member_lying_about_its_size_is_not_imported() -> None:
    honest = _zip({"notes/g1/liar.md": "a" * 100_000, "notes/g1/ok.md": "정상"})
    lying = _lie_about_size(honest, "notes/g1/liar.md", 10)
    store = _store()
    result = import_markdown(store, lying)
    assert [e.code for e in result.errors] == [MemoryTransferCodes.INVALID_FILE]
    assert [s.key for s in iter_entries(store)] == ["ok"]


def test_not_a_zip() -> None:
    with pytest.raises(InvalidArchiveError) as caught:
        import_markdown(_store(), b"not a zip at all")
    assert caught.value.code == "validation_failed"


# ---- 안전: 비밀 검사 -----------------------------------------------------------------------------


def test_secret_content_is_rejected_and_never_echoed() -> None:
    store = _store()
    data = _zip(
        {
            "notes/g1/leak.md": f"키: {SECRET}",
            f"notes/g1/{SECRET}.md": "키 이름에 비밀",
            "notes/g1/tagged.md": f"---\ntags: [{SECRET}]\n---\n본문",
            "notes/g1/ok.md": "정상",
        }
    )
    for dry_run in (True, False):
        result = import_markdown(store, data, dry_run=dry_run)
        assert sorted(e.code for e in result.errors) == ["memory.secret_rejected"] * 3
        assert result.created == 1
        assert SECRET not in result.model_dump_json()
    assert [s.key for s in iter_entries(store)] == ["ok"]


def test_redact_mode_stores_redacted_content() -> None:
    store = _store(policy=MemoryPolicy(secrets=MemorySecretGuard(mode="redact")))
    result = import_markdown(store, _zip({"notes/g1/leak.md": f"키: {SECRET}"}))
    assert result.created == 1
    entry = store.find(NOTES, "leak")
    assert isinstance(entry, MemoryEntry)
    assert SECRET not in entry.content


# ---- 파일 문제 ---------------------------------------------------------------------------------


def test_file_problems_are_reported_per_file() -> None:
    store = _store()
    files: dict[str, str | bytes] = {
        "notes/g1/bad-yaml.md": "---\ntags: [unclosed\n---\n본문",
        "notes/g1/no-close.md": "---\ntags: []\n본문",
        "notes/g1/bad-tags.md": "---\ntags: 3\n---\n본문",
        "notes/g1/bad-type.md": "---\ncontent_type: '; rm -rf'\n---\n본문",
        "notes/g1/bad-flag.md": "---\npinned: yes please\n---\n본문",
        "notes/g1/latin1.md": "é".encode("latin-1"),
        "notes/k.md": "마디 부족",
        "Bad Kind/g1/k.md": "범위 종류 이름 틀림",
        "notes/%ZZ%/k.md": "잘못된 인코딩은 글자 그대로",
        "notes/g1/readme.txt": "md 아님",
        "notes/g1/sub/": "",
        "notes/g1/ok.md": "정상",
    }
    result = import_markdown(store, _zip(files))
    codes = {e.path: e.code for e in result.errors}
    assert codes == {
        "notes/g1/bad-yaml.md": MemoryTransferCodes.INVALID_FILE,
        "notes/g1/no-close.md": MemoryTransferCodes.INVALID_FILE,
        "notes/g1/bad-tags.md": MemoryTransferCodes.INVALID_FILE,
        "notes/g1/bad-type.md": MemoryTransferCodes.INVALID_FILE,
        "notes/g1/bad-flag.md": MemoryTransferCodes.INVALID_FILE,
        "notes/g1/latin1.md": MemoryTransferCodes.INVALID_FILE,
        "notes/k.md": MemoryTransferCodes.INVALID_FILE,
        "Bad Kind/g1/k.md": MemoryTransferCodes.INVALID_FILE,
        "notes/g1/readme.txt": MemoryTransferCodes.UNSUPPORTED,
    }
    assert result.created == 2  # ok.md + 글자 그대로 읽힌 %ZZ% 범위
    assert all("본문" not in e.message for e in result.errors)


def test_duplicate_scope_and_key_inside_archive() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("notes/g1/k.md", "첫째")
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr("notes/g1/k.md", "둘째")
    store = _store()
    dup = import_markdown(store, buffer.getvalue())
    assert [e.code for e in dup.errors] == [MemoryTransferCodes.DUPLICATE]
    entry = store.find(NOTES, "k")
    assert entry is not None
    assert entry.content == "첫째"


def test_store_limits_become_problems() -> None:
    store = _store(policy=MemoryPolicy())
    long_key = "k" * 300
    data = _zip({f"notes/g1/{long_key}.md": "x", "notes/g1/big.md": "x" * (70 * 1024)})
    result = import_markdown(store, data)
    assert sorted(e.code for e in result.errors) == ["memory.invalid_key", "memory.too_large"]


@pytest.mark.parametrize("module", [_transfer, _entries])
def test_module_doctests(module: ModuleType) -> None:
    result = doctest.testmod(module, optionflags=doctest.ELLIPSIS)
    assert result.attempted > 0
    assert result.failed == 0


class _SearchOnly:
    """`search`·`get`만 내놓는 감싸기(`EntryScanner` 없는 저장소 길)."""

    def __init__(self, store: InMemoryMemoryStore) -> None:
        self._store = store
        self.policy = store.policy

    def __getattr__(self, name: str) -> Any:
        if name == "scan_entries":
            raise AttributeError(name)
        return getattr(self._store, name)


def test_export_without_scanner_matches_scanner_path() -> None:
    store = _filled()
    assert isinstance(store, EntryScanner)
    plain = _SearchOnly(store)
    assert not isinstance(plain, EntryScanner)

    def contents(data: bytes) -> dict[str, bytes]:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return {name: archive.read(name) for name in archive.namelist()}

    fast = contents(export_markdown(store))
    slow = contents(export_markdown(plain))
    assert fast == slow
    assert len(fast) == 7
    scoped = list(iter_entries(plain, scopes=[NOTES], include_archived=False, page_size=1))
    assert sorted(e.key for e in scoped) == ["결정/api-버전", "회의/10-28"]
