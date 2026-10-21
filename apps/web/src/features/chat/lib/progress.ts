import type { EdgeTypeDescriptor, Graph } from "@agent-console/contracts";
import type { ProgressStep, StepAvatar } from "@agent-console/chat";
import { delegationMessages as dm, formatRunOrdinal } from "../../delegation";
import type { LiveRun } from "./liveRun";
import { resolveAvatar } from "../../library";
import { agentOfNode, nodeName, type NamingContext } from "./team";

/** 구독에서 받은 서브에이전트 종료 상태 문자열 → 진행 줄 상태. */
function subagentStatus(stopped: string | undefined): string {
  if (stopped === undefined) return "running";
  const s = stopped.toLowerCase();
  if (s.includes("fail") || s.includes("error")) return "failed";
  if (s.includes("cancel") || s.includes("stop") || s.includes("kill")) return "cancelled";
  return "succeeded";
}

/** 자식 Run 최종 상태(Run 상태 어휘) → 진행 줄 상태(노드 상태 어휘). 모르는 값은 그대로. */
function runStatusToStep(status: string | undefined): string {
  switch (status) {
    case undefined:
      return "running";
    case "completed":
      return "succeeded";
    default:
      return status;
  }
}

const TERMINAL = new Set(["succeeded", "failed", "skipped", "cancelled"]);

export interface ProgressInput {
  live: LiveRun;
  graph: Graph | undefined;
  kinds: ReadonlyMap<string, EdgeTypeDescriptor>;
  naming: NamingContext;
  /** 단계 칩 링크(`/runs/:id#node=…`) 생성기. 없으면 링크 없음. */
  hrefFor?: (nodeId: string) => string;
  /** 사유가 붙은 건너뜀의 상태 문구(예: "건너뜀(이어 가기)") */
  skippedWith?: (reason: string) => string;
  /** 자식 Run id → 그 Run의 이벤트로 접은 상태. 없으면 중첩 팀 칩은 하위 단계 없이 보인다 */
  childLive?: Readonly<Record<string, LiveRun>>;
  /** 자식 팀 구성 id → 그래프(칩 이름·하위 단계 이름·진행 숫자의 분모) */
  childGraphs?: Readonly<Record<string, Graph>>;
  /** 자식 실행 화면 주소 */
  childHref?: (runId: string) => string;
  /** 노드 타입 id → 실행되는 노드인가(진행 숫자의 분모에서 사용자 노드 등을 뺀다). 모르면 모든 노드를 센다 */
  executableOf?: (typeId: string) => boolean;
  /** 들여 쓰기 시작 값(자식 실행의 단계는 부모 칩보다 한 단계 깊다) */
  baseIndent?: number;
  /** 자식 실행 안 노드 링크가 가리킬 Run id(없으면 루트) */
  runId?: string;
}

/**
 * 진행 줄 단계. 위임·넘기기 단계(서브에이전트·독립 위임), 반복·반복 한도, 중첩 팀(하위 단계 포함), 실패 처리를 만든다
 * (입구·답변 연결, 리소스 연결은 제외). 방식 라벨은 연결 종류 디스크립터의 `title`, 점선은 `ui_hints.dashed`, 반복·실패 처리는
 * 디스크립터 속성(`cycle`·`handles_failure`)으로 알아본다. 종류 이름은 쓰지 않는다. 회차·호출 번호는 화면에서 +1이다.
 */
