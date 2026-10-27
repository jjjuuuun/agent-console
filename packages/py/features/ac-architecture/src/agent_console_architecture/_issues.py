"""프로필 검사(`profile_issues`, `check_profile_data`). 문제는 알리기만 하고 저장을 막지 않는다."""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Iterator, Mapping
from typing import Any, Final

from pydantic import ValidationError

from agent_console_conditions import ConditionOperator, condition_issues
from agent_console_contracts import Issue, IssueSeverity, KnownIssueCodes
from agent_console_contracts.architecture import (
    ArchitectureProfile,
    KnownArchitectureEdgeKinds,
    KnownArchitectureIssueCodes,
)
from agent_console_contracts.runs import ConditionSpec

from ._project import KNOWN_METRICS

ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
"""칸·연결·영역·프로필 id 글자 규칙(계약 `Slug`와 같다). `:`가 없어야 선택 필터 `arch`가 읽힌다."""

_EDGE_KINDS: Final = frozenset(
    {KnownArchitectureEdgeKinds.OBSERVED, KnownArchitectureEdgeKinds.STRUCTURAL}
)


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _issue(severity: IssueSeverity, code: str, message: str, path: str, **details: Any) -> Issue:
    return Issue(severity=severity, code=code, message=message, path=path, details=details)


def _bad_id(value: str, what: str, path: str) -> Issue | None:
    if ID_PATTERN.match(value):
        return None
    return _issue(
        "error",
        KnownArchitectureIssueCodes.BAD_ID,
        f"{what} id {value!r}은(는) 영문·숫자로 시작하고 "
        "영문·숫자·_·-만 쓸 수 있습니다(최대 128자)",
        path,
        id=value,
    )


def _metric_issues(names: list[str] | None, base: str) -> list[Issue]:
    return [
        _issue(
            "warning",
            KnownArchitectureIssueCodes.UNKNOWN_METRIC,
            f"지표 {name!r}을(를) 모릅니다. 이 지표는 보이지 않습니다",
            f"{base}/metrics/{index}",
            metric=name,
        )
        for index, name in enumerate(names or [])
        if name not in KNOWN_METRICS
    ]


def _condition_specs(profile: ArchitectureProfile) -> Iterator[tuple[str, ConditionSpec]]:
    """프로필의 조건 묶음과 그 위치(JSON Pointer): 칸 ``when``, 연결 ``when``, ``error_when``."""
    for cid, cell in profile.cells.items():
        if cell.when is not None:
            yield f"/cells/{_escape(cid)}/when", cell.when
    for index, edge in enumerate(profile.edges):
        if edge.when is not None:
            yield f"/edges/{index}/when", edge.when
    if profile.error_when is not None:
        yield "/error_when", profile.error_when


def _matching_prefix(path: str, prefixes: tuple[str, ...]) -> str | None:
    for prefix in prefixes:
        if path == prefix or path.startswith(f"{prefix}/"):
            return prefix
    return None


def unlisted_path_issues(
    profile: ArchitectureProfile, unlisted_paths: Iterable[str]
) -> list[Issue]:
    """조건이 목록 본문에 없는 경로를 보면 경고한다(M-4, ``architecture.condition_path_unlisted``).

    구조도 판정은 목록용 이벤트로만 하므로, 목록에서 빠지는 경로(무엇이 빠지는지는 호출자가
    데이터로 준다 — 이 함수는 경로 이름을 모른다)를 보는 조건은 늘 값이 없어 맞지 않는다.

    Args:
        profile: 프로필.
        unlisted_paths: 목록 본문에 없는 경로 접두(JSON Pointer, 예: 로그 연동이 주는 값).
            조건 경로가 접두와 같거나 ``접두/``로 시작하면 걸린다. 빈 값·``/``는 무시한다
            (문서 전체를 뜻하므로).

    Returns:
        warning 이슈 목록(``path`` = 조건 항목의 ``path`` 위치, ``details.prefix`` = 걸린 접두,
        ``details.condition_path`` = 조건 경로). 접두가 없으면 빈 목록.
    """
    prefixes = tuple(dict.fromkeys(p.rstrip("/") for p in unlisted_paths if p.rstrip("/")))
    if not prefixes:
        return []
    issues: list[Issue] = []
    for base, spec in _condition_specs(profile):
        for mode, items in (("all", spec.all), ("any", spec.any)):
            for index, item in enumerate(items or ()):
                prefix = _matching_prefix(item.path, prefixes)
                if prefix is None:
                    continue
                issues.append(
                    _issue(
                        "warning",
                        KnownIssueCodes.ARCHITECTURE_CONDITION_PATH_UNLISTED,
                        f"조건 경로 {item.path!r}은(는) 목록 본문에 없어 맞지 않습니다"
                        f"(구조도는 목록 본문만 봅니다. 걸린 경로: {prefix!r})",
                        f"{base}/{mode}/{index}/path",
                        prefix=prefix,
                        condition_path=item.path,
                    )
                )
    return issues


