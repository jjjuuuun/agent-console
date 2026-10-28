"""ruamel.yaml 왕복 유틸: 주석·키 순서 보존, 원자적 파일 쓰기.

의존: ruamel.yaml. 대안: PyYAML(주석 소실), 파일 대신 DB 단일 저장(R0.4 위반 위험).
"""

import datetime
import io
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import LiteralScalarString

from .errors import DefinitionCorrupt


def _yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def to_plain(value: Any) -> Any:
    """ruamel 자료형을 JSON 호환 파이썬 값(dict, list, str, int, float, bool, None)으로."""
    if isinstance(value, Mapping):
        return {str(k): to_plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [to_plain(v) for v in value]
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return str(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, datetime.date | datetime.time):
        return value.isoformat()
    return str(value)


def wrap_value(value: Any) -> Any:
    """새 값을 ruamel 자료형으로(여러 줄 문자열은 `|` 블록으로)."""
    if isinstance(value, Mapping):
        out = CommentedMap()
        for k, v in value.items():
            out[k] = wrap_value(v)
        return out
    if isinstance(value, list):
        seq = CommentedSeq()
        for item in value:
            seq.append(wrap_value(item))
        return seq
    if isinstance(value, str) and "\n" in value and "\r" not in value:
        return LiteralScalarString(value)
    return value


def merge_into(old: Any, new: Any) -> Any:
    """`old`(ruamel 객체)를 `new` 값으로 맞추되 같은 값의 노드는 그대로 둬 주석·서식을 보존한다."""
    if isinstance(old, CommentedMap) and isinstance(new, Mapping):
        for key in [k for k in old if k not in new]:
            del old[key]
        for key, value in new.items():
            old[key] = merge_into(old[key], value) if key in old else wrap_value(value)
        return old
    if isinstance(old, CommentedSeq) and isinstance(new, list):
        for i, value in enumerate(new):
            if i < len(old):
                old[i] = merge_into(old[i], value)
            else:
                old.append(wrap_value(value))
        del old[len(new) :]
        return old
    plain = to_plain(old)
    if type(plain) is type(new) and plain == new:
        return old
    return wrap_value(new)


def load_yaml_text(text: str, name: str = "document") -> CommentedMap:
    """YAML 텍스트를 왕복 가능한 객체로 읽는다. 빈 문서는 빈 매핑.

    Raises:
        DefinitionCorrupt: 문법 오류이거나 최상위가 객체가 아니다(`name`은 메시지에만 쓴다).
    """
    try:
        data = _yaml().load(text)
    except Exception as exc:
        raise DefinitionCorrupt(f"{name}: invalid YAML ({exc.__class__.__name__})") from exc
    if data is None:
        return CommentedMap()
    if not isinstance(data, CommentedMap):
        raise DefinitionCorrupt(f"{name}: top level must be a mapping")
    return data


def load_yaml_file(path: Path) -> CommentedMap | None:
    """파일을 왕복 가능한 객체로 읽는다. 없으면 None, 문법 오류·비객체면 `DefinitionCorrupt`."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        raise DefinitionCorrupt(f"{path.name}: {exc}") from exc
    return load_yaml_text(text, path.name)


def dump_yaml(data: Any) -> str:
    buffer = io.StringIO()
    _yaml().dump(data, buffer)
    return buffer.getvalue()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """같은 폴더의 임시 파일에 쓰고 fsync 후 `os.replace`로 바꾼다(중간 상태가 보이지 않는다)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, text: str) -> None:
    """UTF-8 텍스트를 줄바꿈 변환 없이 원자적으로 쓴다(`atomic_write_bytes` 참고)."""
    atomic_write_bytes(path, text.encode("utf-8"))
