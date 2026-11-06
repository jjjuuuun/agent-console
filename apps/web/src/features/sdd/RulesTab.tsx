/**
 * 규칙 탭(screen-sdd §10): 스펙 정의(이름·설명·문서 목록·규칙)를 계약 JSON Schema(`x-ui`)로 그린다. 섹션 목록·제목·순서·필드는 스키마에서 나오고
 * 코드에 이름이 없다(`ruleSections`). 검사(`규칙 검사`)·저장(`If-Match`)·충돌·읽기 전용·틀로 저장을 다룬다. 저장은 검사 오류가 있어도 막지 않는다.
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { ApiError } from "@agent-console/api-client";
import { ERROR_CODES, getContractSchema } from "@agent-console/contracts";
import { SchemaForm, type FormError } from "@agent-console/schema-form";
import { Banner, Button, ConfirmDialog, Disclosure, useToast } from "@agent-console/ui";
import { RulesSourceBadge } from "@agent-console/sdd-view";
import type { SpecDefinition, SpecIssue } from "@agent-console/contracts/sdd";
import type { SchemaNode } from "../../lib/schemaTools";
import { AutomationBar } from "./AutomationBar";
import { ListSkeleton } from "./parts";
import { AUTOMATION_FIELDS, AUTOMATION_OPS, SDD_PARAMS } from "./sddConfig";
import { sddMessages as m, viewMessages } from "./messages";
import { issueInSection, mergeSection, ruleSections, sectionValue, type RuleSection } from "./ruleSections";
import { SaveTemplateDialog } from "./SaveTemplateDialog";
import type { SddTabProps } from "./sddTabs";
import { useAutomationControl } from "./useAutomation";
import { useSddSpace, useSpecSyntax } from "./useSddApi";
import { specTemplatesPath } from "./sddPaths";

const P = SDD_PARAMS;
type Obj = Record<string, unknown>;
const numText = (v: unknown): string | undefined => (typeof v === "number" ? String(v) : undefined);

const errorsFor = (issues: readonly SpecIssue[], section: RuleSection): FormError[] => {
  const key = section.path[section.path.length - 1] as string;
  return issues
    .filter((i) => issueInSection(i.path, section))
    .map((i) => ({ path: `/${key}${(i.path as string).slice(section.pointer.length)}`, message: i.message, severity: i.severity === "error" ? ("error" as const) : ("warning" as const) }));
};

export function RulesTab({ specId, view, versionHash, ctx, params, setParams, ownHashes, refresh, reportDirty }: SddTabProps) {
  const space = useSddSpace();
  const toast = useToast();
  const navigate = useNavigate();
  const syntax = useSpecSyntax(specId);
  const schema = useMemo(() => getContractSchema("SpecDefinition") as SchemaNode, []);
  const sections = useMemo(() => ruleSections(schema), [schema]);
  const base = view.spec as unknown as Obj;
  const [draft, setDraft] = useState<{ value: Obj; baseHash: string } | null>(null);
  const [checked, setChecked] = useState<readonly SpecIssue[] | null>(null);
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [saveTemplate, setSaveTemplate] = useState(false);
  const [confirmAuto, setConfirmAuto] = useState<string | null>(null);
  const automation = useAutomationControl(specId);

  const value = draft?.value ?? base;
  const dirty = draft !== null && JSON.stringify(draft.value) !== JSON.stringify(base);
  useEffect(() => {
    reportDirty("rules", dirty);
    return () => reportDirty("rules", false);
  }, [dirty, reportDirty]);
  const externalChange = dirty && draft.baseHash !== versionHash;
  const showConflict = conflict || externalChange;
  const issues = checked ?? view.issues ?? [];
  const errors = issues.filter((i) => i.severity === "error").length;
  const warnings = issues.length - errors;
  const wanted = params.get(P.section);
  const section = sections.find((s) => s.id === wanted) ?? sections[0];
  const readonly = ctx.readOnly;

  const select = (id: string) => {
    const next = new URLSearchParams(params);
    next.set(P.section, id);
    setParams(next, { replace: true });
  };
  const edit = (s: RuleSection, next: unknown) => {
    const merged = mergeSection(value, s, next);
    setDraft({ value: merged, baseHash: draft?.baseHash ?? versionHash });
  };

  const check = async () => {
    setChecking(true);
    try {
      const def = value as unknown as SpecDefinition;
      const result = await space.client.checkSpec(specId, { rules: (def.rules ?? {}) as Obj, documents: def.documents ?? [] });
      setChecked(result.issues ?? []);
    } catch (e) {
      setFailure(e instanceof ApiError && e.message !== "" ? e.message : m.rules.saveFailed);
    } finally {
      setChecking(false);
    }
  };
  const save = async (expected: string) => {
    if (draft === null || readonly) return;
    setSaving(true);
    setFailure(null);
    try {
      const saved = await space.client.putSpec(specId, draft.value as unknown as SpecDefinition, expected);
      if (saved.version_hash !== undefined) ownHashes.current.add(saved.version_hash);
      setDraft(null);
      setConflict(false);
      setChecked(null);
      await refresh();
    } catch (e) {
      if (e instanceof ApiError && e.code === ERROR_CODES.VERSION_CONFLICT) setConflict(true);
      else setFailure(e instanceof ApiError && e.message !== "" ? e.message : m.rules.saveFailed);
    } finally {
      setSaving(false);
    }
  };
  /** 자동 진행을 새로 켜는 저장이면 먼저 확인을 받는다(비용이 사람 없이 시작될 수 있다) */
  const autoOf = (def: Obj | undefined): Obj | undefined => ((def?.["rules"] as Obj | undefined)?.[AUTOMATION_FIELDS.key] as Obj | undefined);
  const requestSave = (expected: string) => {
    if (draft === null || readonly) return;
    const enabling = autoOf(draft.value)?.[AUTOMATION_FIELDS.enabled] === true && autoOf(base)?.[AUTOMATION_FIELDS.enabled] !== true;
    if (enabling) setConfirmAuto(expected);
    else void save(expected);
  };
  const overwrite = async () => {
    const fresh = await space.client.getSpec(specId);
    await save(fresh.version_hash ?? versionHash);
  };

  if (section === undefined) return <ListSkeleton rows={6} />;
  const isAutomation = section.path.includes(AUTOMATION_FIELDS.key);
  const autoValue = autoOf(value);
  const sectionIssueCount = (s: RuleSection) => issues.filter((i) => issueInSection(i.path, s)).length;
  const templatesOn = ctx.capabilities.templates && specTemplatesPath() !== undefined;

  return (
    <div className="sdd-rules">
      <div className="sdd-toolbar" role="group" aria-label={m.rules.toolbar}>
        <Button size="sm" loading={checking} onClick={() => void check()}>{checking ? m.rules.checking : m.rules.check}</Button>
        {issues.length === 0 && checked !== null ? <span className="app-muted" role="status">{m.rules.checkOk}</span> : issues.length > 0 ? <span role="status" data-testid="sdd-check-summary">{m.rules.checkResult(errors, warnings)}</span> : null}
        {templatesOn ? <Button size="sm" onClick={() => setSaveTemplate(true)}>{m.rules.saveAsTemplate}</Button> : null}
        <span className="sdd-spacer" />
        <span className="app-muted" role="status">{saving ? m.rules.saving : dirty ? m.rules.unsaved : m.rules.saved}</span>
        <Button size="sm" variant="primary" loading={saving} aria-disabled={!dirty || readonly || showConflict || undefined} title={readonly ? ctx.readOnlyReason : undefined} onClick={() => { if (dirty && !readonly && !showConflict) requestSave(draft?.baseHash ?? versionHash); }}>{m.rules.save}</Button>
      </div>
      {readonly ? <Banner tone="warning" data-testid="sdd-rules-readonly">{m.rules.readonlyTop}</Banner> : null}
      {failure === null ? null : <Banner tone="danger">{failure}</Banner>}
      {showConflict ? (
        <Banner tone="warning" title={m.rules.conflictTitle} actions={<><Button size="sm" onClick={() => { setDraft(null); setConflict(false); void refresh(); }}>{m.rules.reload}</Button><Button size="sm" disabled={readonly} onClick={() => void overwrite()}>{m.rules.overwrite}</Button></>}>
          {m.rules.conflictBody}
        </Banner>
      ) : null}
      {view.automation_state?.enabled === true && ctx.capabilities.automation ? (
        <AutomationBar
          state={view.automation_state}
          busy={automation.busy}
          blockedReason={readonly ? ctx.readOnlyReason : undefined}
          onStop={() => void automation.control(AUTOMATION_OPS.stop)}
          onResume={() => void automation.control(AUTOMATION_OPS.resume)}
        />
      ) : null}
      {automation.error === null ? null : <Banner tone="danger">{automation.error}</Banner>}
      {issues.length > 0 ? (
        <Disclosure summary={m.rules.checkResult(errors, warnings)}>
          <ul className="sdd-issues-list">
            {issues.map((i, idx) => <li key={`${i.code}:${i.path ?? ""}:${idx}`} data-tone={i.severity === "error" ? "danger" : "warning"}>{i.message}</li>)}
          </ul>
        </Disclosure>
      ) : null}
      <div className="sdd-rules-body">
        <nav className="sdd-rules-nav" aria-label={m.rules.sections}>
          <ul>
            {sections.map((s) => {
              const n = sectionIssueCount(s);
              return (
                <li key={s.id}>
                  <button type="button" aria-current={s.id === section.id ? "true" : undefined} onClick={() => select(s.id)}>
                    <span className="ac-ellipsis">{s.title}</span>
                    {n > 0 ? <span className="sdd-dot" data-tone="danger" aria-label={`${n}`}>{n}</span> : null}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="sdd-rules-form">
          <h3 className="sdd-section-title">{section.title}</h3>
          {isAutomation && !ctx.capabilities.runs ? <p className="app-muted sdd-note" data-testid="sdd-automation-off">{m.automation.runsOff}</p> : null}
          <SchemaForm
            key={section.id}
            schema={section.schema}
            value={sectionValue(value, section)}
            onChange={(next) => edit(section, next)}
            errors={errorsFor(issues, section)}
            readonly={readonly || (isAutomation && !ctx.capabilities.runs)}
            idPrefix={`sdd-rules-${section.id.replace(/[^A-Za-z0-9_-]/g, "-")}`}
            rawJsonToggle={false}
          />
          {syntax.data === undefined || Object.keys(syntax.data.sources ?? {}).length === 0 ? null : (
            <Disclosure summary={m.rules.syntaxSource}>
              <ul className="sdd-sources">
                {Object.entries(syntax.data.sources ?? {}).map(([key, source]) => (
                  <li key={key}><span className="sdd-mono">{key}</span> <RulesSourceBadge source={source} messages={viewMessages} /></li>
                ))}
              </ul>
            </Disclosure>
          )}
        </div>
      </div>
      <ConfirmDialog
        open={confirmAuto !== null}
        title={m.automation.confirmTitle}
        confirmLabel={m.automation.confirmOk}
        cancelLabel={m.cancel}
        onConfirm={() => { const expected = confirmAuto; setConfirmAuto(null); if (expected !== null) void save(expected); }}
        onCancel={() => setConfirmAuto(null)}
      >
        {m.automation.confirmBody(numText(autoValue?.[AUTOMATION_FIELDS.maxParallel]), numText(autoValue?.[AUTOMATION_FIELDS.maxFailures]))}
      </ConfirmDialog>
      {saveTemplate ? (
        <SaveTemplateDialog
          open
          onClose={() => setSaveTemplate(false)}
          initialName={view.spec.name}
          onSubmit={async (body) => {
            await space.client.saveSpecAsTemplate(specId, body);
            setSaveTemplate(false);
            const href = specTemplatesPath();
            toast({ tone: "success", text: m.saveTemplate.done(body.name), ...(href === undefined ? {} : { action: { label: m.templatesTitle, onClick: () => void navigate(href) } }) });
          }}
        />
      ) : null}
    </div>
  );
}