def profile_issues(
    profile: ArchitectureProfile,
    *,
    operators: Mapping[str, ConditionOperator],
    filters: Collection[str] | None = None,
    profile_id: str | None = None,
    unlisted_paths: Iterable[str] = (),
) -> list[Issue]:
    """프로필을 검사한다.

    본다: id 글자 규칙(프로필·칸·연결·영역), 연결·영역 id 중복, 없는 칸을 가리키는 연결·수집 범위,
    없는 영역을 가리키는 칸, 모르는 지표 이름, 모르는 연결 종류, 하위 구조도의 모르는 필터 이름,
    조건(모르는 연산자·값 형식, `ac-conditions` 저장 전 검사).

    Args:
        profile: 프로필.
        operators: 조건 연산자(등록된 것).
        filters: 하위 구조도가 쓸 수 있는 필터 이름(로그 질의가 아는 이름). None이면 보지 않는다.
        profile_id: 주면 프로필 id 글자 규칙도 본다.
        unlisted_paths: 목록 본문에 없는 경로 접두(``unlisted_path_issues``). 비우면(기본) 보지
            않는다.

    Returns:
        이슈 목록(`path` = 프로필 기준 JSON Pointer). 오류(error)·경고(warning) 모두 저장은
        막지 않는다.
    """
    issues: list[Issue] = []
    if profile_id is not None and (bad := _bad_id(profile_id, "프로필", "")):
        issues.append(bad)

    zone_ids: set[str] = set()
    for index, zone in enumerate(profile.zones):
        path = f"/zones/{index}/id"
        if bad := _bad_id(zone.id, "영역", path):
            issues.append(bad)
        if zone.id in zone_ids:
            issues.append(
                _issue(
                    "error",
                    KnownArchitectureIssueCodes.DUPLICATE_ID,
                    f"영역 id {zone.id!r}이(가) 겹칩니다",
                    path,
                    id=zone.id,
                )
            )
        zone_ids.add(zone.id)

    for cid, cell in profile.cells.items():
        base = f"/cells/{_escape(cid)}"
        if bad := _bad_id(cid, "칸", base):
            issues.append(bad)
        if cell.zone is not None and cell.zone not in zone_ids:
            issues.append(
                _issue(
                    "warning",
                    KnownArchitectureIssueCodes.UNKNOWN_ZONE,
                    f"칸 {cid!r}의 영역 {cell.zone!r}이(가) 없습니다",
                    f"{base}/zone",
                    zone=cell.zone,
                )
            )
        issues.extend(_metric_issues(cell.metrics, base))
        if cell.drill is not None and filters is not None and cell.drill.filter not in filters:
            issues.append(
                _issue(
                    "warning",
                    KnownArchitectureIssueCodes.UNKNOWN_DRILL_FILTER,
                    f"하위 구조도의 걸러낼 항목 {cell.drill.filter!r}을(를) 모릅니다",
                    f"{base}/drill/filter",
                    filter=cell.drill.filter,
                )
            )
        if cell.when is not None:
            issues.extend(condition_issues(cell.when, operators, base_path=f"{base}/when"))

    edge_ids: set[str] = set()
    for index, edge in enumerate(profile.edges):
        base = f"/edges/{index}"
        if bad := _bad_id(edge.id, "연결", f"{base}/id"):
            issues.append(bad)
        if edge.id in edge_ids:
            issues.append(
                _issue(
                    "error",
                    KnownArchitectureIssueCodes.DUPLICATE_ID,
                    f"연결 id {edge.id!r}이(가) 겹칩니다. 뒤의 연결은 그리지 않습니다",
                    f"{base}/id",
                    id=edge.id,
                )
            )
        edge_ids.add(edge.id)
        for end, value in (("from", edge.from_), ("to", edge.to)):
            if value not in profile.cells:
                issues.append(
                    _issue(
                        "error",
                        KnownArchitectureIssueCodes.UNKNOWN_CELL,
                        f"연결 {edge.id!r}이(가) 없는 칸 {value!r}을(를) 가리킵니다",
                        f"{base}/{end}",
                        cell=value,
                    )
                )
        if edge.kind not in _EDGE_KINDS:
            issues.append(
                _issue(
                    "warning",
                    KnownArchitectureIssueCodes.UNKNOWN_EDGE_KIND,
                    f"연결 종류 {edge.kind!r}을(를) 모릅니다. 구조 연결로 그립니다",
                    f"{base}/kind",
                    kind=edge.kind,
                )
            )
        issues.extend(_metric_issues(edge.metrics, base))
        if edge.when is not None:
            issues.extend(condition_issues(edge.when, operators, base_path=f"{base}/when"))

    for kind, coverage in profile.coverage.items():
        base = f"/coverage/{_escape(kind)}"
        for index, cid in enumerate(coverage.cells):
            if cid not in profile.cells:
                issues.append(
                    _issue(
                        "warning",
                        KnownArchitectureIssueCodes.UNKNOWN_CELL,
                        f"수집 범위 {kind!r}이(가) 없는 칸 {cid!r}을(를) 가리킵니다",
                        f"{base}/cells/{index}",
                        cell=cid,
                    )
                )
        for cid in coverage.partial:
            if cid not in profile.cells:
                issues.append(
                    _issue(
                        "warning",
                        KnownArchitectureIssueCodes.UNKNOWN_CELL,
                        f"수집 범위 {kind!r}의 부분 표시가 없는 칸 {cid!r}을(를) 가리킵니다",
                        f"{base}/partial/{_escape(cid)}",
                        cell=cid,
                    )
                )

    if profile.error_when is not None:
        issues.extend(condition_issues(profile.error_when, operators, base_path="/error_when"))
    issues.extend(unlisted_path_issues(profile, unlisted_paths))
    return issues


