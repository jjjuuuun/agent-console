/**
 * 규칙 탭(screen-sdd §10): 스펙 정의(이름·설명·문서 목록·규칙)를 계약 JSON Schema(`x-ui`)로 그린다. 섹션 목록·제목·순서·필드는 스키마에서 나오고
 * 코드에 이름이 없다(`ruleSections`). 검사(`규칙 검사`)·저장(`If-Match`)·충돌·읽기 전용·틀로 저장을 다룬다. 저장은 검사 오류가 있어도 막지 않는다.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { ApiError } from "@agent-console/api-client";
import { ERROR_CODES, getContractSchema } from "@agent-console/contracts";
import { Banner, Button, ConfirmDialog, Disclosure, useToast } from "@agent-console/ui";
import { RulesSourceBadge } from "@agent-console/sdd-view";
import type { SpecDefinition, SpecIssue } from "@agent-console/contracts/sdd";
import type { SchemaNode } from "../../lib/schemaTools";
import { AutomationBar } from "./AutomationBar";
import { ListSkeleton } from "./parts";
import { AUTOMATION_FIELDS, AUTOMATION_OPS, SDD_LIMITS, SDD_PARAMS } from "./sddConfig";
import { RuleSectionsForm } from "./RuleSectionsForm";
import { useSddWidgetData } from "./widgets/SddWidgetEnv";
import { sddMessages as m, viewMessages } from "./messages";
import { ruleSections } from "./ruleSections";
import { SaveTemplateDialog } from "./SaveTemplateDialog";
import type { SddTabProps } from "./sddTabs";
import { useAutomationControl } from "./useAutomation";
import { useSddSpace, useSpecSyntax } from "./useSddApi";
import { specTemplatesPath } from "./sddPaths";

const P = SDD_PARAMS;
type Obj = Record<string, unknown>;
const numText = (v: unknown): string | undefined => (typeof v === "number" ? String(v) : undefined);

const autoOf = (def: Obj | undefined): Obj | undefined => ((def?.["rules"] as Obj | undefined)?.[AUTOMATION_FIELDS.key] as Obj | undefined);

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
  /** 자동 진행을 켜는 변경은 확인을 받을 때까지 초안에 넣지 않고 여기에 둔다(취소하면 버린다) */
  const [pendingAuto, setPendingAuto] = useState<Obj | null>(null);
  /** 취소로 버린 변경이 폼 입력에 남아 보이지 않도록 폼을 다시 만드는 번호 */
  const [formEpoch, setFormEpoch] = useState(0);
  const checkSeq = useRef(0);
  const automation = useAutomationControl(specId);

  const value = draft?.value ?? base;
  const valueRef = useRef(value);
  useEffect(() => {
    valueRef.current = value;
  });
  const widgetEnv = useSddWidgetData(specId, value as unknown as SpecDefinition, ctx.capabilities.runs);
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
  const edit = (merged: Obj) => {
    // 자동 진행을 새로 켜는 변경은 확인 대화상자를 거친다(screen-sdd §10.2). 취소하면 값은 그대로다.
    if (autoOf(merged)?.[AUTOMATION_FIELDS.enabled] === true && autoOf(value)?.[AUTOMATION_FIELDS.enabled] !== true) {
      setPendingAuto(merged);
      return;
    }
    setDraft({ value: merged, baseHash: draft?.baseHash ?? versionHash });
  };

  /** 규칙 검사. `silent`(편집 뒤 자동 검사)는 실패해도 알리지 않고 로딩 표시도 하지 않는다. 늦게 온 옛 응답은 버린다 */
  const check = useCallback(
    async (silent: boolean) => {
      const seq = ++checkSeq.current;
      if (!silent) setChecking(true);
      try {
        const def = valueRef.current as unknown as SpecDefinition;
        const result = await space.client.checkSpec(specId, { rules: (def.rules ?? {}) as Obj, documents: def.documents ?? [] });
        if (seq === checkSeq.current) setChecked(result.issues ?? []);
      } catch (e) {
        if (!silent && seq === checkSeq.current) setFailure(e instanceof ApiError && e.message !== "" ? e.message : m.rules.saveFailed);
      } finally {
        if (!silent && seq === checkSeq.current) setChecking(false);
      }
    },
    [space.client, specId],
  );
  // 편집이 멈추고 600ms 뒤 자동 검사: 연속 입력은 한 번만 검사한다.
  useEffect(() => {
    if (!dirty || readonly) return;
    const timer = setTimeout(() => void check(true), SDD_LIMITS.checkDebounceMs);
    return () => clearTimeout(timer);
  }, [draft?.value, dirty, readonly, check]);
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
  const overwrite = async () => {
    const fresh = await space.client.getSpec(specId);
    await save(fresh.version_hash ?? versionHash);
  };

  if (section === undefined) return <ListSkeleton rows={6} />;
  const automationOff = (s: { path: readonly string[] }) => s.path.includes(AUTOMATION_FIELDS.key) && !ctx.capabilities.runs;
  const templatesOn = ctx.capabilities.templates && specTemplatesPath() !== undefined;

  return (
    <div className="sdd-rules">
      <div className="sdd-toolbar" role="group" aria-label={m.rules.toolbar}>
        <Button size="sm" loading={checking} onClick={() => void check(false)}>{checking ? m.rules.checking : m.rules.check}</Button>
        {issues.length === 0 && checked !== null ? <span className="app-muted" role="status">{m.rules.checkOk}</span> : issues.length > 0 ? <span role="status" data-testid="sdd-check-summary">{m.rules.checkResult(errors, warnings)}</span> : null}
        {templatesOn ? <Button size="sm" onClick={() => setSaveTemplate(true)}>{m.rules.saveAsTemplate}</Button> : null}
        <span className="sdd-spacer" />
        <span className="app-muted" role="status">{saving ? m.rules.saving : dirty ? m.rules.unsaved : m.rules.saved}</span>
        <Button size="sm" variant="primary" loading={saving} aria-disabled={!dirty || readonly || showConflict || undefined} title={readonly ? ctx.readOnlyReason : undefined} onClick={() => { if (dirty && !readonly && !showConflict) void save(draft?.baseHash ?? versionHash); }}>{m.rules.save}</Button>
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
      <RuleSectionsForm
        schema={schema}
        value={value}
        onChange={edit}
        issues={issues}
        readonly={readonly}
        sectionId={wanted}
        onSectionChange={select}
        navLabel={m.rules.sections}
        idPrefix="sdd-rules"
        widgetEnv={widgetEnv}
        formEpoch={formEpoch}
        readonlyFor={automationOff}
        sectionNote={(s) => (automationOff(s) ? <p className="app-muted sdd-note" data-testid="sdd-automation-off">{m.automation.runsOff}</p> : null)}
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
      <ConfirmDialog
        open={pendingAuto !== null}
        title={m.automation.confirmTitle}
        confirmLabel={m.automation.confirmOk}
        cancelLabel={m.cancel}
        onConfirm={() => { const next = pendingAuto; setPendingAuto(null); if (next !== null) setDraft({ value: next, baseHash: draft?.baseHash ?? versionHash }); }}
        onCancel={() => { setPendingAuto(null); setFormEpoch((n) => n + 1); }}
      >
        {m.automation.confirmBody(numText(autoOf(pendingAuto ?? undefined)?.[AUTOMATION_FIELDS.maxParallel]), numText(autoOf(pendingAuto ?? undefined)?.[AUTOMATION_FIELDS.maxFailures]))}
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
