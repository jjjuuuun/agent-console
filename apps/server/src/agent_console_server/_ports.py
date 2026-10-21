"""호스트가 모으는 포트(design §3R.1.3·§3R.1.4, 3R.13). 이름으로만 맞춘다(기능 모듈 패키지를
import하지 않는다, design §3R.1.2).

| 포트 | 모양 | 쓰는 곳 |
| --- | --- | --- |
| `server.warnings`(multi) | `() -> Issue[]` | `GET /server-info` 경고 |
| `server.attributes`(multi) | `() -> {이름: 값}` | `GET /server-info` 속성 |
| `secrets.redact` | `(str) -> str` | 호스트 오류 메시지·플러그인 보고 가리기(없으면 그대로) |
| `secrets.rules` | `() -> SecretRules` | 모듈 옵션 보기의 평문 비밀 의심 판정(없으면 기본 규칙) |
"""

from __future__ import annotations

from typing import Any

from agent_console_modkit import PortKey

SERVER_WARNINGS: PortKey[Any] = PortKey("server.warnings", "서버 정보 경고", multi=True)
"""호스트(`GET /server-info`)가 모으는 경고 포트."""
SERVER_ATTRIBUTES: PortKey[Any] = PortKey("server.attributes", "서버 정보 속성", multi=True)
"""호스트(`GET /server-info`)가 모으는 속성 포트."""
SECRET_REDACT: PortKey[Any] = PortKey("secrets.redact", "해석한 비밀 값 가리기")
"""호스트 오류 메시지·플러그인 보고 가리기에 쓰는 포트(없으면 그대로)."""

SECRET_RULES: PortKey[Any] = PortKey("secrets.rules", "지금 비밀 의심 규칙")
"""모듈 옵션 보기(`GET /modules/{id}/options`)가 쓰는 비밀 규칙 포트(없으면 기본 규칙)."""

__all__ = ["SECRET_REDACT", "SECRET_RULES", "SERVER_ATTRIBUTES", "SERVER_WARNINGS"]
