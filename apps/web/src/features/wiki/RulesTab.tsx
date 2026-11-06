/**
 * 규칙 탭(screen-wiki §9): 이 위키의 정보·쓰는 규칙을 계약 스키마 폼으로 고쳐 저장(`PUT … + If-Match`)하고, 합친 지침·합친 규칙·유효 문법을 읽기 전용으로 보인다.
 * 폼 섹션·필드·위젯은 `WikiDefinition` JSON Schema(`x-ui`)가 정한다 — 규칙 목록 편집기는 스키마가 단 위젯 `wiki-rule-refs`로 꽂힌다(앱 uiSchema로 필드를 숨기지 않는다).
 * 규칙 id·이름·쓰기 규칙 동작·문법 값·출처는 서버 데이터이고, 읽기 전용 표의 톤·라벨은 규칙 스키마의 `x-ui.enum_tones`·`enum_labels`에서 온다.
 */
import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router";
import { ApiError } from "@agent-console/api-client";
import { ERROR_CODES, getContractSchema } from "@agent-console/contracts";
import { KNOWN_UI_WIDGETS, KNOWN_WIKI_RULE_ENTRY_KINDS, KNOWN_WIKI_SYNTAX_SOURCES } from "@agent-console/contracts/constants";
import { SchemaForm } from "@agent-console/schema-form";
import { Banner, Button, useToast } from "@agent-console/ui";
import { SyntaxValueTree, type RuleSummary } from "@agent-console/wiki-view";
import { ToneChip } from "@agent-console/markdown-doc";
import type { WikiDefinition, WikiRuleEntry } from "@agent-console/contracts/wiki";
import type { SchemaNode } from "../../lib/schemaTools";
import { widgetUiSchema } from "../sdd";
import { ROUTE_ROLES, routePath } from "../library";
import { useCopyDialog } from "../projects";
import { MenuButton } from "../../app/menuParts";
import { FailureBlock, ListSkeleton } from "./parts";
import { RuleRefsField, RuleRefsProvider, type RuleRefsEnv } from "./RuleRefsField";
import { RULES_SECTION_KEYS, sectionDomId, type RulesSectionKey } from "./rulesSections";
import { collectEnumUi, propertyTitles } from "./rulesSchema";
import { useInvalidateWiki, useWikiRulesList, useWikiSpace, useWikiSyntax } from "./useWikiApi";
import { useRulesScreenOn, useLibraryRulesKind } from "./wikiDialogs";
import { severityTone, WIKI_PARAMS } from "./wikiConfig";
import { wikiRulesPath } from "./wikiPaths";
import type { WikiTabProps } from "./wikiTabs";
import { wikiTabMessages } from "./tabMessages";

type Obj = Record<string, unknown>;
const t = wikiTabMessages.rules;
const RULE_REFS = KNOWN_UI_WIDGETS.WIKI_RULE_REFS;
const FIELDS = { [RULE_REFS]: RuleRefsField } as const;

const isConflict = (e: unknown): boolean => e instanceof ApiError && (e.code === ERROR_CODES.VERSION_CONFLICT || e.status === 412);

