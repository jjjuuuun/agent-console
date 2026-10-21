import type { ChatReply, ChatTurn, Interaction, RunStatus } from "@agent-console/contracts";
import type { ReplyEdge } from "./team";
import { isActiveStatus, type LiveRun } from "./liveRun";

/**
 * 최신 상호작용 상태(WS `interactions` 토픽·응답 결과)를 턴의 목록에 덮는다. 목록에 없던 같은 턴의 것은 더한다.
 * 턴의 목록은 루트 실행 기준이라 중첩 팀 자식 실행의 요청(`root_run_id` = 이 턴의 Run)도 섞인다.
 */
export function mergeInteractions(turn: ChatTurn, latest: ReadonlyMap<string, Interaction>): Interaction[] {
  const base = turn.interactions ?? [];
  const ids = new Set(base.map((i) => i.id));
  const merged = base.map((i) => latest.get(i.id) ?? i);
  for (const i of latest.values()) if ((i.root_run_id ?? i.run_id) === turn.run_id && !ids.has(i.id)) merged.push(i);
  return merged.sort((a, b) => a.created_at - b.created_at);
}

/**
 * 스트림용 빈 답변: 스트리밍이 켜진 답변 연결의 출발 노드가 일하는 동안, 아직 `run.reply`가 없으면
 * 빈 문장의 답변 카드를 하나 둔다(스트리밍 텍스트는 `TurnView`가 같은 `node_id`의 답변에 덮어 보인다).
 */
export function streamPlaceholders(live: LiveRun | undefined, replyEdges: readonly ReplyEdge[], existing: readonly ChatReply[], agentOf: (nodeId: string) => string | null): ChatReply[] {
  if (!live) return [];
  const out: ChatReply[] = [];
  for (const re of replyEdges) {
    if (!re.stream) continue;
    const working = live.nodeStatus[re.nodeId] === "running" || live.streaming[re.nodeId] !== undefined;
    if (!working || existing.some((r) => r.edge_id === re.edgeId)) continue;
    out.push({ edge_id: re.edgeId, node_id: re.nodeId, agent_id: agentOf(re.nodeId), label: re.label, order: re.order, final: re.final, text: "" });
  }
  return out;
}

export interface AssembleInput {
  serverTurns: readonly ChatTurn[];
  live: Readonly<Record<string, LiveRun>>;
  interactions: ReadonlyMap<string, Interaction>;
  replyEdges: readonly ReplyEdge[];
  agentOfNode: (nodeId: string) => string | null;
}

/** 서버 턴 + 실시간 상태 → 화면 턴. 서버가 끝났다고 한 턴은 서버 값을 따른다. */
export function assembleTurns({ serverTurns, live, interactions, replyEdges, agentOfNode }: AssembleInput): ChatTurn[] {
  return serverTurns.map((turn) => {
    const lv = live[turn.run_id];
    const serverActive = isActiveStatus(turn.status);
    const status: RunStatus = serverActive && lv?.status !== undefined ? lv.status : turn.status;
    const liveReplies = (lv?.replies ?? []).map((r) => (r.agent_id ? r : { ...r, agent_id: agentOfNode(r.node_id) }));
    const base = liveReplies.length > 0 ? liveReplies : (turn.replies ?? []);
    const active = isActiveStatus(status);
    const replies = active ? [...base, ...streamPlaceholders(lv, replyEdges, base, agentOfNode)] : base;
    return { ...turn, status, replies, interactions: mergeInteractions(turn, interactions) };
  });
}
