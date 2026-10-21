import { useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";
import type { GraphSummary } from "@agent-console/contracts";
import { Banner, Button, Dialog } from "@agent-console/ui";
import { messages as appMessages } from "../../app/messages";
import { formatRelative } from "../../lib/format";
import { chatMessages } from "./chatMessages";
import { hasEntry } from "./lib/team";
import { blocksRun, ValidationChip, teamMessages as vt } from "../teams";
import { useImeGuard } from "../../lib/ime";

const t = chatMessages.newDialog;

export interface TeamPickerDialogProps {
  open: boolean;
  title: string;
  confirmLabel: string;
  graphs: readonly GraphSummary[];
  loading?: boolean;
  loadError?: string | null;
  /** 팀 구성 id → 마지막 사용 시각(epoch 초) */
  lastUsed?: ReadonlyMap<string, number>;
  /** 미리 선택할 팀 구성 id(사용할 수 없으면 무시) */
  preselectedId?: string | undefined;
  /** 현재 대화의 팀 구성 id: 전환 때 "현재" 표시 */
  currentId?: string | undefined;
  /** 제목 입력(새 대화에서만) */
  withTitle?: boolean;
  /** 확인 단계 안내문(전환용). 있으면 목록 아래에 항상 보인다 */
  notice?: string;
  nowMs: number;
  busy?: boolean;
  error?: string | null;
  /** 팀 구성 편집 화면 경로(`/teams`) */
  teamsPath: string;
  /** 검증 요약 칩의 [문제 보기] 펼침 본문(서버 이슈를 읽어 그리는 쪽은 호출자). 없으면 펼침 버튼이 없다 */
  renderIssues?: (graph: GraphSummary) => ReactNode;
  onConfirm: (graphId: string, title: string) => void;
  onClose: () => void;
}

/**
 * 팀 구성 고르기 다이얼로그: 새 대화와 대화 중 팀 구성 전환이 같이 쓴다.
 * 입구가 없거나 검증 요약이 실행을 막는(`validation.blocks_run`) 팀 구성은 `aria-disabled` + 사유 + 편집 링크로 보이고 선택되지 않는다.
 * `validation`이 null인 팀 구성은 계산 안 함이라 막지 않는다.
 */
export function TeamPickerDialog(props: TeamPickerDialogProps) {
  // 열릴 때마다 새로 시작하도록 열려 있을 때만 본문을 둔다(검색어·제목·선택 초기화)
  return props.open ? <TeamPickerBody {...props} /> : null;
}

function TeamPickerBody(props: TeamPickerDialogProps) {
  const { open, graphs } = props;
  const [query, setQuery] = useState("");
  const [pickedId, setPicked] = useState<string | undefined>(undefined);
  const [title, setTitle] = useState("");
  const list = useRef<HTMLUListElement>(null);
  const uid = useId();
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [liveText, setLiveText] = useState("");
  const toggleExpanded = (id: string) =>
    setExpanded((cur) => {
      const next = new Set(cur);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  const usable = (g: GraphSummary) => hasEntry(g) !== false && !blocksRun(g.validation);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q === "" ? graphs : graphs.filter((g) => g.name.toLowerCase().includes(q) || (g.description ?? "").toLowerCase().includes(q));
  }, [graphs, query]);

  const selectable = filtered.filter(usable);
  // 고른 것이 없으면 미리 선택(지정된 팀 → 사용할 수 있는 첫 팀). 목록이 늦게 와도 따라간다.
  const preselect = (graphs.find((g) => g.id === props.preselectedId && usable(g)) ?? graphs.find(usable))?.id;
  const picked = pickedId ?? preselect;
  const onKeyDown = (e: KeyboardEvent<HTMLUListElement>) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    // 막힌 행도 포커스는 받는다(문제 보기·편집으로 갈 수 있게). 선택은 사용할 수 있는 행만.
    const focused = e.target instanceof HTMLElement ? e.target.closest<HTMLElement>("[data-team-id]")?.dataset["teamId"] : undefined;
    const i = filtered.findIndex((g) => g.id === (focused ?? picked));
    const next = filtered[Math.min(filtered.length - 1, Math.max(0, i + (e.key === "ArrowDown" ? 1 : -1)))];
    if (next) {
      if (usable(next)) setPicked(next.id);
      list.current?.querySelector<HTMLElement>(`[data-team-id="${CSS.escape(next.id)}"]`)?.focus();
    }
  };

  // 탭 정지는 라디오 그룹에서 하나: 고른 행 → 없으면 선택 가능한 첫 행 → 전부 막혔으면 보이는 첫 행(E·문제 보기로 갈 수 있게)
  const tabStopId = (selectable.some((g) => g.id === picked) ? picked : selectable[0]?.id) ?? filtered[0]?.id;
  const canConfirm = picked !== undefined && selectable.some((g) => g.id === picked) && !props.busy;
  const ime = useImeGuard();
  const confirm = () => {
    if (picked !== undefined && canConfirm) props.onConfirm(picked, title.trim());
  };

  return (
    <Dialog
      open={open}
      title={props.title}
      onClose={props.onClose}
      wide
      actions={
        <>
          <Button onClick={props.onClose}>{appMessages.common.cancel}</Button>
          <Button variant="primary" disabled={!canConfirm} loading={props.busy} onClick={confirm}>{props.confirmLabel}</Button>
        </>
      }
    >
      <div className="chat-picker" onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") confirm(); }}>
        {props.loading ? (
          <p className="app-muted" role="status">{t.loading}</p>
        ) : props.loadError ? (
          <Banner tone="danger">{props.loadError}</Banner>
        ) : graphs.length === 0 ? (
          <div className="chat-list-empty">
            <p>{t.noTeams}</p>
            <Link className="ac-btn" data-variant="primary" data-size="md" to={props.teamsPath} onClick={props.onClose}>{t.createTeam}</Link>
          </div>
        ) : (
          <>
            <input type="search" className="ac-input" aria-label={t.searchLabel} placeholder={t.searchPlaceholder} value={query} onChange={(e) => setQuery(e.target.value)} />
            {filtered.length === 0 ? <p className="app-muted">{t.noMatches}</p> : null}
            <ul ref={list} role="radiogroup" aria-label={t.teamLabel} className="chat-picker-list" onKeyDown={onKeyDown}>
              {filtered.map((g) => {
                const ok = usable(g);
                const used = props.lastUsed?.get(g.id);
                return (
                  <li key={g.id} role="presentation" className="chat-picker-item" data-team-row={g.id} data-selected={picked === g.id ? "true" : undefined} data-disabled={ok ? undefined : "true"}>
                    <div
                      role="radio"
                      aria-checked={picked === g.id}
                      aria-disabled={ok ? undefined : true}
                      data-team-id={g.id}
                      tabIndex={g.id === tabStopId ? 0 : -1}
                      className="chat-picker-row"
                      onClick={() => ok && setPicked(g.id)}
                      onKeyDown={(e) => {
                        if (e.target !== e.currentTarget) return;
                        if (e.key === "e" || e.key === "E") {
                          if (e.ctrlKey || e.metaKey || e.altKey) return;
                          // E = 이 팀 구성 편집으로(선택 가능 여부와 무관)
                          e.preventDefault();
                          props.onClose();
                          navigate(`${props.teamsPath}/${encodeURIComponent(g.id)}`);
                          return;
                        }
                        if (e.key !== " " && e.key !== "Enter") return;
                        if (e.ctrlKey || e.metaKey) return;
                        e.preventDefault();
                        if (ok) setPicked(g.id);
                        else if (blocksRun(g.validation) && e.key === "Enter" && props.renderIssues) toggleExpanded(g.id);
                        else if (blocksRun(g.validation)) setLiveText(vt.validation.notSelectable);
                      }}
                    >
                      <div className="chat-picker-name">
                        <strong className="ac-ellipsis">{g.name}</strong>
                        {g.id === props.currentId ? <span className="chat-chip">{t.current}</span> : null}
                      </div>
                      {g.description ? <div className="app-muted ac-ellipsis">{g.description}</div> : null}
                      <div className="app-muted chat-picker-meta">
                        <span>{t.nodes(g.node_count)}</span>
                        {used !== undefined ? <span>{t.lastUsed(formatRelative(used, props.nowMs))}</span> : null}
                      </div>
                    </div>
                    {/* 칩·펼침·링크는 라디오 밖에 둔다: aria-disabled 요소 안의 컨트롤은 비활성으로 취급되기 때문 */}
                    {g.validation != null && (blocksRun(g.validation) || (g.validation.error_count ?? 0) > 0 || (g.validation.warning_count ?? 0) > 0) ? (
                      <div className="chat-picker-reason" data-validation={blocksRun(g.validation) ? "blocked" : "info"}>
                        <ValidationChip summary={g.validation} />
                        {props.renderIssues ? (
                          <button
                            type="button"
                            className="app-link-btn"
                            aria-expanded={expanded.has(g.id)}
                            aria-controls={`${uid}-issues-${g.id}`}
                            onClick={() => toggleExpanded(g.id)}
                          >
                            {expanded.has(g.id) ? vt.validation.hideIssues : vt.validation.showIssues} {expanded.has(g.id) ? "▴" : "▾"}
                          </button>
                        ) : null}
                        {blocksRun(g.validation) ? <Link to={`${props.teamsPath}/${encodeURIComponent(g.id)}`} onClick={props.onClose}>{vt.validation.editTeam}</Link> : null}
                      </div>
                    ) : null}
                    {props.renderIssues && expanded.has(g.id) ? <div id={`${uid}-issues-${g.id}`}>{props.renderIssues(g)}</div> : null}
                    {hasEntry(g) === false ? (
                      <div className="chat-picker-reason">
                        <span>{t.noEntry}</span>
                        {/* 막힌 행은 위 줄에 편집 링크가 이미 있다(중복 링크 방지) */}
                        {blocksRun(g.validation) ? null : <Link to={`${props.teamsPath}/${encodeURIComponent(g.id)}`} onClick={props.onClose}>{t.editTeam}</Link>}
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
            {props.withTitle ? (
              <div className="app-field">
                <label htmlFor={`${uid}-title`}>{t.titleLabel}</label>
                <input id={`${uid}-title`} aria-describedby={`${uid}-help`} type="text" className="ac-input" value={title} onChange={(e) => setTitle(e.target.value)} {...ime.handlers} onKeyDown={(e) => { if (e.key === "Enter" && !ime.isIme(e)) { e.preventDefault(); confirm(); } }} />
                <span id={`${uid}-help`} className="app-muted">{t.titleHelp}</span>
              </div>
            ) : null}
          </>
        )}
        <span className="ac-sr-only" role="status" aria-live="polite">{liveText}</span>
        {props.notice ? <Banner tone="warning">{props.notice}</Banner> : null}
        {props.error ? <Banner tone="danger">{props.error}</Banner> : null}
      </div>
    </Dialog>
  );
}
