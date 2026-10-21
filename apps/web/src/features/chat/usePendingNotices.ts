import { requesterName } from "../../lib/requester";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import type { Agent, Interaction } from "@agent-console/contracts";
import { useToast } from "@agent-console/ui";
import { usePendingInteractions } from "../../shell/pending";
import { chatMessages } from "./chatMessages";
import { chatPaths } from "./paths";

export interface PendingNoticeInput {
  /** 지금 열려 있는 대화(그 대화의 새 대기는 토스트 없이 스크린리더 알림만) */
  currentConversationId: string | undefined;
  agents: ReadonlyMap<string, Agent>;
  /** 에이전트가 없는 요청(검토 등)의 표시 이름(노드 라벨). 모르면 undefined -> 노드 id */
  nodeLabelOf?: (interaction: Interaction) => string | undefined;
  /** 현재 시각(epoch 초) 공급자 — 화면이 열린 뒤에 생긴 대기만 알린다 */
  nowSeconds: () => number;
}

/**
 * 채팅 화면이 열려 있는 동안 새로 생긴 응답 대기를 알린다.
 * 다른 대화의 대기는 토스트(대화 열기 동작 포함), 모든 새 대기는 보이지 않는 aria-live 문구("{actor}이/가 응답을 기다립니다")로.
 * @returns aria-live 영역에 넣을 문구(없으면 빈 문자열)
 */
export function usePendingNotices({ currentConversationId, agents, nowSeconds, nodeLabelOf }: PendingNoticeInput): string {
  const { items } = usePendingInteractions();
  const toast = useToast();
  const navigate = useNavigate();
  const [since] = useState(() => nowSeconds() - 1);
  const nameOf = (i: Interaction) => requesterName(i, i.actor ? agents.get(i.actor)?.name : undefined, nodeLabelOf?.(i));

  // 보이지 않는 aria-live 문구: 화면이 열린 뒤 생긴 새 대기를 알린다(렌더 중 파생 상태 갱신)
  const [announced, setAnnounced] = useState<{ seen: ReadonlySet<string>; text: string }>({ seen: new Set(), text: "" });
  const unseen = items.filter((i) => !announced.seen.has(i.id));
  if (unseen.length > 0) {
    const fresh = unseen.filter((i) => i.created_at >= since);
    setAnnounced({
      seen: new Set([...announced.seen, ...unseen.map((i) => i.id)]),
      text: fresh.length > 0 ? fresh.map((i) => chatMessages.interaction.waitingLive(nameOf(i))).join(". ") : announced.text,
    });
  }

  // 다른 대화의 새 대기는 토스트로(대화 열기 동작 포함)
  const notified = useRef<Set<string>>(new Set());
  useEffect(() => {
    for (const i of items) {
      if (notified.current.has(i.id)) continue;
      notified.current.add(i.id);
      if (i.created_at < since || i.conversation_id == null || i.conversation_id === currentConversationId) continue;
      const conversationId = i.conversation_id;
      toast({
        tone: "info",
        text: chatMessages.interaction.toastWaiting(nameOf(i)),
        action: { label: chatMessages.interaction.toastOpen, onClick: () => void navigate(chatPaths.conversation(conversationId)) },
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, currentConversationId, since, toast, navigate]);

  return announced.text;
}
