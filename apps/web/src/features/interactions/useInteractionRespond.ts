import { useCallback, useState } from "react";
import { ApiError } from "@agent-console/api-client";
import type { FieldError } from "@agent-console/chat";
import type { Interaction } from "@agent-console/contracts";
import { useApi } from "../../app/ApiContext";
import { closedInteraction, fieldProblems, isNetworkError } from "./errors";
import { interactionMessages, type InteractionMessages } from "./messages";

const NO_ERRORS: readonly FieldError[] = [];

export interface InteractionRespondOptions {
  /** 서버가 알려 준 현재 상태(응답 결과·409의 `details.interaction`)를 저장소에 반영 */
  applyInteraction?: (interaction: Interaction) => void;
  /** 성공·닫힘·없음 뒤에 목록을 다시 읽는다 */
  refresh?: () => void;
  /** 닫힘·없음 안내(토스트 등). 없으면 오류 메시지로만 알린다 */
  notify?: (text: string) => void;
  /** 기본 문구를 덮어쓴다 */
  messages?: Partial<InteractionMessages>;
}

export interface InteractionResponder {
  /**
   * 응답을 보낸다. 성공하면 true, 422를 필드 오류로 보여 줄 수 있으면 false(`errorsOf`로 읽는다).
   * 그 밖의 실패는 던진다(카드/입력창의 오류 영역에 메시지가 보인다).
   */
  respond(interaction: Interaction, response: unknown): Promise<boolean>;
  errorsOf(interactionId: string): readonly FieldError[];
}

/**
 * 상호작용 응답 호출 훅. 채팅 카드·입력창 답변·실행 상세가 같은 경로를 쓴다.
 * - 409(이미 닫힘): 서버의 현재 상태 반영 + 안내 + 새로고침 후 던짐
 * - 404: 안내 + 새로고침 후 던짐
 * - 422: 필드 오류로 매핑되면 false, 아니면 서버 메시지로 던짐
 * - 네트워크 오류: 입력 유지 안내로 던짐
 */
export function useInteractionRespond({ applyInteraction, refresh, notify, messages }: InteractionRespondOptions = {}): InteractionResponder {
  const { rest } = useApi();
  const [errors, setErrors] = useState<Readonly<Record<string, readonly FieldError[]>>>({});
  const closed = messages?.closed ?? interactionMessages.closed;
  const notFound = messages?.notFound ?? interactionMessages.notFound;
  const offline = messages?.offline ?? interactionMessages.offline;
  const failed = messages?.failed ?? interactionMessages.failed;

  const respond = useCallback(
    async (interaction: Interaction, response: unknown): Promise<boolean> => {
      setErrors((cur) => (interaction.id in cur ? Object.fromEntries(Object.entries(cur).filter(([k]) => k !== interaction.id)) : cur));
      try {
        const updated = await rest.respondInteraction(interaction.run_id, interaction.id, (response ?? {}) as Record<string, unknown>);
        applyInteraction?.(updated);
        refresh?.();
        return true;
      } catch (e) {
        if (e instanceof ApiError) {
          if (e.isInteractionClosed) {
            const current = closedInteraction(e);
            if (current) applyInteraction?.(current);
            refresh?.();
            notify?.(closed);
            throw new Error(closed, { cause: e });
          }
          if (e.status === 404) {
            refresh?.();
            notify?.(notFound);
            throw new Error(notFound, { cause: e });
          }
          if (e.status === 422) {
            const problems = fieldProblems(e);
            if (problems.length > 0) {
              setErrors((cur) => ({ ...cur, [interaction.id]: problems }));
              return false;
            }
          }
          if (isNetworkError(e)) throw new Error(offline, { cause: e });
        }
        throw e instanceof Error && e.message !== "" ? e : new Error(failed);
      }
    },
    [rest, applyInteraction, refresh, notify, closed, notFound, offline, failed],
  );
  const errorsOf = useCallback((id: string) => errors[id] ?? NO_ERRORS, [errors]);
  return { respond, errorsOf };
}
