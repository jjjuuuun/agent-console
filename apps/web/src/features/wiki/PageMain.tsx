/**
 * 페이지 탭 가운데 칸의 표현 조각(screen-wiki §6.4·§6.6): 페이지 머리(제목·경로·태그·별칭·머리말), 보기 도구줄, 편집 상태 줄, 규칙 시험 칩.
 * 데이터와 콜백은 props이고 요청은 하지 않는다. 제목·경로·태그·머리말 값은 전부 서버 데이터다(웹은 키 이름을 모른다).
 */
import { useId, useState, type ReactNode } from "react";
import { Disclosure, Popover } from "@agent-console/ui";
import { KNOWN_WIKI_WRITE_ACTIONS } from "@agent-console/contracts/constants";
import { ToneChip } from "@agent-console/markdown-doc";
import type { WikiPagePreview, WikiPageView } from "@agent-console/contracts/wiki";
import { GuardedButton, MenuButton } from "../../app/menuParts";
import { severityTone } from "./wikiConfig";
import { wikiMessages as m } from "./messages";

const lastSegment = (path: string): string => path.split("/").pop() ?? path;

/** 머리말 값을 한 줄 글로(문자열이면 그대로, 아니면 JSON 한 줄). */
function frontValue(v: unknown): string {
  if (typeof v === "string") return v;
  try {
    return JSON.stringify(v) ?? "";
  } catch {
    return String(v);
  }
}

export function PageHeaderBlock({ page, onCopyPath }: { page: WikiPageView; onCopyPath: () => void }) {
  const title = page.page.title !== undefined && page.page.title !== "" ? page.page.title : lastSegment(page.page.path);
  const tags = page.page.tags ?? [];
  const aliases = page.page.aliases ?? [];
  const front = Object.entries(page.front_matter ?? {});
  const [aliasOpen, setAliasOpen] = useState(false);
  return (
    <header className="wiki-page-head">
      <h2 className="wiki-page-title" tabIndex={-1} data-wiki-title="" title={title}>{title}</h2>
      <div className="wiki-page-sub">
        <span className="ac-mono-wrap ac-ellipsis wiki-mono app-muted" title={page.page.path}>{page.page.path}</span>
        <button type="button" className="app-link-btn" onClick={onCopyPath}>{m.copy}</button>
        {tags.map((t) => <span key={t} className="wiki-tag" title={t}>{t}</span>)}
        {aliases.length === 0 ? null : (
          <button type="button" className="app-link-btn" aria-expanded={aliasOpen} onClick={() => setAliasOpen(!aliasOpen)}>{m.page.aliases(aliases.length)} {aliasOpen ? "▾" : "▸"}</button>
        )}
      </div>
      {aliasOpen ? <div className="wiki-page-sub">{aliases.map((a) => <span key={a} className="wiki-tag" title={a}>{a}</span>)}</div> : null}
      {front.length === 0 ? null : (
        <Disclosure summary={m.page.frontMatter(front.length)}>
          <dl className="wiki-front">
            {front.map(([k, v]) => (
              <div key={k} className="wiki-front-row">
                <dt className="ac-mono ac-ellipsis" title={k}>{k}</dt>
                <dd className="ac-ellipsis" title={frontValue(v)}>{frontValue(v)}</dd>
              </div>
            ))}
          </dl>
        </Disclosure>
      )}
    </header>
  );
}

export interface ViewToolbarProps {
  blockedReason: string | undefined;
  onEdit: () => void;
  onRename: () => void;
  onDelete: () => void;
  onCopyPath: () => void;
  onOpenHistory: (() => void) | undefined;
  onReload: () => void;
  panelOpen: boolean;
  onTogglePanel: () => void;
  backlinkCount: number;
  panelControls: string;
}