export function RulesTab({ wikiId, view, versionHash, summary, ctx, params, setParams, refresh, reportDirty }: WikiTabProps) {
  const navigate = useNavigate();
  const toast = useToast();
  const space = useWikiSpace();
  const invalidate = useInvalidateWiki();
  const copy = useCopyDialog();
  const rulesQ = useWikiRulesList(true);
  const syntaxQ = useWikiSyntax(wikiId);
  const rulesScreen = useRulesScreenOn();
  const library = useLibraryRulesKind(rulesScreen && ctx.capabilities.rules_library && ctx.projectId !== null);

  const schema = useMemo(() => getContractSchema("WikiDefinition") as SchemaNode, []);
  const ui = useMemo(() => widgetUiSchema(schema, new Set(Object.keys(FIELDS))), [schema]);
  const ruleSchema = useMemo(() => getContractSchema("WikiRulesDefinition"), []);
  const enumUi = useMemo(() => collectEnumUi(ruleSchema), [ruleSchema]);
  const syntaxTitles = useMemo(() => propertyTitles(getContractSchema("WikiSyntax")), []);

  const server = view.wiki as unknown as Obj;
  const [draft, setDraft] = useState<Obj | null>(null);
  const [baseHash, setBaseHash] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [epoch, setEpoch] = useState(0);

  const dirty = draft !== null && JSON.stringify(draft) !== JSON.stringify(server);
  const stale = dirty && baseHash !== null && baseHash !== versionHash;
  const showConflict = conflict || stale;
  const writeBlock = ctx.readOnly ? ctx.readOnlyReason : undefined;
  const readonly = writeBlock !== undefined;
  const value = draft ?? server;

  // 저장 안 한 변경 알림(화면 이동 막기)
  useEffect(() => {
    reportDirty("rules", dirty);
    return () => reportDirty("rules", false);
  }, [dirty, reportDirty]);
  const edit = (next: Obj) => {
    setBaseHash((h) => h ?? versionHash);
    setDraft(next);
  };
  const discard = () => {
    setDraft(null);
    setBaseHash(null);
    setConflict(false);
    setFailure(null);
    setEpoch((n) => n + 1);
  };

  const save = async (expected: string) => {
    if (readonly || !dirty || draft === null) return;
    setSaving(true);
    setFailure(null);
    try {
      await space.client.putWiki(wikiId, draft as unknown as WikiDefinition, expected);
      setDraft(null);
      setBaseHash(null);
      setConflict(false);
      await invalidate();
    } catch (e) {
      if (isConflict(e)) setConflict(true);
      else setFailure(e instanceof Error && e.message !== "" ? e.message : t.saveFailed);
    } finally {
      setSaving(false);
    }
  };
  const overwrite = async () => {
    const fresh = await space.client.getWiki(wikiId);
    await save(fresh.version_hash ?? fresh.value.version_hash);
  };

  const list = rulesQ.data;
  const all = useMemo<RuleSummary[]>(() => (list ?? []).map((r) => ({ id: r.id, ...(r.name === undefined ? {} : { name: r.name }), ...(r.counts === undefined ? {} : { counts: r.counts }), ...(r.has_instructions === undefined ? {} : { has_instructions: r.has_instructions }) })), [list]);
  const summaries = useMemo(() => Object.fromEntries(all.map((r) => [r.id, r])), [all]);

  const openRule = rulesScreen ? (id: string) => void navigate(wikiRulesPath(id, ctx.projectId) ?? routePath(ROUTE_ROLES.settings)) : undefined;
  /** 복사 대화상자는 항목 id를 미리 검색하지 않는다(고르기 단계에서 직접 고른다) */
  const importRule = () => {
    const kind = library.kind;
    if (kind === null || ctx.projectId === null) return;
    copy.open({
      direction: "import",
      project: ctx.projectId,
      start: "pick",
      onlyKinds: [kind],
      onApplied: () => void invalidate(),
    });
  };
  const env: RuleRefsEnv = {
    refs: view.rules?.rules ?? summary?.rules ?? [],
    summaries,
    all,
    onOpen: openRule,
    onImport: rulesScreen && ctx.capabilities.rules_library && library.kind !== null && ctx.projectId !== null ? importRule : undefined,
    onRemoved: (restore) => toast({ tone: "info", text: t.removed, durationMs: 5000, action: { label: t.undo, onClick: restore } }),
    readOnlyReason: writeBlock,
  };

  const scrollTo = (key: RulesSectionKey) => {
    const next = new URLSearchParams(params);
    next.set(WIKI_PARAMS.section, key);
    setParams(next, { replace: true });
    document.getElementById(sectionDomId(key))?.scrollIntoView?.({ block: "start" });
  };
  const active = RULES_SECTION_KEYS.find((k) => k === params.get(WIKI_PARAMS.section)) ?? RULES_SECTION_KEYS[0];
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) {
      e.preventDefault();
      if (dirty && !showConflict) void save(baseHash ?? versionHash);
    }
  };

  const issues = view.issues ?? [];
  const errors = issues.filter((i) => i.severity === "error").length;
  const instructions = view.rules?.instructions ?? "";
  const entries = view.rules?.entries ?? [];
  const byKind = (kind: string) => entries.filter((e) => e.kind === kind);
  const openOwner = (ruleId: string) => {
    const to = rulesScreen ? wikiRulesPath(ruleId, ctx.projectId) : undefined;
    if (to !== undefined) void navigate(to);
  };
  const openSource = (source: string) => {
    const prefix = KNOWN_WIKI_SYNTAX_SOURCES.RULES_PREFIX;
    if (source.startsWith(prefix)) openOwner(source.slice(prefix.length));
    else void navigate(routePath(ROUTE_ROLES.settings));
  };

  const actionChip = (e: WikiRuleEntry) => {
    const value = e.kind === KNOWN_WIKI_RULE_ENTRY_KINDS.LINT ? e.severity : e.action;
    if (value === undefined || value === null || value === "") return <span className="app-muted">–</span>;
    const tone = e.kind === KNOWN_WIKI_RULE_ENTRY_KINDS.LINT ? severityTone(value) : (enumUi.tones[value] ?? "neutral");
    return <ToneChip tone={tone} label={enumUi.labels[value] ?? value} />;
  };
  const sourceCell = (ruleId: string) =>
    rulesScreen ? <button type="button" className="app-link-btn wiki-mono" onClick={() => openOwner(ruleId)} aria-label={`${t.openRule}: ${ruleId}`}>{ruleId}</button> : <span className="wiki-mono">{ruleId}</span>;
  const table = (kind: string, withValue: boolean) => {
    const rows = byKind(kind);
    if (rows.length === 0) return null;
    return (
      <section key={kind} aria-label={t.table[kind] ?? kind}>
        <h4 className="wiki-subtitle">{t.table[kind] ?? kind}</h4>
        <table className="wiki-table" aria-label={t.table[kind] ?? kind}>
          <thead>
            <tr>
              <th scope="col">{t.col.id}</th>
              {withValue ? <th scope="col">{kind === KNOWN_WIKI_RULE_ENTRY_KINDS.LINT ? t.col.severity : t.col.action}</th> : null}
              <th scope="col">{kind === KNOWN_WIKI_RULE_ENTRY_KINDS.TEMPLATE ? t.col.name : t.col.message}</th>
              <th scope="col">{t.col.source}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => (
              <tr key={`${e.kind}:${e.rule_id}:${e.id}`}>
                <td className="wiki-mono">{e.id}</td>
                {withValue ? <td>{actionChip(e)}</td> : null}
                <td>{e.label ?? ""}</td>
                <td>{sourceCell(e.rule_id)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    );
  };

  const sectionItems = RULES_SECTION_KEYS.map((k) => ({ id: k, label: t.sections[k], onSelect: () => scrollTo(k) }));
  const syntax = syntaxQ.data;

  return (
    <div className="wiki-rules" data-testid="wiki-rules" onKeyDown={onKeyDown}>
      <nav className="wiki-rules-nav" aria-label={t.sectionsLabel}>
        <ul>
          {RULES_SECTION_KEYS.map((k) => (
            <li key={k}>
              <button type="button" aria-current={k === active ? "true" : undefined} onClick={() => scrollTo(k)}>{t.sections[k]}</button>
            </li>
          ))}
        </ul>
      </nav>
      <div className="wiki-rules-main">
        <div className="wiki-rules-toolbar" role="group" aria-label={t.toolbar}>
          <span className="wiki-rules-menu"><MenuButton label={<>{t.sectionsMenu} <span aria-hidden="true">▾</span></>} panelLabel={t.sectionsLabel} align="start" items={sectionItems} /></span>
          {issues.length === 0 ? null : <span data-testid="wiki-rules-issues"><ToneChip tone={errors > 0 ? "danger" : "warning"} label={t.issuesChip(issues.length)} /></span>}
          <span className="wiki-spacer" />
          <span className="app-muted" role="status">{saving ? t.saving : dirty ? t.dirty : t.saved}</span>
          <Button
            size="sm"
            variant="primary"
            loading={saving}
            aria-disabled={!dirty || readonly || showConflict || undefined}
            title={readonly ? writeBlock : undefined}
            onClick={() => {
              if (dirty && !readonly && !showConflict) void save(baseHash ?? versionHash);
            }}
          >
            {t.save}
          </Button>
        </div>
        {readonly ? <Banner tone="warning" data-testid="wiki-rules-readonly">{writeBlock ?? t.readonlyTop}</Banner> : null}
        {failure === null ? null : <Banner tone="danger">{failure}</Banner>}
        {showConflict ? (
          <Banner
            tone="warning"
            title={t.conflictTitle}
            data-testid="wiki-rules-conflict"
            actions={
              <>
                <Button size="sm" onClick={() => { discard(); void refresh(); }}>{t.reload}</Button>
                <Button size="sm" disabled={readonly} onClick={() => void overwrite()}>{t.overwrite}</Button>
              </>
            }
          >
            {t.conflictBody}
          </Banner>
        ) : null}

        <section id={sectionDomId("info")} aria-label={t.sections.info} className="wiki-rules-section">
          <h3 className="wiki-section-title">{t.sections.info}</h3>
          <RuleRefsProvider env={env}>
            <SchemaForm
              key={epoch}
              schema={schema}
              uiSchema={ui}
              customFields={FIELDS}
              value={value}
              onChange={(next) => edit(next as Obj)}
              readonly={readonly || saving}
              idPrefix="wiki-rules-form"
              rawJsonToggle={false}
              advancedStorageKey="wiki.info"
            />
          </RuleRefsProvider>
          {issues.length === 0 ? null : (
            <ul className="wiki-issue-lines" aria-label={t.issuesChip(issues.length)}>
              {issues.map((i, idx) => <li key={`${i.code}:${idx}`} data-tone={i.severity === "error" ? "danger" : "warning"}>{i.message}</li>)}
            </ul>
          )}
        </section>

        <section id={sectionDomId("instructions")} aria-label={t.sections.instructions} className="wiki-rules-section">
          <h3 className="wiki-section-title">{t.sections.instructions}</h3>
          {ctx.capabilities.runs ? null : <Banner tone="info" data-testid="wiki-rules-runs-off">{t.instructionsRunsOff}</Banner>}
          {instructions === "" ? (
            <p className="app-muted">{t.instructionsNone}</p>
          ) : (
            <>
              <div className="wiki-toolbar">
                <Button size="sm" onClick={() => { void navigator.clipboard?.writeText(instructions); toast({ tone: "success", text: t.instructionsCopied }); }}>{t.instructionsCopy}</Button>
              </div>
              <pre className="ac-pre wiki-instructions" tabIndex={0} aria-label={t.sections.instructions}>{instructions}</pre>
            </>
          )}
          <p className="app-muted wiki-hint">{t.instructionsNote}</p>
        </section>

        <section id={sectionDomId("merged")} aria-label={t.sections.merged} className="wiki-rules-section">
          <h3 className="wiki-section-title">{t.sections.merged}</h3>
          {entries.length === 0 ? <p className="app-muted">{t.mergedNone}</p> : (
            <>
              {table(KNOWN_WIKI_RULE_ENTRY_KINDS.WRITE, true)}
              {table(KNOWN_WIKI_RULE_ENTRY_KINDS.LINT, true)}
              {table(KNOWN_WIKI_RULE_ENTRY_KINDS.TEMPLATE, false)}
            </>
          )}
        </section>

        <section id={sectionDomId("syntax")} aria-label={t.sections.syntax} className="wiki-rules-section">
          <h3 className="wiki-section-title">{t.sections.syntax}</h3>
          {syntaxQ.isPending ? <ListSkeleton rows={3} /> : syntaxQ.isError || syntax === undefined ? (
            <FailureBlock error={syntaxQ.error} title={t.syntaxLoadFailed} onRetry={() => void syntaxQ.refetch()} />
          ) : (
            <>
              <SyntaxValueTree syntax={syntax} titles={syntaxTitles} onOpenSource={openSource} />
              <p className="app-muted wiki-hint">{t.syntaxDefault}</p>
              <Button size="sm" onClick={() => void navigate(routePath(ROUTE_ROLES.settings))}>{t.syntaxOpenSettings}</Button>
            </>
          )}
        </section>
      </div>
      {copy.dialog}
    </div>
  );
}
