import type { ConversationSessions, SessionStatus } from "@agent-console/contracts";

/** 세션 이어 가기 상태를 화면 표시로 옮긴 결과(순수 함수, 상태 문자열은 열린 값이라 아는 값만 해석한다). */
export interface SessionView {
  /** 이어 갈 수 없음: 맨 위 배너를 보이고 전송은 선택 전까지 막는다. 판정은 `continuable` 하나로 한다. */
  blocked: boolean;
  /** `missing`인 노드 수(배너 본문 둘째 문장 분기용). */
  missingCount: number;
  /** 일부 노드만 `missing`인가(`items` 중 이어 가기 개념이 있는 노드 기준). */
  partial: boolean;
  /** 입력창 아래 info 줄 종류. `archived`가 있으면 그것만. `continuable == false`이면 없다. */
  info: "archived" | "relocatable" | undefined;
  items: readonly SessionStatus[];
}

/** `GET /conversations/{id}/sessions` 응답 → 표시 값. 응답이 없으면(요청 중·실패) 아무것도 막지 않는다. */
export function sessionViewOf(data: ConversationSessions | undefined): SessionView {
  const items = data?.items ?? [];
  if (data === undefined) return { blocked: false, missingCount: 0, partial: false, info: undefined, items };
  const missingCount = items.filter((i) => i.state === "missing").length;
  const blocked = !data.continuable;
  const counted = items.filter((i) => i.state !== "not_applicable").length;
  const info = blocked ? undefined : items.some((i) => i.state === "archived") ? "archived" : items.some((i) => i.state === "relocatable") ? "relocatable" : undefined;
  return { blocked, missingCount, partial: blocked && missingCount > 0 && missingCount < counted, info, items };
}
