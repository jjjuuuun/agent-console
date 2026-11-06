"""agent-console-example-secret-provider: 로컬 파일의 `KEY=VALUE` 줄에서 비밀 값 읽기(X10).

실행 엔진·서버에는 entry point `agent_console.secret_providers`로만 등록된다(또는 설치하지 않고
`plugins.modules`로 ``register``). 외부 서비스·네트워크가 없다.

공개 API:
    - 공급자 key: ``PROVIDER_ID``
    - 공급자: ``FileSecretProvider(path, *, settings)``, entry point 값
      ``EnvFileSecretProvider(environ=None, *, settings)``(경로 = 환경변수)
    - 설정: ``SecretFileSettings``, ``load_settings(options)``, ``default_settings_data()``
    - 줄 읽기(순수): ``parse_secret_lines(text, settings)``
    - 설치 없이 쓰기: ``register(registries)``
"""

from agent_console_example_secret_provider._provider import (
    PROVIDER_ID,
    EnvFileSecretProvider,
    FileSecretProvider,
    SecretFileSettings,
    default_settings_data,
    load_settings,
    parse_secret_lines,
    register,
)

__all__ = [
    "PROVIDER_ID",
    "EnvFileSecretProvider",
    "FileSecretProvider",
    "SecretFileSettings",
    "default_settings_data",
    "load_settings",
    "parse_secret_lines",
    "register",
]
