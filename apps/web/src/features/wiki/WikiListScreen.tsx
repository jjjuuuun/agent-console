/**
 * 위키 목록 화면(`/wiki`, screen-wiki §3): 현재 프로젝트의 위키를 카드로 보고(페이지 수·끊긴 링크·규칙·최근 변경), 새 위키를 만들거나 zip으로 가져온다.
 * 위키가 1개여도 목록을 건너뛰지 않는다 — 그 카드가 미리 선택되어 Enter 한 번으로 열린다(자동 이동·`?all` 질의 없음).
 * 데이터는 `useWikiApi`, 대화상자는 `wikiDialogs`가 맡고 이 파일은 잇는 얇은 조립이다. 위키 이름·규칙 이름·설명은 서버 데이터다.
 */
import "@agent-console/wiki-view/styles.css";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Link, useNavigate } from "react-router";
import { ChipRow, EmptyState, Icon, PageHeader, StepGuide, useToast, type StepGuideStep } from "@agent-console/ui";
import { AuthorChip } from "@agent-console/wiki-view";
import { ToneChip } from "@agent-console/markdown-doc";
import type { WikiSummary } from "@agent-console/contracts/wiki";
import { useNow } from "../../app/useNow";
import { usePageTitle } from "../../shell/titles";
import { ROUTE_ROLES, routePath } from "../library";
import { ProjectChip } from "../projects";
import { GuardedButton, MenuButton } from "../../app/menuParts";
import { FailureBlock, ListSkeleton, DebouncedInput } from "./parts";
import { useDeleteWikiDialog, useExportDialog, useImportDialog, useNewWikiDialog, useRulesScreenOn } from "./wikiDialogs";
import { useWikiList, useWikiLive, type OwnWrites } from "./useWikiApi";
import { useWikiContext } from "./useWikiContext";
import { buildWikiDisplay } from "./wikiConfig";
import { wikiPath, wikiRulesPath } from "./wikiPaths";
import "./wiki.css";
import { useT } from "@agent-console/i18n";
import { useMaybeT } from "../../i18n/useMaybeT";
import { useUiLibMessages } from "../../i18n/useViewLibMessages";
import { useWikiViewMessages } from "./useViewMessages";
import { useLanguageCode } from "../../i18n";
import { useFormat } from "../../i18n";

const wikiName = (w: WikiSummary): string => (w.name !== undefined && w.name !== "" ? w.name : w.id);

/** 목록 거르기(순수): 이름·설명·id 부분 일치, 이름 오름차순(화면 언어, 숫자 정렬). */
export function filterWikis(wikis: readonly WikiSummary[], q: string, language: string): WikiSummary[] {
  const collator = new Intl.Collator(language, { numeric: true });
  const needle = q.trim().toLowerCase();
  return wikis
    .filter((w) => needle === "" || `${wikiName(w)} ${w.description ?? ""} ${w.id}`.toLowerCase().includes(needle))
    .sort((a, b) => collator.compare(wikiName(a), wikiName(b)));
}

function renderLink({ to, className, children, dataAttrs }: { to: string; className: string; children: React.ReactNode; dataAttrs: Record<string, string> }) {
  return <Link to={to} className={className} {...dataAttrs}>{children}</Link>;
}

