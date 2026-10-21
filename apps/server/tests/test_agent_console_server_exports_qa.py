"""2R.11 QA: 실서버 write 안전(경로 탈출·링크·보호 위치·토큰·빈 roots)과 zip 평문 비밀 없음.

가짜 HOME·임시 폴더만 쓴다.
"""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from typing import Any

import pytest

from agent_console_server.testing import API, TEST_TOKEN, agent_doc, make_settings, server


def tree_hash(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()
    }


def put_agent(client: Any, prompt: str = "안녕") -> None:
    doc = agent_doc("qa-a", "x", system_prompt=prompt)
    assert client.post(f"{API}/agents", json=doc).status_code in (200, 201)


def req(**extra: Any) -> dict[str, Any]:
    return {"exporter": "claude-dir", "items": [{"kind": "agent", "id": "qa-a"}], **extra}


def test_default_roots_empty_and_write_impossible(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        put_agent(client)
        assert client.get(f"{API}/exports/roots").json() == []
        r = client.post(f"{API}/exports/write", json=req(root="any", subdir=""))
        assert r.status_code == 404


def test_write_requires_token_and_roots(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    s = make_settings(tmp_path, options={"mod-exports": {"roots": [{"id": "o", "path": str(out)}]}})
    with server(s, with_token=False) as client:
        assert client.get(f"{API}/exports/roots").status_code == 401
        r = client.post(f"{API}/exports/write", json=req(root="o"))
        assert r.status_code in (401, 403, 404)
        assert not any(out.iterdir())


@pytest.mark.parametrize(
    "subdir",
    ["../escape", "/abs", "a/../../x", "..", "C:/x", "a\\b", "CON", "x/NUL.txt", "a//b"],
)
def test_subdir_escape_rejected(tmp_path: Path, subdir: str) -> None:
    out = tmp_path / "out"
    out.mkdir()
    s = make_settings(tmp_path, options={"mod-exports": {"roots": [{"id": "o", "path": str(out)}]}})
    with server(s) as client:
        put_agent(client)
        r = client.post(f"{API}/exports/write", json=req(root="o", subdir=subdir))
        assert r.status_code == 422, (subdir, r.text)
    assert not any(out.iterdir())
    assert sorted(p.name for p in tmp_path.iterdir() if p.name != "ws") == ["out"]


def test_symlink_dirs_and_files_refused(tmp_path: Path) -> None:
    out = tmp_path / "out"
    outside = tmp_path / "outside"
    out.mkdir()
    outside.mkdir()
    (outside / "keep.txt").write_text("k")
    before = tree_hash(outside)
    os.symlink(outside, out / "link")  # 링크 폴더(정션 대체)
    (out / "real").mkdir()
    os.symlink(outside, out / "real" / ".claude")  # 중간 구성요소 링크
    s = make_settings(tmp_path, options={"mod-exports": {"roots": [{"id": "o", "path": str(out)}]}})
    with server(s) as client:
        put_agent(client)
        assert (
            client.post(f"{API}/exports/write", json=req(root="o", subdir="link")).status_code
            == 422
        )
        assert (
            client.post(f"{API}/exports/write", json=req(root="o", subdir="real")).status_code
            == 422
        )
        # 파일 링크: 대상 파일 자리가 링크
        (out / "p" / ".claude" / "agents").mkdir(parents=True)
        plan = client.post(f"{API}/exports/plan", json=req(root="o", subdir="p")).json()
        rel = plan["files"][0]["path"]
        target = outside / "victim.txt"
        target.write_text("v")
        os.symlink(target, out / "p" / rel)
        r = client.post(
            f"{API}/exports/write", json=req(root="o", subdir="p", on_conflict="overwrite")
        )
        assert r.status_code == 422, r.text
        assert target.read_text() == "v"
    assert tree_hash(outside) == {**before, "victim.txt": b"v"}


def test_root_that_is_symlink_or_claude_home_refused(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".claude" / "agents").mkdir(parents=True)
    (home / ".claude" / "agents" / "o.md").write_text("orig")
    before = tree_hash(home)
    real = tmp_path / "real"
    real.mkdir()
    os.symlink(real, tmp_path / "lnk")
    s = make_settings(
        tmp_path,
        options={
            "mod-imports": {"home": str(home)},
            # 보호 위치 기준 홈은 내보내기 자기 옵션이다(4R.18: 가져오기 home을 읽지 않음).
            "mod-exports": {
                "home": str(home),
                "roots": [
                    {"id": "ch", "path": str(home / ".claude")},
                    {"id": "h", "path": str(home)},
                    {"id": "lnk", "path": str(tmp_path / "lnk")},
                    {"id": "viaLink", "path": str(tmp_path / "real")},
                ],
            },
        },
    )
    with server(s) as client:
        put_agent(client)
        ids = [r["id"] for r in client.get(f"{API}/exports/roots").json()]
        assert "ch" not in ids
        assert "lnk" not in ids
        for root, sub in [("ch", ""), ("ch", "agents"), ("h", ""), ("h", ".claude"), ("lnk", "")]:
            r = client.post(f"{API}/exports/write", json=req(root=root, subdir=sub))
            assert r.status_code in (404, 422), (root, sub, r.text)
        # 대소문자 우회
        r = client.post(
            f"{API}/exports/write", json=req(root="h", subdir=".CLAUDE", on_conflict="overwrite")
        )
        assert r.status_code in (404, 422)
    assert tree_hash(home) == before
    assert not any(real.iterdir())


def test_zip_has_no_plain_secret(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        put_agent(client, "키는 ghp_abcdefghijklmnopqrstuvwxyz0123456789 이다")
        r = client.post(f"{API}/exports/archive", json=req())
        # 평문 비밀이 있으면 거부하거나 가려야 한다
        if r.status_code == 200:
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                for n in z.namelist():
                    assert b"ghp_abcdefghijklmnop" not in z.read(n), n
        else:
            assert r.status_code == 422, r.text
        assert TEST_TOKEN.encode() not in r.content
