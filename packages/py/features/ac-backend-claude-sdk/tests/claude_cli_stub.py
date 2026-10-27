"""테스트용 가짜 Claude Code CLI(실제 CLI·로그인을 부르지 않는다, 5.2R.82).

사용: ``python claude_cli_stub.py <시나리오> auth {login|status|logout}``

``CLAUDE_CONFIG_DIR``(테스트 임시 폴더)에만 쓴다. 없으면 아무것도 쓰지 않고 끝난다.

로그인 시나리오:
- ``code``: URL → 코드 요청 → ``GOOD-CODE``면 자격 파일을 쓰고 성공 문구, 그 밖은 오류 후 종료 1.
- ``callback``: URL → 잠시 뒤 자격 파일을 쓰고 성공 문구(코드 없이).
- ``nourl``: 아무 URL 없이 멈춘다.
- ``silent``: 성공 문구 없이 자격 파일을 쓰고 종료 0.
- ``false_success``: 자격 파일 없이 성공 문구를 내고 종료 0(확인이 실패해야 한다).
- ``ignore_term``: SIGTERM을 무시하고 URL 뒤 멈춘다(강제 종료 확인).
- ``bad_url``: 허용되지 않은 호스트·http URL만 낸다.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path

URL = "https://claude.ai/oauth/authorize?code=true&client_id=stub&state=s1"
GOOD_CODE = "GOOD-CODE"
ENV_KEYS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "SECRET_OTHER")


def _config() -> Path | None:
    value = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(value) if value else None


def _creds() -> Path | None:
    folder = _config()
    return folder / ".credentials.json" if folder else None


def _write_creds() -> None:
    path = _creds()
    if path is not None:
        path.write_text('{"stub": true}', encoding="utf-8")


def _record_env() -> None:
    folder = _config()
    if folder is not None:
        seen = {key: os.environ.get(key) for key in ENV_KEYS}
        (folder / "env.json").write_text(json.dumps(seen), encoding="utf-8")


def _say(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def _hang() -> None:
    while True:
        time.sleep(0.1)


def _success_then_enter() -> int:
    _say("\x1b[32mLogin successful.\x1b[0m Press Enter to continue\r\n")
    sys.stdin.readline()
    return 0


def login(scenario: str) -> int:
    _record_env()
    if scenario == "ignore_term":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if scenario == "nourl":
        _say("Starting login...\r\n")
        _hang()
    if scenario == "silent":
        _write_creds()
        return 0
    if scenario == "bad_url":
        _say("Open http://claude.ai/oauth/authorize?x=1\r\n")
        _say("Or https://evil.example/oauth/authorize?x=1\r\n")
        _hang()
    _say("\x1b[1mBrowser didn't open? Use the url below to sign in\x1b[0m\r\n\r\n")
    _say(URL + "\r\n\r\n")
    if scenario == "ignore_term":
        _hang()
    if scenario == "false_success":
        return _success_then_enter()
    if scenario == "callback":
        time.sleep(0.3)
        _write_creds()
        return _success_then_enter()
    _say("Paste code here if prompted > ")
    code = sys.stdin.readline().strip()
    if code == GOOD_CODE:
        _write_creds()
        _say("\r\n")
        return _success_then_enter()
    _say("\r\nOAuth error: Invalid code\r\n")
    return 1


def status() -> int:
    path = _creds()
    if path is not None and path.exists():
        print(json.dumps({"loggedIn": True, "authMethod": "claude.ai"}))
        return 0
    print(json.dumps({"loggedIn": False, "authMethod": "none"}))
    return 1


def logout() -> int:
    path = _creds()
    if path is not None and path.exists():
        path.unlink()
    _say("Successfully logged out from your Anthropic account.\r\n")
    return 0


def main(argv: list[str]) -> int:
    scenario, _auth, verb = argv[1], argv[2], argv[3]
    if verb == "login":
        return login(scenario)
    if verb == "status":
        return status()
    if verb == "logout":
        return logout()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
