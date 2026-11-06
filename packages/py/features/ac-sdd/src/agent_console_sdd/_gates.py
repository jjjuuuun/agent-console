"""관문: 조건 맥락 만들기, 관문 평가(`ac-conditions`), 관문이 보는 문서 id(design §6R.1.5, §6R.18
Q5·Q12).

관문을 평가하는 때(실행 시작 전 `run`, 작업 상태 바꾸기 전 `task_status`, 문서 상태 전환 전
`document_state`)는 코드에 고정된 개념이다(§6R.12). 어느 관문이 어느 때에 걸리는지·조건은 데이터다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from agent_console_conditions import ConditionOperator, evaluate_conditions
from agent_console_contracts import ConditionOutcome
from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.definitions import Issue
from agent_console_contracts.sdd import (
    ParsedTask,
    SddGateBlockedDetails,
    SpecDefinition,
    SpecGate,
    SpecIndex,
    SpecRules,
    SpecTemplate,
)

from ._errors import GateBlockedError

__all__ = [
    "GateBlock",
    "evaluate_gates",
    "gate_context",
    "gate_documents",
    "require_gates",
]

_DOCUMENTS_PREFIX = "/documents/"


def _unescape(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _paths(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        path = value.get("path")
        if isinstance(path, str):
            yield path
        for item in value.values():
            if isinstance(item, Mapping | list):
                yield from _paths(item)
    elif isinstance(value, list):
        for item in value:
            yield from _paths(item)


def gate_documents(gate: SpecGate) -> list[str]:
    """관문 조건이 보는 문서 id(`/documents/<id>/…` 포인터에서, 중첩 `all`·`any` 포함, 처음 나온
    순).

    화면의 [문서 열기]에 쓴다(`SddGateBlockedDetails.document_ids`, §6R.18 Q5).
    """
    out: list[str] = []
    for path in _paths(gate.require.model_dump(mode="json", by_alias=True)):
        if not path.startswith(_DOCUMENTS_PREFIX):
            continue
        token = path[len(_DOCUMENTS_PREFIX) :].split("/", 1)[0]
        doc_id = _unescape(token)
        if doc_id and doc_id not in out:
            out.append(doc_id)
    return out


def gate_context(
    spec: SpecDefinition | SpecTemplate,
    index: SpecIndex | None = None,
    *,
    task: ParsedTask | None = None,
    change: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """관문·프로필 조건의 판단 대상(JSON 객체)을 만든다.

    모양(design §6R.1.5): ``{spec: {id, name}, documents: {<id>: {state, title}}, task: {key, id,
    status, fields, ready, stage}, stage: {id, title, done, total}, change: {...}}``.
    `task`·`stage`는
    작업이 있을 때만, `change`(바꾸려는 것 — 작업 상태 `{from, to}`, 문서 상태 `{document, from, to,
    by}`)는 줄 때만 들어간다.
    """
    ctx: dict[str, Any] = {
        "spec": {"id": spec.id, "name": spec.name},
        "documents": {d.id: {"state": d.state, "title": d.title} for d in spec.documents},
    }
    if task is not None:
        ctx["task"] = {
            "key": task.key,
            "id": task.id,
            "status": task.status,
            "fields": dict(task.fields),
            "ready": task.ready,
            "stage": task.stage.id if task.stage else None,
            "requirements": list(task.requirements),
            "dependencies": list(task.dependencies),
        }
        if task.stage is not None:
            stage: dict[str, Any] = {"id": task.stage.id, "title": task.stage.title}
            for s in index.stages if index is not None else ():
                if s.id == task.stage.id:
                    stage.update(done=s.done, total=s.total)
                    break
            ctx["stage"] = stage
    if change is not None:
        ctx["change"] = dict(change)
    return ctx


@dataclass(frozen=True, slots=True)
class GateBlock:
    """막은 관문 하나와 근거."""

    gate: SpecGate
    outcome: ConditionOutcome

    @property
    def details(self) -> SddGateBlockedDetails:
        """오류·동작 `disabled`의 `details`."""
        return SddGateBlockedDetails(
            gate_id=self.gate.id, message=self.gate.message, document_ids=gate_documents(self.gate)
        )

    def issue(self) -> Issue:
        """작업 동작 `disabled`·한꺼번에 시작 결과에 실을 이슈(`sdd.gate_blocked`)."""
        return Issue(
            severity="error",
            code=KnownIssueCodes.SDD_GATE_BLOCKED,
            message=self.gate.message or f"관문 '{self.gate.id}'이(가) 막았습니다.",
            details=self.details.model_dump(mode="json"),
        )


def evaluate_gates(
    rules: SpecRules | None,
    target: str,
    context: Mapping[str, Any],
    *,
    operators: Mapping[str, ConditionOperator],
) -> list[GateBlock]:
    """`target`(`KnownGateTargets` — run·task_status·document_state, 열린 문자열)에 걸린 관문 중
    조건이 맞지 않는 것을 규칙 순서대로 돌려준다(빈 목록 = 통과).

    조건 평가는 `ac-conditions`다. 모르는 연산자·없는 값은 거짓이라 막힌다(안전한 쪽).
    """
    blocks: list[GateBlock] = []
    for gate in (rules.gates if rules else None) or ():
        if target not in gate.applies_to:
            continue
        outcome = evaluate_conditions(gate.require, dict(context), operators)
        if not outcome.result:
            blocks.append(GateBlock(gate=gate, outcome=outcome))
    return blocks


def require_gates(
    rules: SpecRules | None,
    target: str,
    context: Mapping[str, Any],
    *,
    operators: Mapping[str, ConditionOperator],
) -> None:
    """`evaluate_gates`에서 막힌 첫 관문이 있으면 `GateBlockedError`를 던진다."""
    blocks = evaluate_gates(rules, target, context, operators=operators)
    if blocks:
        raise GateBlockedError(blocks[0].details)
