import { Button, EmptyState } from "@agent-console/ui";
import { useHint } from "../../app/hints";
import { useRouteOn } from "../library";
import { chatMessages } from "./chatMessages";
import { useConversationList, useGraphList } from "./chatData";
import { StartCard } from "./EmptyViews";
import { hasEntry } from "./lib/team";
import { ROUTE_ROLES } from "./paths";

const te = chatMessages.empty;

/** 대화를 고르지 않았을 때의 오른쪽 영역: 시작하기 카드(대화나 팀 구성이 없을 때) 또는 안내. 카드 내용은 공용 `StartGuide`다. */
export function ChatHome({ onNew }: { onNew: () => void }) {
  const teamsOn = useRouteOn(ROUTE_ROLES.graph);
  const graphs = useGraphList(teamsOn);
  const conversations = useConversationList();
  const hint = useHint("start.dismissed");

  const ready = (!teamsOn || graphs.data !== undefined) && conversations.data !== undefined;
  const noUsableTeam = teamsOn && !(graphs.data ?? []).some((g) => hasEntry(g) !== false);
  const showStart = ready && hint.visible && ((conversations.data?.length ?? 0) === 0 || noUsableTeam);

  return (
    <div className="chat-home">
      {showStart ? (
        <StartCard onNew={onNew} onDismiss={hint.dismiss} />
      ) : (
        <EmptyState
          title={te.selectOrStart}
          description={te.selectOrStartBody}
          action={<Button variant="primary" onClick={onNew}>{te.startNew}</Button>}
        />
      )}
    </div>
  );
}
