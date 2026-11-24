import type { ReactNode } from "react";
import type { SessionStatus } from "@agent-console/contracts";
import { Banner, Button, Disclosure } from "@agent-console/ui";

/** 배너·상태 칩 문구(메시지 표에서 주입). */
export interface SessionMissingBannerTexts {
  title: string;
  body: string;
  /** 일부 노드만 맥락이 없을 때의 본문 */
  bodyPartial: (n: number) => string;
  continueFresh: string;
  newConversation: string;
  details: string;
  settingsLink: string;
  armed: string;
  cancel: string;
  /** 상태 값 → 칩 글자(모르는 값은 원문) */
  stateLabel: (state: string) => string;
  detailsLabel: string;
}

export interface SessionMissingBannerProps {
  texts: SessionMissingBannerTexts;
  items: readonly SessionStatus[];
  missingCount: number;
  partial: boolean;
  /** `[새 세션으로 계속]`을 눌러 다음 전송 한 번이 새 세션으로 가는 모드 */
  armed: boolean;
  onArm: () => void;
  onCancel: () => void;
  onNewConversation: () => void;
  /** 노드 id → 표시 이름 */
  nodeLabel: (nodeId: string) => string;
  /** 세션 기록 보관 설정으로 가는 링크(앱이 라우터 링크를 넣는다) */
  settingsLink?: ReactNode;
  /** 경쟁 상태로 서버가 막았을 때 읽어 주기 */
  assertive?: boolean;
}

/**
 * 대화 맨 위 "세션 기록 없음" 배너(표현 컴포넌트, API를 모른다).
 * 모드가 켜지면 info 한 줄로 바뀌고, 포커스 이동은 호출자가 한다.
 */
export function SessionMissingBanner(p: SessionMissingBannerProps) {
  const { texts: t } = p;
  if (p.armed) {
    return (
      <div className="chat-session-banner" role="region" aria-label={t.title} data-state="armed">
        <Banner tone="info" actions={<Button size="sm" onClick={p.onCancel}>{t.cancel}</Button>}>
          {t.armed}
        </Banner>
      </div>
    );
  }
  return (
    <div className="chat-session-banner" role="region" aria-label={t.title} data-state="missing" {...(p.assertive ? { "aria-live": "assertive" as const } : {})}>
      <Banner
        tone="warning"
        title={t.title}
        actions={
          <>
            <Button size="sm" variant="primary" data-session-arm="" onClick={p.onArm}>{t.continueFresh}</Button>
            <Button size="sm" onClick={p.onNewConversation}>{t.newConversation}</Button>
          </>
        }
      >
        <div>{p.partial ? t.bodyPartial(p.missingCount) : t.body}</div>
        <Disclosure summary={t.details}>
          <ul className="chat-session-items" aria-label={t.detailsLabel}>
            {p.items.map((i) => (
              <li key={i.node_id}>
                <span>{p.nodeLabel(i.node_id)}</span> <span className="app-muted">{i.backend}</span> <span className="chat-session-chip" data-state={i.state}>{t.stateLabel(i.state)}</span>
              </li>
            ))}
          </ul>
          {p.settingsLink}
        </Disclosure>
      </Banner>
    </div>
  );
}
