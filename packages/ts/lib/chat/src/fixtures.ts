import type { ChatTurn, Interaction, InteractionKindDescriptor } from "@agent-console/contracts";

/** 테스트용 임의 데이터. 종류·렌더러 이름은 일부러 제품에 없는 이름도 쓴다. */
export function makeInteraction(over: Partial<Interaction> = {}): Interaction {
  return { id: "i1", run_id: "r1", node_id: "n1", kind: "kind-x", status: "pending", created_at: 1000, ...over };
}

export function makeDescriptor(over: Partial<InteractionKindDescriptor> = {}): InteractionKindDescriptor {
  return { id: "kind-x", title: "임의 종류", ...over };
}

export function makeTurn(over: Partial<ChatTurn> = {}): ChatTurn {
  return { run_id: "r1", user_text: "안녕", status: "completed", replies: [], interactions: [], ...over };
}

export const agentView = (id: string) => ({ name: `이름-${id}`, role: "역할" });