export function buildProgressSteps(input: ProgressInput): ProgressStep[] {
  const { live, graph, kinds, naming, hrefFor, skippedWith } = input;
  const base = input.baseIndent ?? 0;
  const nodes = new Map((graph?.nodes ?? []).map((n) => [n.id, n]));
  const edgesById = new Map((graph?.edges ?? []).map((e) => [e.id, e]));
  const name = (id: string) => nodeName(nodes.get(id), id, naming);
  /** 칩 양 끝 노드의 아바타: 에이전트에 묶인 노드만(채팅 답변 머리와 같은 해석 함수) */
  const avatarOf = (id: string): StepAvatar | undefined => {
    const node = nodes.get(id);
    const agent = node === undefined ? undefined : agentOfNode(node, naming);
    if (agent === undefined) return undefined;
    const spec = resolveAvatar(agent);
    return { id: agent.id, name: agent.name, text: spec.text, color: spec.color };
  };
  const ends = (from: string, to: string) => {
    const f = avatarOf(from);
    const t = avatarOf(to);
    return { ...(f ? { fromAvatar: f } : {}), ...(t ? { toAvatar: t } : {}) };
  };
  const seen = new Map<string, number>();
  const keyFor = (nodeId: string) => {
    const n = (seen.get(nodeId) ?? 0) + 1;
    seen.set(nodeId, n);
    return n === 1 ? nodeId : `${nodeId}#${n}`;
  };
  const target = (nodeId: string) => (input.runId === undefined ? {} : { openTarget: { runId: input.runId, nodeId } });
  const entries: { seq: number; step: ProgressStep }[] = [];

  // 같은 노드가 여러 번 열린 흐름 단계(반복 영역 안 노드)는 두 번째부터 회차 표기를 붙인다
  const opened = new Map<string, number>();
  for (const t of live.edges) {
    const edge = edgesById.get(t.edgeId);
    const kind = edge ? kinds.get(edge.kind) : undefined;
    if (kind === undefined || (kind.scheduling !== undefined && kind.scheduling !== "flow") || kind.invocation != null) continue;
    // 반복 연결은 반복 시작 칩이 대신한다(같은 일을 두 칩으로 그리지 않는다)
    if (kind.cycle != null) continue;
    const count = opened.get(t.to) ?? 0;
    opened.set(t.to, count + 1);
    const duration = live.nodeDurationMs[t.to];
    entries.push({
      seq: t.seq,
      step: {
        key: keyFor(t.to),
        status: live.nodeStatus[t.to] ?? "running",
        fromLabel: name(t.from),
        toLabel: name(t.to),
        ...ends(t.from, t.to),
        methodLabel: kind.title,
        ...(kind.ui_hints?.dashed ? { methodDashed: true } : {}),
        ...(duration !== undefined ? { durationMs: duration } : {}),
        indent: base,
        ...(count > 0 ? { iterationLabel: formatRunOrdinal(count, "iteration") } : {}),
        ...(hrefFor ? { href: hrefFor(t.to) } : {}),
        ...target(t.to),
      },
    });
  }
  for (const s of live.subagents) {
    const edge = (graph?.edges ?? []).find((e) => e.source.node === s.delegator && e.target.node === s.target && kinds.get(e.kind)?.invocation != null);
    const kind = edge ? kinds.get(edge.kind) : undefined;
    entries.push({
      seq: s.seq,
      step: {
        key: keyFor(s.target),
        status: subagentStatus(s.stoppedStatus),
        fromLabel: name(s.delegator),
        toLabel: name(s.target),
        ...ends(s.delegator, s.target),
        methodLabel: kind?.title ?? "",
        ...(kind?.ui_hints?.dashed ? { methodDashed: true } : {}),
        ...(s.durationMs !== undefined ? { durationMs: s.durationMs } : {}),
        indent: base + 1,
        ...(hrefFor ? { href: hrefFor(s.target) } : {}),
        ...target(s.target),
      },
    });
  }

  // 독립 위임: 위임자가 부른 대상이 자기 세션으로 실행된다(호출 NodeRun). 위임자 아래 들여 쓰고 `별도 세션` 배지를 단다.
  const callsPerTarget = new Map<string, number>();
  for (const c of live.calls) callsPerTarget.set(c.target, (callsPerTarget.get(c.target) ?? 0) + 1);
  for (const c of live.calls) {
    const edge = (graph?.edges ?? []).find((e) => e.source.node === c.delegator && e.target.node === c.target && kinds.get(e.kind)?.invocation != null);
    const kind = edge ? kinds.get(edge.kind) : undefined;
    entries.push({
      seq: c.seq,
      step: {
        key: `call:${c.key}`,
        status: c.status,
        fromLabel: name(c.delegator),
        toLabel: name(c.target),
        ...ends(c.delegator, c.target),
        methodLabel: kind?.title ?? "",
        ...(kind?.ui_hints?.dashed ? { methodDashed: true } : {}),
        ...(c.durationMs !== undefined ? { durationMs: c.durationMs } : {}),
        indent: base + Math.max(1, c.path.length - 1),
        badge: dm.chat.separateSession,
        ...((callsPerTarget.get(c.target) ?? 0) > 1 ? { callLabel: formatRunOrdinal(c.call, "call") } : {}),
        ...(c.iteration > 0 ? { iterationLabel: formatRunOrdinal(c.iteration, "iteration") } : {}),
        ...(hrefFor ? { href: hrefFor(c.target) } : {}),
        ...target(c.target),
      },
    });
  }

  // 반복: 반복 시작 이벤트 하나당 칩 하나, 반복 한도 도달은 경고 칩
  for (const it of live.iterations) {
    const edge = edgesById.get(it.edgeId);
    const kind = edge ? kinds.get(edge.kind) : undefined;
    entries.push({
      seq: it.seq,
      step: {
        key: `loop:${it.edgeId}#${it.iteration}`,
        status: "succeeded",
        fromLabel: edge ? name(edge.source.node) : "",
        toLabel: edge ? name(edge.target.node) : it.nodeIds.map(name).join(", "),
        methodLabel: `↻ ${kind?.title ?? ""}`.trim(),
        ...(kind?.ui_hints?.dashed ? { methodDashed: true } : {}),
        indent: base,
        iterationLabel: formatRunOrdinal(it.iteration, "iteration"),
        statusLabel: dm.chat.loopStarted,
        ...(input.runId === undefined ? {} : { openTarget: { runId: input.runId, edgeId: it.edgeId } }),
      },
    });
  }
  for (const ex of live.exhausted) {
    const edge = edgesById.get(ex.edgeId);
    const kind = edge ? kinds.get(edge.kind) : undefined;
    entries.push({
      seq: ex.seq,
      step: {
        key: `exhausted:${ex.edgeId}`,
        status: "skipped",
        fromLabel: edge ? name(edge.source.node) : "",
        toLabel: edge ? name(edge.target.node) : "",
        methodLabel: kind?.title ?? "",
        indent: base,
        tone: "warning",
        statusLabel: ex.maxIterations === undefined ? dm.run.judgement.exhaustedNoLimit : dm.chat.exhaustedStep(ex.maxIterations),
        ...(input.runId === undefined ? {} : { openTarget: { runId: input.runId, edgeId: ex.edgeId } }),
      },
    });
  }

  // 중첩 팀: 부모 노드가 자식 Run을 기다리는 동안 칩 하나. 자식 단계는 접고 펼친다.
  for (const c of live.children) {
    const child = input.childLive?.[c.runId];
    const childGraph = c.graphId === undefined ? undefined : input.childGraphs?.[c.graphId];
    const status = runStatusToStep(c.finishedStatus ?? child?.status);
    const total = childGraph === undefined ? undefined : childGraph.nodes?.filter((n) => input.executableOf?.(n.type) !== false).length;
    const done = child === undefined ? undefined : Object.values(child.nodeStatus).filter((st) => TERMINAL.has(st)).length;
    const steps = child === undefined || childGraph === undefined ? undefined : buildProgressSteps({ ...input, live: child, graph: childGraph, baseIndent: base + 1, runId: c.runId, childLive: input.childLive, hrefFor: undefined });
    const teamName = childGraph?.name ?? name(c.nodeId);
    entries.push({
      seq: c.startSeq,
      step: {
        key: `child:${c.runId}`,
        status,
        fromLabel: "",
        toLabel: dm.chat.nestedStep(teamName),
        methodLabel: "",
        solo: true,
        indent: base,
        hint: teamName,
        child: {
          runId: c.runId,
          href: input.childHref?.(c.runId) ?? "",
          nodeLabel: name(c.nodeId),
          ...(total !== undefined && done !== undefined && !TERMINAL.has(status) ? { progress: { done, total } } : {}),
        },
        ...(steps !== undefined && steps.length > 0 ? { children: steps } : {}),
        ...(c.finishedStatus === "failed" ? { tone: "warning" as const } : {}),
      },
    });
  }

  // 실패했지만 그 노드에서 나가는 실패 처리 연결이 지나갔으면 "구현 실패 → 처리됨"
  const handledFrom = new Set<string>();
  for (const t of live.edges) {
    const edge = edgesById.get(t.edgeId);
    if (edge !== undefined && kinds.get(edge.kind)?.handles_failure === true && live.nodeStatus[edge.source.node] === "failed") handledFrom.add(edge.source.node);
  }
  for (const nodeId of handledFrom) {
    const at = live.edges.find((t) => edgesById.get(t.edgeId)?.source.node === nodeId && kinds.get(edgesById.get(t.edgeId)!.kind)?.handles_failure === true);
    entries.push({
      seq: at?.seq ?? 0,
      step: { key: `handled:${nodeId}`, status: "failed", fromLabel: "", toLabel: name(nodeId), methodLabel: "", indent: base, solo: true, tone: "warning", statusLabel: dm.chat.handledStatus, ...(hrefFor ? { href: hrefFor(nodeId) } : {}), ...target(nodeId) },
    });
  }

  // 사유가 붙은 건너뜀(이어 가기의 상류 등)은 연결 없이 노드 하나로 보인다. 이미 연결 단계로 보인 노드는 그 칩의 상태 문구에 사유를 붙인다.
  for (const sk of live.skipped) {
    const label = skippedWith?.(sk.reason) ?? sk.reason;
    const existing = entries.find((e) => e.step.key === sk.nodeId);
    if (existing) {
      existing.step.statusLabel = label;
      continue;
    }
    entries.push({
      seq: sk.seq,
      step: { key: keyFor(sk.nodeId), status: "skipped", fromLabel: "", toLabel: name(sk.nodeId), methodLabel: "", indent: base, solo: true, statusLabel: label, ...(hrefFor ? { href: hrefFor(sk.nodeId) } : {}), ...target(sk.nodeId) },
    });
  }
  return entries.sort((a, b) => a.seq - b.seq).map((e) => e.step);
}

