"""서버는 조립만 한다(design §2R.1·§3R.1.8, modularity §3.8-6, 3R.16).

`apps/server` 소스에 기능 이름이 없다: 기반(L0)·modkit 밖의 사내 패키지를 import하지 않고, 설치된
모듈의 id·패키지 이름·배포 이름을 문자열·주석에 쓰지 않으며, 기능 이름(모듈 id의 기능 부분)을
코드의 문자열 값으로 쓰지 않는다. 기준 목록은 설치된 모듈(entry point)에서 만든다(테스트에도
고정 목록 없음). 임시 통짜 모듈·`_context.py`·옛 플러그인 로더는 없다.
"""

from __future__ import annotations

import ast
import importlib.metadata
import io
import re
import tokenize
from pathlib import Path

import agent_console_server
from agent_console_server import installed_modules

SERVER_SRC = Path(agent_console_server.__file__).parent

INTERNAL_PREFIX = "agent_console_"
ALLOWED_INTERNAL = frozenset(
    {
        "agent_console_server",
        "agent_console_modkit",
        # 기반(L0, modularity §3.1): 기능이 아니다
        "agent_console_contracts",
        "agent_console_registry",
        "agent_console_settings",
        "agent_console_secret_rules",
        "agent_console_safe_regex",
        "agent_console_claude_format",
        "agent_console_graph",
    }
)
"""서버가 import해도 되는 사내 패키지(modkit + 기반)."""

TEST_SUPPORT = frozenset({"testing.py"})
"""테스트 지원 하위 모듈(design §3R.2.2): 기능 API로 시험 데이터를 만든다.
앱이 import하지 않는다."""


def _sources() -> list[Path]:
    files = sorted(p for p in SERVER_SRC.glob("*.py") if p.name not in TEST_SUPPORT)
    assert files
    return files


def test_app_does_not_import_test_support() -> None:
    for path in _sources():
        assert ".testing" not in path.read_text(encoding="utf-8"), path.name


def _module_terms() -> tuple[set[str], set[str]]:
    """(엄격 — 주석·문서 포함 금지: 모듈 id·import 이름·배포 이름, 코드 문자열 금지: 기능 단어)."""
    modules = installed_modules()
    assert modules, "설치된 모듈이 없다(entry point)"
    strict: set[str] = set()
    words: set[str] = set()
    for module in modules:
        module_id = module.descriptor.id
        strict.add(module_id)
        root = type(module).__module__.split(".")[0]
        strict.add(root)
        try:
            dist = importlib.metadata.packages_distributions().get(root, [])
        except Exception:  # pragma: no cover - 메타데이터 없음
            dist = []
        strict.update(dist)
        # "mod-chat" → "chat", "link-runs-teams" → "runs-teams"
        feature = module_id.split("-", 1)[1] if "-" in module_id else module_id
        words.add(feature)
    return strict, words


def _string_constants(tree: ast.AST) -> tuple[list[str], list[str]]:
    """(코드 문자열, 문서 문자열)."""
    docs: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docs.add(id(body[0].value))
    code: list[str] = []
    doc: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            (doc if id(node) in docs else code).append(node.value)
    return code, doc


def _comments(text: str) -> list[str]:
    tokens = tokenize.generate_tokens(io.StringIO(text).readline)
    return [t.string for t in tokens if t.type == tokenize.COMMENT]


def test_server_imports_only_modkit_and_base_packages() -> None:
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                root = name.split(".")[0]
                if root.startswith(INTERNAL_PREFIX):
                    assert root in ALLOWED_INTERNAL, f"{path.name}: import {name}"


def test_server_has_no_module_or_feature_names() -> None:
    strict, words = _module_terms()
    strict_re = re.compile(
        "|".join(rf"(?<![\w-]){re.escape(t)}(?![\w-])" for t in sorted(strict, key=len)[::-1])
    )
    word_re = re.compile(
        "|".join(rf"(?<![\w-]){re.escape(w)}(?![\w-])" for w in sorted(words, key=len)[::-1])
    )
    problems: list[str] = []
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        code, doc = _string_constants(ast.parse(text))
        for value in [*code, *doc, *_comments(text)]:
            if m := strict_re.search(value):
                problems.append(f"{path.name}: 모듈 이름 {m.group(0)!r} in {value[:60]!r}")
        for value in code:
            if m := word_re.search(value):
                problems.append(f"{path.name}: 기능 이름 {m.group(0)!r} in {value[:60]!r}")
    assert problems == []


def test_terms_cover_installed_modules() -> None:
    """검사가 빈 목록으로 통과하지 않는다(설치된 기능·연동 모듈이 있다)."""
    strict, words = _module_terms()
    kinds = {m.descriptor.kind for m in installed_modules()}
    assert {"feature", "link"} <= kinds
    assert len(words) == len(installed_modules())
    assert len(strict) >= 2 * len(words)
