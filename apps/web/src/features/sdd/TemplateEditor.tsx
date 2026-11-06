/**
 * 문서 틀 편집기(screen-sdd §11.1): 도구줄([검사]·저장·메뉴) + 탭 3개(규칙 = 스키마 폼, 뼈대 파일 = 파일 트리·편집기, 버전 = 공통 버전 기록).
 * 규칙과 뼈대 파일은 하나의 정의 버전(`ETag`)을 나눠 쓰므로 [저장] 한 번에 규칙 → 파일 쓰기 → 파일 지우기 순으로 이어서 쓰고 응답 `ETag`를 다음 요청 `If-Match`로 넘긴다.
 * 충돌(412)·읽기 전용·저장 안 한 변경 알림은 여기서 다루고, 이동 막기는 부모 화면이 한다. 틀 이름·문서 이름·서버 메시지는 데이터다.
 */
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, definitionBase } from "@agent-console/api-client";
import { ERROR_CODES, getContractSchema } from "@agent-console/contracts";
import { Banner, Button, ConfirmDialog, Disclosure, Tabs, type TabItem } from "@agent-console/ui";
import type { Issue } from "@agent-console/contracts";
import type { SpecIssue, SpecTemplate } from "@agent-console/contracts/sdd";
import { ErrorBlock } from "../../app/ErrorBlock";
import type { SchemaNode } from "../../lib/schemaTools";
import { planFileChanges, type FileEntry } from "../resources";
import { VersionHistory } from "../versions";
import { FailureBlock, ListSkeleton, MenuButton } from "./parts";
import { RuleSectionsForm } from "./RuleSectionsForm";
import { classifySddError } from "./sddErrors";
import { TEMPLATE_PARAMS, TEMPLATE_TABS, TEMPLATES_COLLECTION, type TemplateTabId } from "./templateConfig";
import { TemplateFilesPanel } from "./TemplateFilesPanel";
import { templateMessages as t } from "./templateMessages";
import { useSpecTemplate, useTemplateFiles, type TemplateSpace } from "./useTemplateApi";
import { useInvalidateSdd } from "./useSddApi";
import { sddMessages as m } from "./messages";

type Obj = Record<string, unknown>;
const P = TEMPLATE_PARAMS;

export interface TemplateEditorProps {
  space: TemplateSpace;
  id: string;
  params: URLSearchParams;
  setParams: (next: URLSearchParams, options?: { replace?: boolean }) => void;
  /** 저장 안 한 변경이 생기거나 없어질 때 */
  onDirtyChange: (dirty: boolean) => void;
  /** 틀을 지운 뒤(목록을 새로 읽고 선택을 풀어야 한다) */
  onDeleted: (name: string) => void;
}

const isConflict = (e: unknown): boolean => e instanceof ApiError && (e.code === ERROR_CODES.VERSION_CONFLICT || e.status === 412);