/** 이 진행 줄(자식 단계 포함)의 처리된 실패 수 — 턴 푸터 "실패 {n}건 처리됨". */
export function countHandled(steps: readonly ProgressStep[]): number {
  return steps.reduce((n, s) => n + (s.key.startsWith("handled:") ? 1 : 0) + countHandled(s.children ?? []), 0);
}

const flat = (steps: readonly ProgressStep[]): ProgressStep[] => steps.flatMap((s) => [s, ...flat(s.children ?? [])]);

/** 진행 중인(끝나지 않은) 중첩 팀 칩이 있는가 — 중지 확인 문구에 한 줄을 더하는 조건. */
export function hasRunningChild(steps: readonly ProgressStep[]): boolean {
  return flat(steps).some((s) => s.child !== undefined && !TERMINAL.has(s.status));
}

/** 실패로 끝난 중첩 팀 칩(맨 위 단계 우선). 팀 이름은 칩의 `hint`, 없으면 부모 노드 이름. */
export function failedChildOf(steps: readonly ProgressStep[]): { runId: string; name: string } | undefined {
  const hit = flat(steps).find((s) => s.child !== undefined && s.status === "failed");
  return hit?.child === undefined ? undefined : { runId: hit.child.runId, name: hit.hint ?? hit.child.nodeLabel };
}
