import { Button } from "@agent-console/ui";
import { StartGuide, startMessages } from "../start";
import { chatMessages } from "./chatMessages";
import type { TeamSummary } from "./lib/team";

const te = chatMessages.empty;

export interface EmptyConversationProps {
  teamName: string | undefined;
  description?: string | undefined;
  summary: TeamSummary | undefined;
  /** 계획 요약을 읽는 중 */
  summaryLoading?: boolean;
  /** 계획 요약을 읽지 못함(나머지 카드는 그대로 동작) */
  summaryFailed?: boolean;
  onRetrySummary?: () => void;
}

function Line({ label, names }: { label: string; names: readonly string[] }) {
  return (
    <div className="chat-empty-line">
      <dt>{label}</dt>
      <dd>{names.length > 0 ? names.join(", ") : <span className="app-muted">{te.none}</span>}</dd>
    </div>
  );
}

/** 턴이 하나도 없는 대화: 팀 구성이 무엇을 받고 무엇을 답하는지 요약한다(그래프에서 계산한 값을 받는다). */
export function EmptyConversation({ teamName, description, summary, summaryLoading, summaryFailed, onRetrySummary }: EmptyConversationProps) {
  return (
    <section className="chat-empty-card" aria-label={teamName ?? te.teamUnknown}>
      <h2 className="app-block-title">{teamName ?? te.teamUnknown}</h2>
      {description ? <p className="app-muted">{description}</p> : null}
      {summary ? (
        <dl className="chat-empty-lines">
          <Line label={te.entries} names={summary.entries} />
          <Line label={te.answers} names={summary.answers} />
          <Line label={te.askers} names={summary.askers} />
        </dl>
      ) : summaryLoading ? (
        <p className="app-muted" role="status">{te.summaryLoading}</p>
      ) : summaryFailed ? (
        <p className="app-muted" role="alert">
          {te.summaryFailed}{" "}
          {onRetrySummary ? <Button onClick={onRetrySummary}>{te.summaryRetry}</Button> : null}
        </p>
      ) : null}
      <p>{te.firstMessage}</p>
    </section>
  );
}

export interface StartCardProps {
  /** 같은 화면 안에서 대화상자를 여는 [새 대화] 동작(없으면 대화 화면으로 이동) */
  onNew?: () => void;
  onDismiss: () => void;
}

/** 시작하기 카드: 제목 + 닫기 + 공용 첫 단계 안내(`StartGuide`: 바로 시작 줄 + 직접 만들기 3단계). */
export function StartCard({ onNew, onDismiss }: StartCardProps) {
  return (
    <section className="chat-start" aria-label={startMessages.title}>
      <div className="chat-start-head">
        <h2 className="app-block-title">{startMessages.title}</h2>
        <Button size="sm" variant="ghost" onClick={onDismiss}>{startMessages.close}</Button>
      </div>
      <p className="app-muted">{startMessages.description}</p>
      <StartGuide {...(onNew ? { actionOverrides: { talk: onNew } } : {})} />
    </section>
  );
}