export function TemplateEditor({ space, id, params, setParams, onDirtyChange, onDeleted }: TemplateEditorProps) {
  const tpl = useSpecTemplate(space, id);
  const filesQ = useTemplateFiles(space, id);
  const invalidate = useInvalidateSdd();
  const schema = useMemo(() => getContractSchema("SpecTemplate") as SchemaNode, []);
  const [rulesDraft, setRulesDraft] = useState<Obj | null>(null);
  const [filesDraft, setFilesDraft] = useState<FileEntry[] | null>(null);
  const [baseHash, setBaseHash] = useState<string | null>(null);
  const [checked, setChecked] = useState<readonly SpecIssue[] | null>(null);
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [fileErrors, setFileErrors] = useState<Readonly<Record<string, string>>>({});
  const [warnings, setWarnings] = useState<readonly Issue[]>([]);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const server = tpl.data?.value as unknown as Obj | undefined;
  const serverHash = tpl.data?.version_hash ?? "";
  const origin = useMemo(() => filesQ.data ?? [], [filesQ.data]);
  const readonly = space.readOnly;

  const rulesDirty = rulesDraft !== null && JSON.stringify(rulesDraft) !== JSON.stringify(server);
  const plan = useMemo(() => (filesDraft === null ? { puts: [], deletes: [] } : planFileChanges(origin, filesDraft)), [filesDraft, origin]);
  const filesDirty = plan.puts.length > 0 || plan.deletes.length > 0;
  const dirty = rulesDirty || filesDirty;
  useEffect(() => {
    onDirtyChange(dirty);
    return () => onDirtyChange(false);
  }, [dirty, onDirtyChange]);

  const externalChange = dirty && baseHash !== null && baseHash !== serverHash;
  const showConflict = conflict || externalChange;
  const value = rulesDraft ?? server ?? {};
  const issues = checked ?? [];
  const errorCount = issues.filter((i) => i.severity === "error").length;

  const beginEdit = () => setBaseHash((h) => h ?? serverHash);
  const editRules = (next: Obj) => {
    beginEdit();
    setRulesDraft(next);
  };
  const editFiles = (next: FileEntry[]) => {
    beginEdit();
    setFilesDraft(next);
  };
  const discard = () => {
    setRulesDraft(null);
    setFilesDraft(null);
    setBaseHash(null);
    setConflict(false);
    setFailure(null);
    setFileErrors({});
    setChecked(null);
  };

  const check = async () => {
    setChecking(true);
    setFailure(null);
    try {
      const def = value as unknown as SpecTemplate;
      const result = await space.client.checkTemplate({ rules: (def.rules ?? {}) as Obj, documents: def.documents ?? [] });
      setChecked(result.issues ?? []);
    } catch (e) {
      setFailure(e instanceof Error && e.message !== "" ? e.message : t.editor.checkFailed);
    } finally {
      setChecking(false);
    }
  };

  const save = async (expected: string) => {
    if (readonly || !dirty) return;
    setSaving(true);
    setFailure(null);
    setFileErrors({});
    setWarnings([]);
    let hash = expected;
    const warns: Issue[] = [];
    let remaining = false;
    try {
      if (rulesDirty && rulesDraft !== null) {
        const saved = await space.client.putSpecTemplate(id, rulesDraft as unknown as SpecTemplate, hash);
        hash = saved.version_hash ?? hash;
        warns.push(...(saved.issues ?? []));
        setRulesDraft(null);
      }
      if (filesDraft !== null && filesDirty) {
        const errors: Record<string, string> = {};
        for (const f of plan.puts) {
          try {
            const saved = await space.client.putSpecTemplateFile(id, f.path, f.bytes ?? f.text ?? "", hash, f.mediaType);
            hash = saved.version_hash ?? hash;
            warns.push(...(saved.issues ?? []));
          } catch (e) {
            if (isConflict(e) || (e instanceof ApiError && e.status === 428)) throw e;
            errors[f.path] = e instanceof Error && e.message !== "" ? e.message : t.editor.saveFailed;
          }
        }
        if (Object.keys(errors).length === 0) {
          for (const path of plan.deletes) {
            try {
              const saved = await space.client.deleteSpecTemplateFile(id, path, hash);
              hash = saved.version_hash ?? hash;
            } catch (e) {
              if (e instanceof ApiError && e.status === 404) continue;
              if (isConflict(e) || (e instanceof ApiError && e.status === 428)) throw e;
              errors[path] = e instanceof Error && e.message !== "" ? e.message : t.editor.saveFailed;
              break;
            }
          }
        }
        if (Object.keys(errors).length === 0) setFilesDraft(null);
        else {
          setFileErrors(errors);
          remaining = true;
        }
      }
      setBaseHash(remaining ? hash : null);
      setConflict(false);
      setChecked(null);
      setWarnings(warns);
      await invalidate();
    } catch (e) {
      if (isConflict(e)) setConflict(true);
      else {
        const failureKind = classifySddError(e, t.editor.saveFailed);
        setFailure(failureKind.kind === "unavailable" || failureKind.kind === "notFound" ? t.editor.saveFailed : failureKind.message);
      }
      setBaseHash(hash);
    } finally {
      setSaving(false);
    }
  };

  const overwrite = async () => {
    const fresh = await space.client.getSpecTemplate(id);
    await save(fresh.version_hash ?? serverHash);
  };

  const remove = async () => {
    const name = String((server?.["name"] as string | undefined) ?? id);
    try {
      await space.client.deleteSpecTemplate(id, serverHash);
      setConfirmDelete(false);
      discard();
      onDeleted(name);
    } catch (e) {
      setConfirmDelete(false);
      setFailure(e instanceof Error && e.message !== "" ? e.message : t.delete.failed);
    }
  };

  if (tpl.isPending) return <ListSkeleton rows={6} />;
  if (tpl.isError || server === undefined) return <FailureBlock error={tpl.error} title={t.editor.loadFailed} onRetry={() => void tpl.refetch()} />;

  const name = typeof value["name"] === "string" && value["name"] !== "" ? (value["name"] as string) : id;
  const wanted = params.get(P.tab);
  const active: TemplateTabId = TEMPLATE_TABS.find((x) => x.id === wanted)?.id ?? TEMPLATE_TABS[0]?.id ?? "rules";
  const setParam = (key: string, v: string) => {
    const next = new URLSearchParams(params);
    next.set(key, v);
    setParams(next, { replace: true });
  };
  const documents = (value as unknown as SpecTemplate).documents ?? [];
  const tabLabel = (tab: TemplateTabId): string => t.tabs[tab];

  const panels: Record<TemplateTabId, ReactNode> = {
    rules: (
      <RuleSectionsForm
        schema={schema}
        value={value}
        onChange={editRules}
        issues={issues}
        readonly={readonly || saving}
        sectionId={params.get(P.section)}
        onSectionChange={(sid) => setParam(P.section, sid)}
        navLabel={t.editor.sections}
        idPrefix="sdd-template-rules"
      />
    ),
    files: filesQ.isPending ? (
      <ListSkeleton rows={4} />
    ) : filesQ.isError ? (
      <ErrorBlock title={t.files.loadFailed} message={filesQ.error.message} retryLabel={m.retry} onRetry={() => void filesQ.refetch()} />
    ) : (
      <TemplateFilesPanel
        documents={documents}
        files={filesDraft ?? origin}
        originFiles={origin}
        onChange={editFiles}
        errors={fileErrors}
        onDismissError={(path) => setFileErrors((cur) => Object.fromEntries(Object.entries(cur).filter(([k]) => k !== path)))}
        onSave={() => void (dirty && !readonly && !showConflict && save(baseHash ?? serverHash))}
        disabled={readonly || saving}
      />
    ),
    versions: (
      <div className="sdd-template-versions">
        <p className="app-muted">{t.versions.note}</p>
        <VersionHistory
          base={definitionBase(TEMPLATES_COLLECTION, id)}
          currentHash={serverHash}
          dirty={dirty}
          compare={false}
          onRestored={() => {
            discard();
            void invalidate();
          }}
        />
      </div>
    ),
  };
  const items: TabItem[] = TEMPLATE_TABS.map((x) => ({ id: x.id, label: tabLabel(x.id), title: tabLabel(x.id), content: panels[x.id] }));

  return (
    <div className="sdd-template-editor" data-testid="sdd-template-editor">
      <div className="sdd-toolbar" role="group" aria-label={t.editor.toolbar}>
        <h2 className="sdd-section-title ac-ellipsis">{name}</h2>
        <Button size="sm" loading={checking} onClick={() => void check()}>{checking ? t.editor.checking : t.editor.check}</Button>
        {checked === null ? null : issues.length === 0 ? (
          <span className="app-muted" role="status">{t.editor.checkOk}</span>
        ) : (
          <span className="sdd-check-chip" role="status" data-testid="sdd-template-check" data-tone={errorCount > 0 ? "danger" : "warning"}>{t.editor.checkChip(issues.length)}</span>
        )}
        <span className="sdd-spacer" />
        <span className="app-muted" role="status">{saving ? t.editor.saving : dirty ? t.editor.unsaved : t.editor.saved}</span>
        <Button
          size="sm"
          variant="primary"
          loading={saving}
          aria-disabled={!dirty || readonly || showConflict || undefined}
          title={readonly ? space.readOnlyReason : undefined}
          onClick={() => {
            if (dirty && !readonly && !showConflict) void save(baseHash ?? serverHash);
          }}
        >
          {t.editor.save}
        </Button>
        <MenuButton
          label="⋯"
          panelLabel={t.editor.more}
          blockedReason={readonly ? space.readOnlyReason : undefined}
          items={[{ id: "delete", label: t.editor.delete, danger: true, onSelect: () => setConfirmDelete(true) }]}
        />
      </div>
      {readonly ? <Banner tone="warning" data-testid="sdd-template-readonly">{space.readOnlyReason ?? t.editor.readonly}</Banner> : null}
      {failure === null ? null : <Banner tone="danger">{failure}</Banner>}
      {warnings.length === 0 ? null : (
        <Banner tone="warning" actions={<Button size="sm" onClick={() => setWarnings([])}>{t.editor.dismiss}</Button>}>
          {t.editor.savedWithIssues}
          <ul className="sdd-issues-list">{warnings.map((w, i) => <li key={`${w.code}:${i}`}>{w.message}</li>)}</ul>
        </Banner>
      )}
      {showConflict ? (
        <Banner
          tone="warning"
          title={t.editor.conflictTitle}
          data-testid="sdd-template-conflict"
          actions={
            <>
              <Button size="sm" onClick={() => { discard(); void invalidate(); }}>{t.editor.reload}</Button>
              <Button size="sm" disabled={readonly} onClick={() => void overwrite()}>{t.editor.overwrite}</Button>
            </>
          }
        >
          {t.editor.conflictBody}
        </Banner>
      ) : null}
      {issues.length === 0 ? null : (
        <Disclosure summary={t.editor.checkChip(issues.length)}>
          <ul className="sdd-issues-list">
            {issues.map((i, idx) => <li key={`${i.code}:${i.path ?? ""}:${idx}`} data-tone={i.severity === "error" ? "danger" : "warning"}>{i.message}</li>)}
          </ul>
        </Disclosure>
      )}
      <Tabs tabs={items} activeId={active} onChange={(next) => setParam(P.tab, next)} ariaLabel={t.tabs.label} lazy />
      <ConfirmDialog open={confirmDelete} title={t.delete.title(name)} confirmLabel={t.delete.confirm} cancelLabel={m.cancel} danger onConfirm={() => void remove()} onCancel={() => setConfirmDelete(false)}>
        {t.delete.body}
      </ConfirmDialog>
    </div>
  );
}

