"""기본 규칙 데이터. 코드가 아니라 데이터이므로 `SecretRules` 생성자에서 통째로 바꿀 수 있다.

규칙 형식은 `_rules.py` 모듈 설명을 본다. 기본 규칙은 의도적으로 넓다(놓치는 것보다 과하게
의심하는 편이 안전하다). 오탐을 줄이는 장치는 이름 예외 단어(`DEFAULT_NAME_EXCEPTIONS`)다.
"""

from __future__ import annotations

DEFAULT_KEY_NAMES: tuple[str, ...] = (
    "token",
    "secret",
    "password",
    "passwd",
    "passphrase",
    "auth",
    "authorization",
    "credential",
    "credentials",
    "bearer",
    "key",
    "apikey",
    "cookie",
    "accesstoken",
    "authtoken",
    "privatekey",
    "secretkey",
    "clientsecret",
)
"""비밀로 보이는 이름 단어. 이름(키·플래그·쿼리 이름)을 단어로 나눠 이어지는 단어가 이것과 같으면
의심한다(`api_key`·`apiKey`·`x-api-key`·`APIKEY` 모두 `key`·`apikey`에 걸린다). `author`·
`keyboard`·`max_tokens`처럼 단어가 다르면 걸리지 않는다."""

DEFAULT_NAME_EXCEPTIONS: tuple[str, ...] = (
    "file",
    "files",
    "path",
    "paths",
    "dir",
    "directory",
    "name",
    "names",
    "type",
    "types",
    "mode",
    "url",
    "uri",
    "endpoint",
    "id",
    "ids",
    "length",
    "len",
    "size",
    "count",
    "limit",
    "env",
    "header",
    "field",
    "format",
    "prefix",
    "provider",
    "method",
    "scheme",
    "required",
    "enabled",
    "expiry",
    "expires",
    "ttl",
    "timeout",
    "label",
    "title",
    "description",
    "hint",
)
"""비밀 단어 **뒤에** 오면 비밀이 아닌 이름으로 보는 단어(`--key-file`, `auth_mode`,
`token_url`, `secret_name`). 하위 객체가 상위 비밀 이름을 이어받을 때도, 자기 이름의 마지막 단어가
이 목록에 있으면 이어받지 않는다(`{"auth": {"mode": "oauth"}}`의 `mode`)."""

_TOKEN_CHARS = r"[A-Za-z0-9_\-]"

_TOKEN_PREFIXES = (
    r"(?:ghp_|gho_|ghs_|ghu_|ghr_|github_pat_|glpat-|sk-|xox[abprs]-|AKIA|ASIA|AIza|hf_|npm_)"
)
"""알려진 접두 토큰(GitHub, GitLab, OpenAI·Anthropic, Slack, AWS, Google, Hugging Face, npm)."""

_TOKEN_BOUNDARY = r"(?<![A-Za-z0-9_\-])"
"""접두 앞이 토큰 글자가 아님(단어 경계). 이 경계가 있으면 몸통은 6자 이상이면 된다."""

_GLUED_TOKEN_BODY = (
    r"(?=" + _TOKEN_CHARS + r"*[0-9])(?=" + _TOKEN_CHARS + r"*[A-Z])"
    r"(?=" + _TOKEN_CHARS + r"*?[A-Za-z0-9]{16})" + _TOKEN_CHARS + r"{16,}"
)
"""앞에 글자가 붙은 접두 토큰(`xxxsk-…`, 5.5R.32)의 몸통 조건: 숫자와 대문자가 있고, 구분자
(`-`·`_`) 없이 이어진 글자·숫자가 16자 이상인 구간이 있다(무작위 키 모양). 경계가 없으면
`disk-usage`·`risk-assessment-Q4-2024`의 `sk-`처럼 낱말 안 접두가 흔하므로 키처럼 보일 때만 친다."""

DEFAULT_VALUE_PATTERNS: tuple[str, ...] = (
    # 알려진 접두 토큰: 앞이 단어 경계면 몸통 6자 이상
    _TOKEN_BOUNDARY + _TOKEN_PREFIXES + _TOKEN_CHARS + r"{6,}",
    # 알려진 접두 토큰: 앞에 글자가 붙어 있으면(`xxxsk-…`·`keyAKIA…`) 키 모양 몸통일 때만
    _TOKEN_PREFIXES + _GLUED_TOKEN_BODY,
    # JWT(헤더·내용 모두 `{"`의 base64인 `eyJ`로 시작)
    r"(?<![A-Za-z0-9_\-])eyJ"
    + _TOKEN_CHARS
    + r"{8,}\.eyJ"
    + _TOKEN_CHARS
    + r"{8,}\."
    + _TOKEN_CHARS
    + r"{8,}",
    # PEM 개인 키(끝 표시가 없으면 시작부터 최대 길이까지)
    r"-----BEGIN [A-Z0-9 ]{0,40}PRIVATE KEY-----(?:[\s\S]{0,20000}?-----END [A-Z0-9 ]{0,40}"
    r"PRIVATE KEY-----|[\s\S]{0,20000})",
    # Authorization 값(`Bearer x`, `Basic x`): 숫자가 있거나 20자 이상일 때만(일반 문장 오탐 방지)
    r"(?i:\b(?:bearer|basic))\s+(?P<secret>(?=[A-Za-z0-9._~+/=\-]*[0-9])[A-Za-z0-9._~+/=\-]{8,}"
    r"|[A-Za-z0-9._~+/=\-]{20,})",
    # 명령줄 플래그(`--token abc`, `--api-key=abc`): 플래그 이름이 비밀 이름일 때
    r"(?<![\w\-])--?(?P<name>[A-Za-z][A-Za-z0-9_\-]*)(?:=|[ \t]+)(?P<secret>[^\s\"'\-][^\s\"']*)",
    # 대입·쿼리·JSON·YAML(`API_KEY=x`, `?token=x`, `"password": "x"`): 이름이 비밀 이름일 때
    # (`scheme://`의 `//`로 시작하는 값은 대입이 아니다 — `secret://이름` 참조 등)
    # 닫는 괄호(`)`·`}`·`]`)는 값 끝으로 보되, 뒤에 값 글자가 이어지면 값의 일부로 본다
    # (`password=abc]hunter2`·`password=]hunter2`의 뒤 조각이 남지 않게, 5R.19). 두 글자
    # 묶음이 서로 겹치지 않고 소유 수량자라 되돌아가기가 없다(`ac-safe-regex` 검사 통과).
    r"(?<![\w.\-])(?P<name>[A-Za-z_][\w.\-]*)[\"']?[ \t]*[=:][ \t]*[\"']?"
    r"(?:(?i:bearer|basic|token)[ \t]+)?(?P<secret>(?!//)[)}\]]*+[^\s\"'&,;)}\]]++"
    r"(?:[)}\]]++[^\s\"'&,;)}\]]++)*+)",
    # URL 사용자 정보(`scheme://user:pw@host`)
    r"[A-Za-z][A-Za-z0-9+.\-]*://[^\s/:@]+:(?P<secret>[^\s/@]+)@",
)
"""텍스트 안 비밀 모양 정규식. 이름 그룹 규칙:

- `secret`이 있으면 그 부분만 가린다(없으면 매치 전체).
- `name`이 있으면 그 이름이 비밀 이름(`SecretRules.name_suspected`)일 때만 매치로 친다.
- 가릴 부분이 `secret://` 참조면 매치로 치지 않는다."""
