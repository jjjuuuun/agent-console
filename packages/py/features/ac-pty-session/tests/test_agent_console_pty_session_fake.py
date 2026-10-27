"""PtySession을 FakePty로: 읽기·쓰기·키·대기·종료(유예 뒤 강제)."""

from __future__ import annotations

import pytest

from agent_console_pty_session import (
    FakePty,
    FakePtySpawner,
    FakeSpawn,
    PtyClosedError,
    PtySession,
)


async def test_spawn_records_arguments() -> None:
    fake = FakePty()
    session = await PtySession.spawn(
        ["cli", "auth"], env={"A": "1"}, cwd="/work", cols=400, rows=40, spawner=fake.spawn
    )
    try:
        assert fake.spawns == [FakeSpawn(("cli", "auth"), {"A": "1"}, "/work", 400, 40)]
        assert session.argv == ("cli", "auth")
        assert session.pid == 4242
    finally:
        await session.terminate(0.1)


async def test_output_and_changes() -> None:
    fake = FakePty()
    async with await PtySession.spawn(["cli"], spawner=fake.spawn) as session:
        v0 = session.version
        fake.emit("\x1b[1mhello\x1b[0m\r\n")
        v1 = await session.wait_changed(v0, 2.0)
        assert v1 > v0
        assert session.screen_lines() == ["hello"]
        chunk = session.text_since(0)
        assert chunk.text == "hello\n"
        assert session.text_offset == chunk.offset


async def test_wait_changed_times_out_without_output() -> None:
    fake = FakePty()
    async with await PtySession.spawn(["cli"], spawner=fake.spawn) as session:
        assert await session.wait_changed(session.version, 0.05) == session.version


async def test_input_reaction_script() -> None:
    def react(pty: FakePty, text: str) -> None:
        if text == "\r":
            pty.emit("Login successful\r\n")
            pty.exit(0)

    fake = FakePty(output="Paste code > ", on_input=react)
    async with await PtySession.spawn(["cli"], spawner=fake.spawn) as session:
        session.write("CODE-1")
        session.send_key("enter")
        assert await session.wait_exit(2.0) == 0
        assert session.screen_lines()[-1] == "Paste code > Login successful"
        assert fake.inputs == ["CODE-1", "\r"]
        assert session.output_ended
        with pytest.raises(PtyClosedError):
            session.write("late")


async def test_unknown_key_raises() -> None:
    fake = FakePty()
    async with await PtySession.spawn(["cli"], spawner=fake.spawn) as session:
        with pytest.raises(KeyError):
            session.send_key("f13")


async def test_terminate_polite() -> None:
    fake = FakePty()
    session = await PtySession.spawn(["cli"], spawner=fake.spawn)
    assert await session.terminate(1.0) == -15
    assert fake.terminate_calls == 1
    assert fake.kill_calls == 0
    assert fake.closed
    assert await session.terminate(1.0) == -15  # 다시 불러도 된다


async def test_terminate_ignored_then_killed() -> None:
    fake = FakePty(ignore_terminate=True)
    session = await PtySession.spawn(["cli"], spawner=fake.spawn)
    assert await session.terminate(0.05) == -9
    assert (fake.terminate_calls, fake.kill_calls) == (1, 1)
    assert not session.is_alive()


async def test_exit_code_and_resize() -> None:
    fake = FakePty(output="bye\n", exit_code=3)
    async with await PtySession.spawn(["cli"], spawner=fake.spawn) as session:
        assert await session.wait_exit(1.0) == 3
        assert session.exit_code == 3
    fake2 = FakePty()
    async with await PtySession.spawn(["cli"], spawner=fake2.spawn) as session2:
        session2.resize(100, 10)
        assert fake2.size == (100, 10)


async def test_wait_exit_timeout_returns_none() -> None:
    fake = FakePty()
    async with await PtySession.spawn(["cli"], spawner=fake.spawn) as session:
        assert await session.wait_exit(0.05) is None


async def test_spawner_factory_makes_new_fake_each_time() -> None:
    spawner = FakePtySpawner(lambda call: FakePty(exit_code=0 if call.argv[-1] == "ok" else 1))
    for arg, expected in (("ok", 0), ("bad", 1)):
        async with await PtySession.spawn(["cli", arg], spawner=spawner) as session:
            assert await session.wait_exit(1.0) == expected
    assert [call.argv[-1] for call, _ in spawner.spawned] == ["ok", "bad"]


async def test_spawn_validates_arguments() -> None:
    with pytest.raises(ValueError, match="argv"):
        await PtySession.spawn([], spawner=FakePty().spawn)
    with pytest.raises(ValueError, match="cols"):
        await PtySession.spawn(["x"], cols=0, spawner=FakePty().spawn)
