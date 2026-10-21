"""5R.15 QA: 서버 적용의 의존 순서(뒤섞인 매니페스트·순환)와 연동 모듈이 꺼진 서버."""

from __future__ import annotations

from pathlib import Path

from agent_console_server.testing import API, make_settings, server


def _graph(gid: str, child: str | None) -> str:
    nodes = "  - {id: you, type: user, position: {x: 0, y: 0}}\n"
    edges = ""
    if child:
        nodes += (
            f"  - {{id: sub, type: team, position: {{x: 200, y: 0}}, "
            f"config: {{team_ref: {child}}}}}\n"
        )
        edges = (
            "  - {id: m1, source: {node: you, port: says}, "
            "target: {node: sub, port: in}, kind: message}\n"
        )
    body = edges or "  []\n"
    return f"kind: graph\nid: {gid}\nschema_version: 1\nname: {gid}\nnodes:\n{nodes}edges:\n{body}"


def _preset(root: Path, name: str, graphs: dict[str, str | None]) -> None:
    folder = root / name
    (folder / "graphs").mkdir(parents=True)
    for gid, child in graphs.items():
        (folder / "graphs" / f"{gid}.yaml").write_text(_graph(gid, child), encoding="utf-8")
    items = "\n".join(f"  - graphs/{gid}.yaml" for gid in graphs)
    (folder / "preset.yaml").write_text(
        f"kind: preset\nid: {name}\nschema_version: 1\nname: {name}\nitems:\n{items}\n",
        encoding="utf-8",
    )


def _opts(root: Path) -> dict[str, dict[str, object]]:
    return {"mod-presets": {"directories": [str(root)], "apply_on_start": []}}


def test_scrambled_manifest_applies_children_first_and_cycle_terminates(tmp_path: Path) -> None:
    root = tmp_path / "presets"
    # 매니페스트 순서: 부모 → 중간 → 잎 (가장 나쁜 순서). 순환: loop-a ↔ loop-b.
    _preset(root, "chain", {"top": "mid", "mid": "leaf", "leaf": None})
    _preset(root, "cyc", {"loop-a": "loop-b", "loop-b": "loop-a"})
    with server(make_settings(tmp_path, options=_opts(root))) as client:
        chain = client.post(f"{API}/presets/chain/apply").json()
        order = [i["id"] for i in chain["items"]]
        assert order == ["leaf", "mid", "top"], chain
        cyc = client.post(f"{API}/presets/cyc/apply")
        assert cyc.status_code == 200, cyc.text
        assert {i["id"] for i in cyc.json()["items"]} == {"loop-a", "loop-b"}
        assert {i["action"] for i in cyc.json()["items"]} == {"created"}


def test_link_off_server_still_applies_in_manifest_order(tmp_path: Path) -> None:
    root = tmp_path / "presets"
    _preset(root, "chain", {"top": "mid", "mid": "leaf", "leaf": None})
    settings = make_settings(
        tmp_path,
        modules={
            "disabled": ["link-definitions-teams"],
            "options": _opts(root),
        },
    )
    with server(settings) as client:
        infos = {m["id"]: m for m in client.get(f"{API}/modules").json()}
        assert infos["link-definitions-teams"]["status"] == "disabled"
        applied = client.post(f"{API}/presets/chain/apply").json()
        assert [i["id"] for i in applied["items"]] == ["top", "mid", "leaf"]
        assert {i["action"] for i in applied["items"]} == {"created"}
        assert {g["id"] for g in client.get(f"{API}/graphs").json()} == {"top", "mid", "leaf"}
