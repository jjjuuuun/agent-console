import { Link } from "react-router";
import { StatusChip } from "@agent-console/ui";
import { messages as appMessages } from "../../app/messages";
import { folderHomeMessages as m } from "./folderHomeMessages";
import { relativeTime, type ActivityRow } from "./projectHomeLib";

export interface RecentActivityCardProps {
  rows: readonly ActivityRow[];
  loading: boolean;
  failed: boolean;
  /** 기록을 읽을 수 없는 상태(기록 파일 오류·폴더 없음)면 안내로 바꾼다 */
  unreadable: boolean;
  /** 상세 주소. 꺼진 기능은 undefined(그 행·링크가 없다) */
  chatHref: ((id: string) => string) | undefined;
  runHref: ((id: string) => string) | undefined;
  chatsAllHref: string | undefined;
  runsAllHref: string | undefined;
  nowMs: number;
}

/** "최근 활동" 카드(표현 전용, §4.4 ③): 채팅·실행을 시간순으로 합친 한 목록. 기능 이름은 모른다(주소는 호출한 쪽이 준다). */
export function RecentActivityCard(p: RecentActivityCardProps) {
  return (
    <section className="prj-card prj-activity" aria-labelledby="prj-activity-title" data-testid="project-activity-card">
      <header className="prj-card-head">
        <h2 id="prj-activity-title" className="prj-card-title">{m.home.activityTitle}</h2>
      </header>
      {p.unreadable ? (
        <p className="app-muted">{m.home.activityUnreadable}</p>
      ) : p.failed && p.rows.length === 0 ? (
        <p className="app-muted">{m.home.activityLoadFailed}</p>
      ) : p.rows.length === 0 ? (
        <p className="app-muted">{p.loading ? m.home.loading : m.home.activityEmpty}</p>
      ) : (
        <ul className="prj-activity-list">
          {p.rows.map((r) => {
            const href = r.origin === "chat" ? p.chatHref?.(r.id) : p.runHref?.(r.id);
            const title = r.title === "" ? m.home.untitled : r.title;
            const body = (
              <>
                <span className="prj-kind-chip">{r.origin === "chat" ? m.home.activityChat : m.home.activityRun}</span>
                <span className="prj-activity-title ac-ellipsis" title={title}>{title}</span>
                {r.status === undefined ? null : <StatusChip status={r.status} kind="run" label={appMessages.runStatus[r.status] ?? r.status} compact />}
                <span className="prj-activity-time app-muted">{relativeTime(p.nowMs, r.at)}</span>
              </>
            );
            return <li key={r.key}>{href === undefined ? <span className="prj-activity-row">{body}</span> : <Link className="prj-activity-row" to={href}>{body}</Link>}</li>;
          })}
        </ul>
      )}
      <footer className="prj-activity-foot">
        {p.chatsAllHref === undefined ? null : <Link to={p.chatsAllHref}>{m.home.activityAllChats} →</Link>}
        {p.runsAllHref === undefined ? null : <Link to={p.runsAllHref}>{m.home.activityAllRuns} →</Link>}
      </footer>
    </section>
  );
}