def _error_path(loc: tuple[int | str, ...]) -> str:
    return "".join(f"/{_escape(str(part))}" for part in loc)


def check_profile_data(
    data: Any,
    *,
    operators: Mapping[str, ConditionOperator],
    filters: Collection[str] | None = None,
    profile_id: str | None = None,
    unlisted_paths: Iterable[str] = (),
) -> list[Issue]:
    """편집 중인 프로필 본문(읽은 YAML 객체)을 검사한다. 형식 오류도 예외가 아니라 이슈로 낸다.

    Returns:
        형식이 틀리면 `architecture.invalid` 하나(`details.errors` = 오류 목록
        `{path, message, type}`), 맞으면 `profile_issues` 결과.
    """
    try:
        profile = ArchitectureProfile.model_validate(data)
    except ValidationError as exc:
        errors = [
            {"path": _error_path(err["loc"]), "message": err["msg"], "type": err["type"]}
            for err in exc.errors(include_url=False, include_context=False, include_input=False)
        ]
        issues = [
            _issue(
                "error",
                KnownArchitectureIssueCodes.INVALID,
                f"프로필 형식이 맞지 않습니다({len(errors)}곳)",
                errors[0]["path"] if errors else "",
                errors=errors,
            )
        ]
        if profile_id is not None and (bad := _bad_id(profile_id, "프로필", "")):
            issues.insert(0, bad)
        return issues
    return profile_issues(
        profile,
        operators=operators,
        filters=filters,
        profile_id=profile_id,
        unlisted_paths=unlisted_paths,
    )