export function ViewToolbar(p: ViewToolbarProps) {
  return (
    <div className="wiki-toolbar-row" role="toolbar" aria-label={m.title}>
      <GuardedButton variant="primary" blockedReason={p.blockedReason} onClick={p.onEdit}>{m.page.edit}</GuardedButton>
      <GuardedButton blockedReason={p.blockedReason} onClick={p.onRename}>{m.page.rename}</GuardedButton>
      <GuardedButton blockedReason={p.blockedReason} onClick={p.onDelete}>{m.page.delete}</GuardedButton>
      <MenuButton
        label={<><span aria-hidden="true">⋯</span><span className="ac-sr-only">{m.page.more}</span></>}
        panelLabel={m.page.more}
        items={[
          { id: "copy", label: m.page.copyPath, onSelect: p.onCopyPath },
          ...(p.onOpenHistory === undefined ? [] : [{ id: "history", label: m.page.openHistory, onSelect: p.onOpenHistory }]),
          { id: "reload", label: m.page.reload, onSelect: p.onReload },
        ]}
      />
      <span className="wiki-spacer" />
      <button type="button" className="wiki-panel-toggle app-btn" aria-expanded={p.panelOpen} aria-controls={p.panelControls} aria-label={p.backlinkCount > 0 && !p.panelOpen ? m.page.panelBadge(p.backlinkCount) : m.page.panel} onClick={p.onTogglePanel}>
        {m.page.panel} {p.panelOpen ? "▸" : "◂"}
      </button>
    </div>
  );
}

/** 편집 상태 줄: 줄·글자 수(KB)·링크 수·이슈 수. 한도의 80%부터 경고, 100% 이상은 위험 톤. */
export function EditStatus({ bytes, maxBytes, links, brokenLinks, issues, large }: { bytes: number; maxBytes: number | null; links: number | null; brokenLinks: number; issues: number; large: boolean }): ReactNode {
  const kb = (n: number) => (n / 1024).toFixed(1);
  const ratio = maxBytes === null || maxBytes === 0 ? 0 : bytes / maxBytes;
  const tone = ratio >= 1 ? "danger" : ratio >= 0.8 ? "warning" : "neutral";
  return (
    <span className="wiki-status-line" data-testid="wiki-status-line">
      <span data-tone={tone} className="wiki-size">{maxBytes === null ? `${kb(bytes)}KB` : m.editor.size(kb(bytes), kb(maxBytes))}</span>
      {links === null ? null : <span>{m.editor.linksCount(links)}{brokenLinks > 0 ? ` ▲ ${brokenLinks}` : ""}</span>}
      {issues > 0 ? <span>⚠ {m.editor.issuesN(issues)}</span> : null}
      {large ? <span className="app-muted">{m.page.large}</span> : null}
    </span>
  );
}

/** 규칙 시험 칩: 통과 · 경고 n · 거부 n. 누르면 서버가 준 규칙 id와 메시지를 그대로 보인다. 거부여도 저장은 막지 않는다. */
export function RuleChip({ preview, onGoto }: { preview: WikiPagePreview; onGoto: (line: number) => void }) {
  const [open, setOpen] = useState(false);
  const results = preview.rule_results ?? [];
  const id = useId();
  // 동작 이름은 서버 열린 문자열이다. 계약이 이름 붙인 거부·경고만 세고 그 밖의 동작은 경고로 본다.
  const rejects = results.filter((r) => r.action === KNOWN_WIKI_WRITE_ACTIONS.REJECT).length;
  const warns = results.length - rejects;
  const rejected = rejects > 0 || preview.would_reject === true;
  const tone = rejected ? "danger" : warns > 0 ? "warning" : "success";
  const label = rejected ? m.editor.rulesReject(Math.max(rejects, 1)) : warns > 0 ? m.editor.rulesWarn(warns) : m.editor.rulesOk;
  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      panelRole="dialog"
      panelLabel={m.editor.rulesTitle}
      renderTrigger={(trigger) => (
        <button type="button" className="wiki-rulechip app-btn" data-tone={tone} {...trigger} aria-describedby={id}>
          <ToneChip label={label} tone={tone} size="normal" />
        </button>
      )}
    >
      <ul className="wiki-rule-rows" id={id}>
        {results.length === 0 ? <li className="app-muted">{m.editor.rulesOk}</li> : null}
        {results.map((r, i) => (
          <li key={`${r.rule_id}:${i}`}>
            <code className="ac-mono">{r.rule_id}</code> <span>{r.message}</span>
            {(r.lines ?? []).length > 0 ? <button type="button" className="app-link-btn" onClick={() => onGoto((r.lines ?? [])[0] as number)}>{m.band.gotoLine}</button> : null}
          </li>
        ))}
      </ul>
    </Popover>
  );
}

export { severityTone };
