"""공간 고르기(design §6R.4, §6R.18 Q2): ``sdd.spaces``가 있으면 ``?project=``가 그 공간, 없으면 409
``sdd.spaces_unavailable``(단독 루트로 새지 않음), 모르는 공간 404, 쓰기 불가 공간·폴더 기준
경로."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_console_mod_sdd.testing import SimpleSpace, spaces_module
from agent_console_sdd import LocalSpecFiles

API = "/api/v1"


def test_project_without_spaces_port_is_409_and_leaves_root_alone(tmp_path: Path, kit: Any) -> None:
    with kit.client_for(kit.make_assembly(tmp_path)) as client:
        made = client.post(f"{API}/sdd/specs?project=a", json={"name": "X"})
        assert made.status_code == 409
        assert made.json()["error"]["code"] == "sdd.spaces_unavailable"
        assert made.json()["error"]["details"] == {"project_id": "a"}
        assert client.get(f"{API}/sdd/info?project=a").status_code == 409
    assert not (tmp_path / "ws" / "sdd").exists()


def test_space_store_files_and_spec_root(tmp_path: Path, kit: Any) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    store = kit.spec_store(folder / ".cfg")
    kit.write_template(store)
    space = SimpleSpace(store=store, files=LocalSpecFiles(folder), config_dir=".cfg")
    readonly = SimpleSpace(store=kit.spec_store(tmp_path / "ro"), config_writable=False)
    assembly = kit.make_assembly(tmp_path, spaces_module({"a": space, "ro": readonly}))
    with kit.client_for(assembly) as client:
        info = client.get(f"{API}/sdd/info?project=a").json()
        assert info["spec_root"] == ".cfg/specs"
        assert info["capabilities"]["import_export"] is True
        ro = client.get(f"{API}/sdd/info?project=ro").json()
        assert ro["writable"] is False
        assert ro["capabilities"]["import_export"] is False
        assert client.get(f"{API}/sdd/info?project=zz").status_code == 404

        made = client.post(f"{API}/sdd/specs?project=a", json={"name": "P", "template": "flow"})
        assert made.status_code == 201, made.text
        assert made.json()["directory"] == ".cfg/specs/p"
        assert (folder / ".cfg" / "specs" / "p" / "tasks.md").is_file()
        assert client.get(f"{API}/sdd/specs").json() == []  # 단독 루트와 섞이지 않는다
        assert [s["id"] for s in client.get(f"{API}/sdd/specs?project=a").json()] == ["p"]
        variables = client.get(f"{API}/sdd/specs/p/variables?project=a").json()
        assert any(v["name"] == "spec_dir" for v in variables)

        # 폴더 안 파일 목록·가져오기·내보내기(저장소 폴더는 예약)
        (folder / "docs").mkdir()
        (folder / "docs" / "plan.md").write_text("# 계획\n- [ ] 1 하나\n", encoding="utf-8")
        (folder / "docs" / ".hidden.md").write_text("x", encoding="utf-8")
        listing = client.get(f"{API}/sdd/import/files?project=a&path=docs").json()
        assert [(f["name"], f["title_guess"]) for f in listing["files"]] == [("plan.md", "계획")]
        assert client.get(f"{API}/sdd/import/files?project=a&path=.cfg").status_code == 422
        assert client.get(f"{API}/sdd/import/files?project=a&path=../x").status_code == 422
        imported = client.post(
            f"{API}/sdd/specs/import?project=a",
            json={"name": "Imported", "files": ["docs/plan.md"]},
        )
        assert imported.status_code == 201, imported.text
        assert [t["key"] for t in imported.json()["index"]["tasks"]] == []  # 역할 없음
        exported = client.post(
            f"{API}/sdd/specs/p/export?project=a", json={"to_dir": "out", "overwrite": False}
        )
        assert exported.status_code == 200, exported.text
        assert "tasks.md" in exported.json()["written"]
        assert (folder / "out" / "tasks.md").is_file()
        refused = client.post(
            f"{API}/sdd/specs/p/export?project=a", json={"to_dir": ".cfg/x", "overwrite": True}
        )
        assert refused.status_code == 422
        no_files = client.post(
            f"{API}/sdd/specs/import?project=ro", json={"name": "N", "files": ["a.md"]}
        )
        assert no_files.status_code == 409
