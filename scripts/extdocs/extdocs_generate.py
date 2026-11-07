"""생성(``poe extdocs``): ``reference.md``, 영역 페이지의 생성 구간, 예제 색인.

결정적이다: 대상은 워크스페이스 멤버 배포만, 모든 표 정렬, 시각·절대 경로·환경 값 없음, LF.
문장·제목·표 머리는 데이터(``templates/registration.yaml``·``templates/text.yaml``)다.
"""

from __future__ import annotations

import contextlib
import os
import string
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from extdocs_common import (
    Collection,
    Declared,
    SymbolError,
    SymbolResolver,
    ToolData,
    first_doc_line,
    is_python_symbol,
)
from extdocs_md import FACTS_RE, facts_block, replace_facts, section_span
from extdocs_points import CodeFacts


class _Blank(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return ""


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _table(header: Sequence[str], rows: Iterable[Sequence[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    out.extend("| " + " | ".join(_cell(c) for c in row) + " |" for row in rows)
    return out


def _code(items: Iterable[str]) -> str:
    return ", ".join(f"`{i}`" for i in items)


def _relpath(target: str, from_dir: str) -> str:
    return Path(os.path.relpath(target, from_dir or ".")).as_posix()


class Generator:
    """생성기. 입력(수집·코드 사실·데이터)은 생성자로 받는다."""

    def __init__(
        self,
        col: Collection,
        facts: CodeFacts,
        data: ToolData,
        resolver: SymbolResolver,
    ) -> None:
        self.col = col
        self.facts = facts
        self.data = data
        self.resolver = resolver
        self.text: Mapping[str, Any] = data.text
        self.labels: Mapping[str, str] = data.text.get("labels", {})
        self.area_order = {a.id: i for i, a in enumerate(data.areas)}

    # -------------------------------------------------------- 공통 값

    def _label(self, key: str) -> str:
        return str(self.labels.get(key, key))

    def _none(self) -> str:
        return self._label("none")

    def _heading(self, key: str) -> str:
        return str(self.text.get("headings", {}).get(key, key))

    def _columns(self, key: str) -> list[str]:
        return [str(c) for c in self.text.get("columns", {}).get(key, [])]

    def _ordered(self) -> list[Declared]:
        return sorted(
            self.col.declarations,
            key=lambda d: (self.area_order.get(d.point.area, len(self.area_order)), d.slug),
        )

    def registration_name(self, decl: Declared) -> str:
        reg = decl.point.registration
        if decl.slug in self.facts.declared_groups:
            return self.facts.declared_groups[decl.slug]
        if decl.slug in self.facts.declared_ports:
            return self.facts.declared_ports[decl.slug][0]
        return reg.path or reg.export or reg.name or reg.group or reg.port or ""

    def builtins(self, decl: Declared) -> list[str]:
        """기본 구현(등록 이름 → 배포). ``builtin = "none"``이면 비운다."""
        mode = decl.point.builtin
        if mode == "none":
            return []
        group = self.facts.declared_groups.get(decl.slug)
        if group is not None and mode in (None, "entry-points"):
            return [f"{name} ({dist})" for name, dist in self.facts.ep_groups.get(group, [])]
        port = self.facts.declared_ports.get(decl.slug)
        if port is not None and mode in (None, "providers"):
            return list(self.facts.ports.get(port[0], {}).get("provides", []))
        return []

    def _values(self, decl: Declared) -> _Blank:
        reg = decl.point.registration
        port = self.facts.declared_ports.get(decl.slug)
        multi = reg.multi if reg.multi is not None else (port[1] if port else None)
        values = _Blank(
            slug=decl.slug,
            title=decl.point.title,
            kind=reg.kind,
            group=self.facts.declared_groups.get(decl.slug, reg.group or ""),
            group_symbol=reg.group if reg.group and is_python_symbol(reg.group) else "",
            port=port[0] if port else (reg.port or ""),
            port_symbol=reg.port if reg.port and is_python_symbol(reg.port) else "",
            multi=self._label("yes") if multi else self._label("no"),
            path=reg.path or "",
            settings=_code(reg.settings),
            disable=_code(reg.disable),
            export=reg.export or "",
            name=reg.name or "",
            package=decl.package,
        )
        return values

    def sentence(self, decl: Declared, key: str) -> str:
        """등록 종류별 문장. 틀이 목록이면 자리표시자가 다 채워지는 첫 틀(마지막은 무조건)."""
        templates = self.data.registration_templates
        tmpl = templates.get(decl.point.registration.kind) or templates["_default"]
        raw = tmpl.get(key, templates["_default"].get(key, ""))
        choices = [str(c) for c in raw] if isinstance(raw, list) else [str(raw)]
        values = self._values(decl)
        for i, choice in enumerate(choices):
            names = [f for _, f, _, _ in string.Formatter().parse(choice) if f]
            if i == len(choices) - 1 or all(values[n] for n in names):
                return choice.format_map(values)
        return ""

    def doc_line(self, symbol: str) -> str:
        if not is_python_symbol(symbol):
            return ""
        try:
            return first_doc_line(self.resolver.resolve(symbol))
        except SymbolError:
            return ""

    # -------------------------------------------------------- 영역 페이지 생성 구간

    def point_facts(self, decl: Declared, doc_file: str) -> str:
        """지점 하나의 생성 구간 본문(표지 제외). ``doc_file``은 저장소 상대 문서 경로."""
        point = decl.point
        lines = [f"- {self._heading('facts_register')}: {self.sentence(decl, 'register')}"]
        if point.interface:
            lines.append(f"- {self._heading('facts_interface')}:")
            for symbol in point.interface:
                doc = self.doc_line(symbol)
                lines.append(f"  - `{symbol}`" + (f" — {doc}" if doc else ""))
        if point.settings:
            lines.append(f"- {self._heading('facts_settings')}: {_code(point.settings)}")
        builtins = self.builtins(decl)
        lines.append(
            f"- {self._heading('facts_builtin')}: "
            + (", ".join(f"`{b}`" for b in builtins) if builtins else self._none())
        )
        doc_dir = Path(doc_file).parent.as_posix()
        if point.example:
            lines.append(f"- {self._heading('facts_example')}:")
            for ex in point.example:
                if ex.path:
                    readme = f"{ex.path.rstrip('/')}/README.md"
                    link = f"[{ex.path}]({_relpath(readme, doc_dir)})"
                else:
                    link = _code(ex.symbols) if ex.symbols else ""
                if link and ex.note:
                    text = f"{link} — {ex.note}"
                else:
                    text = link or ex.note or self._none()
                lines.append(f"  - {ex.kind}: {text}")
        else:
            lines.append(f"- {self._heading('facts_example')}: {self._none()}")
        disable = self.sentence(decl, "disable")
        if disable:
            lines.append(f"- {self._heading('facts_disable')}: {disable}")
        return "\n".join(lines) + "\n"

    # -------------------------------------------------------- reference.md

    def reference(self) -> str:
        t = self.text
        out = [str(t.get("generated_notice", "")), "", f"# {t.get('reference_title', '')}", ""]
        intro = str(t.get("reference_intro", ""))
        if intro:
            out += [intro, ""]
        areas = {a.id: a.title for a in self.data.areas}
        rows = []
        for decl in self._ordered():
            slug = f"[{decl.slug}]({self._guide_link(decl)})" if decl.point.guide else decl.slug
            builtins = self.builtins(decl)
            rows.append(
                [
                    areas.get(decl.point.area, decl.point.area),
                    slug,
                    decl.point.title,
                    decl.point.registration.kind,
                    f"`{self.registration_name(decl)}`"
                    if self.registration_name(decl)
                    else self._none(),
                    str(len(builtins)) if builtins else self._none(),
                    ", ".join(sorted({e.kind for e in decl.point.example})) or self._none(),
                ]
            )
        out += [f"## {self._heading('points')}", "", *_table(self._columns("points"), rows), ""]

        # 정의 상수: 선언이 쓴 공개 기호가 있으면 그것, 없으면 상수를 찾은 정의 모듈 자리.
        declared_syms: dict[str, set[str]] = {}
        for decl in self.col.declarations:
            group = self.facts.declared_groups.get(decl.slug)
            symbol = decl.point.registration.group or ""
            if group is not None and is_python_symbol(symbol):
                declared_syms.setdefault(group, set()).add(symbol)
        consts: dict[str, list[str]] = {g: sorted(v) for g, v in declared_syms.items()}
        for c in self.facts.constants:
            if c.value not in declared_syms:
                consts.setdefault(c.value, []).append(c.symbol)
        groups = sorted(set(consts) | set(self.facts.ep_groups))
        group_rows = [
            [
                f"`{g}`",
                _code(sorted(consts.get(g, []))) or self._none(),
                ", ".join(f"`{n}` ({d})" for n, d in self.facts.ep_groups.get(g, []))
                or self._none(),
            ]
            for g in groups
        ]
        out += [
            f"## {self._heading('groups')}",
            "",
            *_table(self._columns("groups"), group_rows),
            "",
        ]

        internal: dict[str, str] = {}
        for item, _ in self.col.internal_ports:
            name = item.port
            if is_python_symbol(name):
                with contextlib.suppress(SymbolError):
                    name = str(getattr(self.resolver.resolve(name), "name", name))
            internal.setdefault(name, item.reason)
        port_rows = [
            [
                f"`{name}`",
                ", ".join(roles["provides"]) or self._none(),
                ", ".join(roles["requires"]) or self._none(),
                ", ".join(roles["optional"]) or self._none(),
                self._label("yes") if roles["multi"] else self._label("no"),
                internal.get(name, ""),
            ]
            for name, roles in self.facts.ports.items()
        ]
        out += [f"## {self._heading('ports')}", "", *_table(self._columns("ports"), port_rows), ""]

        mod_rows = [
            [
                f"`{m.id}`",
                m.kind,
                ", ".join(m.web_roles) or self._none(),
                ", ".join(f"{k} {v}" for k, v in m.contracts) or self._none(),
                ", ".join(f"{n}({'/'.join(s)})" for n, s in m.migrations) or self._none(),
            ]
            for m in self.facts.modules.modules
        ]
        out += [
            f"## {self._heading('modules')}",
            "",
            *_table(self._columns("modules"), mod_rows),
            "",
        ]

        facts_cfg: Mapping[str, str] = self.data.settings.get("facts") or {}
        versions = self._resolve_optional(facts_cfg.get("contract_versions"))
        if isinstance(versions, Mapping):
            rows_v = [[f"`{k}`", str(v)] for k, v in sorted(versions.items())]
            out += [
                f"## {self._heading('contracts')}",
                "",
                *_table(self._columns("contracts"), rows_v),
                "",
            ]
        events = self._resolve_optional(facts_cfg.get("known_event_types"))
        if isinstance(events, Iterable) and not isinstance(events, (str, bytes, Mapping)):
            out += [f"## {self._heading('events')}", ""]
            out += [f"- `{e}`" for e in sorted(str(x) for x in events)]
            out.append("")
        return "\n".join(out).rstrip("\n") + "\n"

    def _resolve_optional(self, symbol: str | None) -> Any:
        if not symbol:
            return None
        try:
            return self.resolver.resolve(symbol)
        except SymbolError:
            return None

    def _guide_link(self, decl: Declared) -> str:
        guide = decl.point.guide or ""
        return guide if "#" in guide else f"{guide}#{decl.slug}"

    # -------------------------------------------------------- 예제 색인

    def examples_index(self, index_path: str) -> str:
        t = self.text
        out = [str(t.get("generated_notice", "")), "", f"# {t.get('examples_title', '')}", ""]
        intro = str(t.get("examples_intro", ""))
        if intro:
            out += [intro, ""]
        titles = {d.slug: d.point.title for d in self.col.declarations}
        index_dir = Path(index_path).parent.as_posix()
        rows = []
        for ex in self.col.examples:
            points = sorted(ex.marker.points) if ex.marker else []
            shown = ", ".join(f"`{p}` {titles[p]}" if p in titles else f"`{p}`" for p in points)
            rows.append(
                [
                    f"[{ex.name}]({_relpath(ex.path + '/README.md', index_dir)})",
                    ex.language,
                    shown or self._none(),
                    f"`{ex.install}`" if ex.install else self._none(),
                ]
            )
        out += _table(self._columns("examples"), rows)
        return "\n".join(out) + "\n"

    # -------------------------------------------------------- 문서 폴더 전체 계획

    def scaffold_section(self, decl: Declared, doc_file: str) -> str:
        anchor = self._guide_link(decl).split("#", 1)[1]
        todo = str(self.text.get("todo_text", ""))
        block = facts_block(decl.slug, self.point_facts(decl, doc_file))
        return f"## {anchor}\n\n{todo}\n\n{block}\n"

    def plan(self, root: Path, *, scaffold: bool = False) -> dict[str, str]:
        """저장소 상대 경로 → 생성 후 내용. 문서 폴더가 없으면 ``reference.md``도 계획한다."""
        docs_dir = self.data.docs_dir
        planned: dict[str, str] = {}
        ref_path = f"{docs_dir}/{self.data.s('reference_file')}"
        planned[ref_path] = self.reference()
        index = str(self.data.s("examples_index"))
        planned[index] = self.examples_index(index)

        existing: dict[str, str] = {}
        base = root / docs_dir
        if base.is_dir():
            for path in sorted(base.rglob("*.md")):
                key = path.relative_to(root).as_posix()
                if key != ref_path:
                    existing[key] = path.read_text(encoding="utf-8")
        if scaffold:
            areas = {a.file: a.title for a in self.data.areas}
            for decl in self._ordered():
                if not decl.point.guide:
                    continue
                file_part, anchor = self._guide_link(decl).split("#", 1)
                key = f"{docs_dir}/{file_part}"
                text = existing.get(key)
                if text is None:
                    text = f"# {areas.get(file_part, Path(file_part).stem)}\n"
                if section_span(text, anchor) is None:
                    text = text.rstrip("\n") + "\n\n" + self.scaffold_section(decl, key)
                elif decl.slug not in {m.group("slug") for m in FACTS_RE.finditer(text)}:
                    text = _insert_facts(text, anchor, facts_block(decl.slug, ""))
                existing[key] = text
        for key, text in existing.items():
            render = {d.slug: self.point_facts(d, key) for d in self.col.declarations}
            planned[key] = replace_facts(text, render)
        return dict(sorted(planned.items()))


def _insert_facts(text: str, anchor: str, block: str) -> str:
    span = section_span(text, anchor)
    if span is None:
        return text
    lines = text.split("\n")
    end = span[1]
    while end > span[0] + 1 and not lines[end - 1].strip():
        end -= 1
    return "\n".join([*lines[:end], "", block, *lines[end:]])


def write_plan(root: Path, planned: Mapping[str, str]) -> list[str]:
    """바뀐 파일만 쓴다(LF). 쓴 경로 목록을 돌려준다."""
    written = []
    for key, content in planned.items():
        path = root / key
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == content:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        written.append(key)
    return written


__all__ = ["Generator", "write_plan"]
