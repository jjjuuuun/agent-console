"""마지막 검사: 산출물에 평문 비밀로 의심되는 값이 남지 않게 가린다(형식과 무관한 안전망).

- JSON 파일: 구조로 검사(`SecretRules.find_suspected`). `${이름}` 환경 변수 확장은 참조로 본다.
  의심 위치의 값은 가림 문자열로 바꾼다.
- 그 밖의 텍스트(UTF-8로 읽히는 것): `redact_suspected`로 의심 부분만 가린다.
- 바이너리: 검사하지 않는다(텍스트로 읽을 수 없음).

가린 파일마다 경고(`export.secret_redacted`, 위치만)를 낸다. 값은 경고·로그에 넣지 않는다.
"""

from __future__ import annotations

import json
import re
from typing import Any

from agent_console_contracts import Issue
from agent_console_secret_rules import REDACTED, SecretRules

from ._interfaces import ExportIssueCodes, ExportOutput, OutputFile

__all__ = ["scrub_output"]

_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-[^}]*)?\}")
_JSON_TYPES = ("application/json",)


def _is_json(file: OutputFile) -> bool:
    return (file.media_type or "").split(";")[0].strip() in _JSON_TYPES or file.path.endswith(
        ".json"
    )


def _as_refs(value: Any) -> Any:
    """`${이름}`만 있는 문자열을 `secret://이름`으로(검사용 사본)."""
    if isinstance(value, str):
        match = _ENV_REF.fullmatch(value.strip())
        return f"secret://{match.group(1)}" if match else value
    if isinstance(value, list):
        return [_as_refs(v) for v in value]
    if isinstance(value, dict):
        return {k: _as_refs(v) for k, v in value.items()}
    return value


def _unescape(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _set(data: Any, pointer: str, value: Any) -> bool:
    parts = [_unescape(p) for p in pointer.split("/")[1:]]
    if not parts:
        return False
    target = data
    for part in parts[:-1]:
        if isinstance(target, list):
            target = target[int(part)]
        elif isinstance(target, dict):
            target = target[part]
        else:
            return False
    last = parts[-1]
    if isinstance(target, list):
        target[int(last)] = value
        return True
    if isinstance(target, dict) and last in target:
        target[last] = value
        return True
    return False


def _issue(path: str, pointers: list[str]) -> Issue:
    return Issue(
        severity="warning",
        code=ExportIssueCodes.SECRET_REDACTED,
        message="평문 비밀로 보이는 값을 가렸습니다. 비밀은 참조(secret://)로 두세요",
        details={"file": path, "pointers": pointers},
    )


def _scrub_json(file: OutputFile, rules: SecretRules) -> tuple[OutputFile, Issue | None]:
    try:
        data = json.loads(file.data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return _scrub_text(file, rules)
    findings = rules.find_suspected(_as_refs(data))
    if not findings:
        return file, None
    pointers = []
    for finding in findings:
        try:
            if _set(data, finding.path, REDACTED):
                pointers.append(finding.path)
        except (KeyError, IndexError, ValueError):
            continue
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    return OutputFile(file.path, text.encode("utf-8"), file.media_type), _issue(file.path, pointers)


def _scrub_text(file: OutputFile, rules: SecretRules) -> tuple[OutputFile, Issue | None]:
    try:
        text = file.data.decode("utf-8")
    except UnicodeDecodeError:
        return file, None
    redacted = rules.redact_suspected(text)
    if redacted == text:
        return file, None
    return OutputFile(file.path, redacted.encode("utf-8"), file.media_type), _issue(file.path, [])


def scrub_output(output: ExportOutput, rules: SecretRules) -> ExportOutput:
    """산출물의 평문 비밀 의심 값을 가린 새 산출물(경고 추가)."""
    files: list[OutputFile] = []
    warnings = list(output.warnings)
    for file in output.files:
        cleaned, issue = (_scrub_json if _is_json(file) else _scrub_text)(file, rules)
        files.append(cleaned)
        if issue is not None:
            warnings.append(issue)
    return ExportOutput(files=files, warnings=warnings)