export function WikiListScreen() {
  const fmt = useFormat();
  const language = useLanguageCode();
  const wikiViewMessages = useWikiViewMessages();
  const t = useT("wiki");
  const uiMessages = useUiLibMessages();
  usePageTitle(t("title"));
  const navigate = useNavigate();
  const toast = useToast();
  const ctx = useWikiContext();
  const list = useWikiList();
  const ownWrites = useRef<OwnWrites>(new Map());
  useWikiLive(ownWrites);
  const now = useNow(true, 60_000);
  const tm = useMaybeT("wiki");
  const display = useMemo(() => buildWikiDisplay(tm), [tm]);
  const rulesScreen = useRulesScreenOn();
  const [q, setQ] = useState("");
  const importer = useImportDialog();
  const exporter = useExportDialog();
  const remover = useDeleteWikiDialog();
  const newWiki = useNewWikiDialog((id) => void navigate(wikiPath(id)), ctx.capabilities.import_export ? () => importer.open() : undefined);
  const wikis = useMemo(() => list.data ?? [], [list.data]);
  const shown = useMemo(() => filterWikis(wikis, q, language), [wikis, q, language]);
  const failed = list.isError ? list.error : null;
  const writeBlock = ctx.readOnly ? ctx.readOnlyReason : undefined;
  const open = (w: WikiSummary) => void navigate(wikiPath(w.id));
  const preselected = shown.length === 1 && q.trim() === "" ? shown[0]?.id : undefined;
  const refs = useRef(new Map<string, HTMLElement>());
  // 목록에 들어오면 미리 선택된 카드(없으면 첫 카드)에 포커스를 둔다. 한 번만 — 거르기·새로 읽기로 포커스를 빼앗지 않는다.
  const focusTarget = preselected ?? shown[0]?.id;
  const focused = useRef<string | null>(null);
  useEffect(() => {
    if (focusTarget === undefined || focused.current !== null) return;
    focused.current = focusTarget;
    refs.current.get(focusTarget)?.focus();
  }, [focusTarget]);

  const cardKeys = (e: KeyboardEvent<HTMLElement>, w: WikiSummary, index: number) => {
    if (e.nativeEvent.isComposing) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      open(w);
    } else if (e.key === "ArrowRight" || e.key === "ArrowDown" || e.key === "ArrowLeft" || e.key === "ArrowUp") {
      const delta = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : -1;
      const next = shown[index + delta];
      if (next !== undefined) {
        e.preventDefault();
        refs.current.get(next.id)?.focus();
      }
    }
  };

  const menuFor = (w: WikiSummary) => (
    <MenuButton
      label={<><span aria-hidden="true">⋯</span><span className="ac-sr-only">{t("list.rowMenu", { name: wikiName(w) })}</span></>}
      panelLabel={t("list.actions")}
      items={[
        { id: "open", label: t("list.open"), onSelect: () => open(w) },
        ...(rulesScreen ? [{ id: "rules", label: t("list.rules"), onSelect: () => void navigate(wikiPath(w.id, { tab: "rules" })) }] : []),
        { id: "copy", label: t("list.copyPath"), disabled: (w.directory ?? "") === "", onSelect: () => { void navigator.clipboard?.writeText(w.directory ?? ""); toast({ tone: "success", text: t("copied") }); } },
        ...(ctx.capabilities.import_export ? [{ id: "export", label: t("list.export"), onSelect: () => exporter.open(w) }] : []),
        { id: "delete", label: t("list.delete"), danger: true, disabled: writeBlock !== undefined, onSelect: () => remover.open(w) },
      ]}
    />
  );

  const steps: StepGuideStep[] = [
    ...(rulesScreen ? [{ id: "rules", label: t("list.steps.rules"), done: false, ...(wikiRulesPath() === undefined ? {} : { to: wikiRulesPath() as string }) }] : []),
    ...(rulesScreen ? [{ id: "copy", label: t("list.steps.copy"), done: false, onAction: newWiki.open }] : []),
    { id: "create", label: t("list.steps.create"), done: false, onAction: newWiki.open },
    ...(routePath(ROUTE_ROLES.graph) === "/" ? [] : [{ id: "attach", label: t("list.steps.attach"), done: false, to: routePath(ROUTE_ROLES.graph) }]),
  ];

  return (
    <div className="app-screen-frame wiki-screen">
      <PageHeader
        title={t("title")}
        actions={
          failed !== null ? undefined : (
            <>
              <ProjectChip />
              {ctx.capabilities.import_export ? <GuardedButton blockedReason={writeBlock} onClick={() => importer.open()}>{t("list.import")}</GuardedButton> : null}
              <GuardedButton variant="primary" blockedReason={writeBlock} onClick={newWiki.open}>{t("list.new")}</GuardedButton>
            </>
          )
        }
      />
      {ctx.readOnly && failed === null ? (
        <div className="wiki-banner-row">
          <div className="wiki-readonly-note" role="status" data-testid="wiki-readonly"><strong>{t("readonly.title")}</strong> <span>{t("readonly.body")}</span></div>
        </div>
      ) : null}
      <div className="wiki-screen-body">
        {failed !== null ? (
          <FailureBlock error={failed} title={t("list.loadFailed")} onRetry={() => void list.refetch()} />
        ) : list.isPending ? (
          <ListSkeleton rows={3} />
        ) : wikis.length === 0 ? (
          <div className="wiki-state" data-testid="wiki-empty">
            <EmptyState
              icon={<Icon name="wiki" size={40} />}
              title={t("list.emptyTitle")}
              description={t("list.emptyBody")}
              {...(ctx.capabilities.import_export ? { secondaryAction: <button type="button" className="app-link-btn" onClick={() => importer.open()}>{t("list.emptyImport")}</button> } : {})}
            />
            <StepGuide steps={steps} messages={{ stepsLabel: t("list.stepsLabel"), go: t("list.open"), done: t("on") }} renderLink={renderLink} layout="column" />
          </div>
        ) : (
          <>
            <div className="wiki-toolbar" role="group" aria-label={t("list.search")}>
              <DebouncedInput value={q} onCommit={setQ} label={t("list.search")} className="wiki-search" />
              <span className="wiki-spacer" />
              <span className="app-muted" role="status">{t("list.count", { count: shown.length })}</span>
            </div>
            {shown.length === 0 ? (
              <div className="wiki-state">
                <p role="status">{t("list.noResult", { q: q.trim() })}</p>
                <button type="button" className="app-link-btn" onClick={() => setQ("")}>{t("list.clearSearch")}</button>
              </div>
            ) : (
              <ul className="wiki-cards" aria-label={t("title")} data-testid="wiki-cards">
                {shown.map((w, i) => {
                  const rules = w.rules ?? [];
                  const broken = w.broken_links ?? 0;
                  return (
                    <li key={w.id} className="wiki-card-wrap">
                      <div
                        ref={(el) => {
                          if (el === null) refs.current.delete(w.id);
                          else refs.current.set(w.id, el);
                        }}
                        role="button"
                        tabIndex={i === 0 || w.id === preselected ? 0 : -1}
                        className="wiki-card"
                        data-preselected={w.id === preselected || undefined}
                        onClick={() => open(w)}
                        onKeyDown={(e) => cardKeys(e, w, i)}
                      >
                        <span className="wiki-card-name ac-ellipsis" title={wikiName(w)}>{wikiName(w)}</span>
                        <span className="wiki-card-desc app-muted">{w.description !== undefined && w.description !== "" ? w.description : t("list.descNone")}</span>
                        <span className="wiki-card-stats">
                          <span>{t("list.pages", { n: w.pages ?? 0 })}</span>
                          {broken > 0 ? <ToneChip label={t("list.broken", { n: broken })} tone="warning" /> : null}
                        </span>
                        <span className="wiki-card-meta">
                          {rules.length === 0 ? <span className="app-muted">{t("list.rulesNone")}</span> : <ChipRow messages={uiMessages} chips={rules.map((r) => ({ id: r.id, label: r.name !== undefined && r.name !== "" ? r.name : r.id }))} ariaLabel={t("header.rules")} />}
                          {w.updated_at === undefined || w.updated_at === null ? null : (
                            <span className="app-muted">{t("list.updated", { time: fmt.relative(w.updated_at, now) })}</span>
                          )}
                          {w.updated_by === undefined || w.updated_by === null ? null : <AuthorChip messages={wikiViewMessages} author={w.updated_by} display={display} size="dense" />}
                        </span>
                      </div>
                      <div className="wiki-card-menu">{menuFor(w)}</div>
                    </li>
                  );
                })}
              </ul>
            )}
          </>
        )}
      </div>
      {newWiki.dialog}
      {importer.dialog}
      {exporter.dialog}
      {remover.dialog}
    </div>
  );
}
