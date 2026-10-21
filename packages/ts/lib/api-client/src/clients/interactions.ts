/** 상호작용(되묻기) REST. */
import type { Interaction, InteractionStatus } from "@agent-console/contracts";
import { enc, query, type RestIo } from "../io";

/** GET `/interactions` 필터. `status: "pending"`이면 대기 목록. */
export interface ListInteractionsParams {
  status?: InteractionStatus;
  conversation_id?: string;
  /** 이 루트 Run과 그 아래 모든 자식 Run의 상호작용(중첩 팀 안의 요청 포함, 5R.13). 응답은 각 `Interaction.run_id` 기준으로 보낸다. */
  root?: string;
  limit?: number;
}

export interface InteractionsClient {
  listInteractions(params?: ListInteractionsParams): Promise<Interaction[]>;
  listRunInteractions(runId: string): Promise<Interaction[]>;
  /**
   * 상호작용에 응답한다. 이미 닫혔으면 `ApiError`(409 `interaction_closed`, `isInteractionClosed`로 구분),
   * 응답이 `response_schema`에 안 맞으면 422 `validation_failed`.
   */
  respondInteraction(runId: string, interactionId: string, response: Record<string, unknown>): Promise<Interaction>;
}

export function createInteractionsClient(io: RestIo): InteractionsClient {
  return {
    listInteractions: (params) => io.request("GET", `/interactions${query(params)}`),
    listRunInteractions: (runId) => io.request("GET", `/runs/${enc(runId)}/interactions`),
    respondInteraction: (runId, interactionId, response) =>
      io.request("POST", `/runs/${enc(runId)}/interactions/${enc(interactionId)}/respond`, { body: { response } }),
  };
}
