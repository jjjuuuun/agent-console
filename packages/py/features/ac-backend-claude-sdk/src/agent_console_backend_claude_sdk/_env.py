"""CLI 하위 프로세스 환경 정책.

claude-agent-sdk(0.2.166)는 `os.environ` 전체를 CLI 하위 프로세스에 물려주고(`CLAUDECODE`만 제외)
그 위에 `ClaudeAgentOptions.env`를 덮어쓴다. 상속을 끄는 옵션은 없다. 그래서 허용 목록 밖의 키를
**빈 문자열로 덮어써** 값이 넘어가지 않게 한다(키 이름은 남는다).
"""

from __future__ import annotations

import fnmatch
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_ENV_ALLOW: tuple[str, ...] = (
    # 공통·POSIX
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "LANG",
    "LANGUAGE",
    "LC_*",
    "TZ",
    "TERM",
    "TMPDIR",
    "TEMP",
    "TMP",
    "PWD",
    # Claude Code 설정 폴더(값은 경로, 비밀 아님). 로그인·준비 점검·실행이 같은 폴더를 보게 한다.
    "CLAUDE_CONFIG_DIR",
    # Windows
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "USERPROFILE",
    "USERNAME",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "PROGRAMW6432",
    "COMMONPROGRAMFILES",
    "COMMONPROGRAMFILES(X86)",
    "HOMEDRIVE",
    "HOMEPATH",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "OS",
)
"""CLI 실행에 필요한 최소 키(대소문자 무시, `*` 글롭). 설정 데이터(`EnvPolicy.allow`)로 바꾼다."""


class EnvPolicy(BaseModel):
    """서버 환경변수를 에이전트 프로세스에 얼마나 물려줄지.

    - `allowlist`(기본): `allow`에 맞는 키만 값을 물려주고 나머지는 빈 값으로 덮어쓴다.
    - `all`: SDK 기본 동작(전부 상속). 백엔드는 실행마다 `log.warning`을 낸다.
    `backend_options.env`로 명시한 키는 항상 그 값을 쓴다.
    """

    model_config = ConfigDict(extra="forbid")

    inherit: Literal["allowlist", "all"] = "allowlist"
    allow: list[str] = Field(default_factory=lambda: list(DEFAULT_ENV_ALLOW))

    def allows(self, key: str) -> bool:
        """이 키의 값을 물려줘도 되면 참."""
        if self.inherit == "all":
            return True
        upper = key.upper()
        return any(fnmatch.fnmatchcase(upper, pattern.upper()) for pattern in self.allow)


def apply_env_policy(
    parent: Mapping[str, str], policy: EnvPolicy, explicit: Mapping[str, str]
) -> dict[str, str]:
    """`ClaudeAgentOptions.env`로 넘길 값: 명시 env + 허용 밖 부모 키를 빈 값으로 가린 것."""
    out = {key: "" for key in parent if key not in explicit and not policy.allows(key)}
    out.update(explicit)
    return out
