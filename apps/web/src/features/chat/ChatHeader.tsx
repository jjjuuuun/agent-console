import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { Button, Icon } from "@agent-console/ui";
import { ActionMenu, type ActionMenuItem } from "./ActionMenu";
import { chatMessages } from "./chatMessages";
import { useImeGuard } from "../../lib/ime";

const t = chatMessages.header;

export interface ChatHeaderProps {
  title: string;
  /** 제목 편집을 연다(F2 단축키가 true로 바꾼다) */
  renaming: boolean;
  onRenamingChange: (renaming: boolean) => void;
  onRename: (title: string) => void;
  /** 팀 구성 이름. undefined면 삭제된 팀 구성 */
  teamName: string | undefined;
  teamHref: string | undefined;
  /** 마지막 Run 상세 링크(없으면 버튼 숨김) */
  runHref: string | undefined;
  waitingCount: number;
  onJumpToPending: () => void;
  teamMenu: readonly ActionMenuItem[];
  moreMenu: readonly ActionMenuItem[];
  /** 더보기 메뉴 아래 읽기 전용 줄(답변 표시 방식) */
  moreFooter?: React.ReactNode;
  onToggleList: () => void;
  listOpen: boolean;
}

/** 제목 편집 입력: 열릴 때 현재 제목으로 시작해 선택된다. Enter 저장, Esc 취소, 포커스를 잃으면 저장. */
function TitleInput({ title, onCommit, onCancel }: { title: string; onCommit: (value: string) => void; onCancel: () => void }) {
  const [draft, setDraft] = useState(title);
  const input = useRef<HTMLInputElement>(null);
  const done = useRef(false);
  const ime = useImeGuard();
  const finish = (fn: () => void) => {
    if (done.current) return;
    done.current = true;
    fn();
  };
  useEffect(() => {
    input.current?.focus();
    input.current?.select();
  }, []);
  return (
    <input
      ref={input}
      className="chat-title-input"
      aria-label={t.renameLabel}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => finish(() => onCommit(draft))}
      {...ime.handlers}
      onKeyDown={(e) => {
        if (e.key === "Enter" && !ime.isIme(e)) {
          e.preventDefault();
          finish(() => onCommit(draft));
        } else if (e.key === "Escape") {
          e.stopPropagation();
          finish(onCancel);
        }
      }}
    />
  );
}

/** 채팅 영역 헤더(48px). 제목 인라인 편집, 팀 구성 칩, 마지막 실행 상세 아이콘 링크(글자 버튼 없음), 응답 대기 칩, 더보기 메뉴. 표현 전용. */
export function ChatHeader(props: ChatHeaderProps) {
  const { title, renaming } = props;
  return (
    <header className="chat-header">
      <button type="button" className="ac-btn chat-list-toggle" data-variant="ghost" data-size="sm" aria-label={t.toggleListLabel} aria-expanded={props.listOpen} onClick={props.onToggleList}>
        {t.toggleList}
      </button>
      {renaming ? (
        <TitleInput
          title={title}
          onCommit={(next) => {
            props.onRenamingChange(false);
            if (next.trim() !== title.trim()) props.onRename(next.trim());
          }}
          onCancel={() => props.onRenamingChange(false)}
        />
      ) : (
        <button type="button" className="chat-title" title={`${title} (F2)`} onClick={() => props.onRenamingChange(true)}>
          <h1 className="ac-ellipsis">{title}</h1>
        </button>
      )}
      <div className="chat-header-team">
        {props.teamName === undefined ? (
          <span className="chat-chip" data-tone="missing">{chatMessages.list.deletedTeam}</span>
        ) : props.teamHref ? (
          <Link className="chat-chip chat-team-chip" to={props.teamHref} title={t.teamTooltip}>{t.team(props.teamName)} ↗</Link>
        ) : (
          <span className="chat-chip">{t.team(props.teamName)}</span>
        )}
        {props.teamMenu.length > 0 ? <ActionMenu label={chatMessages.menu.changeTeam} items={props.teamMenu} icon="▾" size="sm" /> : null}
      </div>
      <span className="app-spacer" />
      {props.waitingCount > 0 ? (
        <Button size="sm" className="chat-waiting-chip" title={t.waitingChipHint} onClick={props.onJumpToPending}>
          {`⏸ ${t.waitingChip(props.waitingCount)}`}
        </Button>
      ) : null}
      {props.runHref ? (
        <Link className="ac-btn ac-icon-btn" data-variant="ghost" data-size="sm" to={props.runHref} aria-label={t.openRun} title={t.openRun}>
          <Icon name="external-link" />
        </Link>
      ) : null}
      <ActionMenu label={chatMessages.menu.more} items={props.moreMenu} footer={props.moreFooter} />
    </header>
  );
}
