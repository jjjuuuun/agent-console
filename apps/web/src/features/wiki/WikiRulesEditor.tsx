/**
 * 위키 규칙 편집기(screen-wiki §10): 도구줄([검사]·저장·메뉴) + 탭 3개(규칙 = 스키마 폼, 본문 파일 = 지침·페이지 틀 파일 편집, 버전 = 공통 버전 기록).
 * 규칙과 본문 파일은 하나의 정의 버전(`ETag`)을 나눠 쓰므로 [저장] 한 번에 규칙 → 파일 쓰기 → 파일 지우기 순으로 이어 쓰고 응답 `ETag`를 다음 요청 `If-Match`로 넘긴다.
 * 초안이 바뀌고 600ms 뒤 서버 검사(`POST /wiki/rules/check`, 저장하지 않음)가 자동으로 돌며, 결과(규칙 위치별 이슈)는 서버 메시지 그대로다 — 화면이 코드를 해석하지 않는다.
 * 검사 오류가 있어도 저장은 막지 않는다. 충돌(412)·읽기 전용·저장 안 한 변경 알림은 여기서 다루고, 이동 막기는 부모 화면이 한다.
 */
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError, definitionBase } from "@agent-console/api-client";
import { ERROR_CODES, getContractSchema } from "@agent-console/contracts";
import { Banner, Button, ConfirmDialog, Disclosure, Tabs, type TabItem } from "@agent-console/ui";
import type { Issue } from "@agent-console/contracts";
import type { SpecIssue } from "@agent-console/contracts/sdd";
import type { WikiIssue, WikiRulesDefinition } from "@agent-console/contracts/wiki";
import { ErrorBlock } from "../../app/ErrorBlock";
import { MenuButton } from "../../app/menuParts";
import type { SchemaNode } from "../../lib/schemaTools";
import { RuleSectionsForm } from "../sdd";
import { planFileChanges, type FileEntry } from "../resources";
import { VersionHistory } from "../versions";
import { FailureBlock, ListSkeleton } from "./parts";
import { WIKI_RULE_WIDGET_FIELDS } from "./ruleWidgets";
import { WikiRuleFilesPanel, type RuleFileLink } from "./WikiRuleFilesPanel";
import { classifyWikiError } from "./wikiErrors";
import { useInvalidateWiki } from "./useWikiApi";
import { useWikiRuleFiles, useWikiRulesView, type WikiRulesSpace } from "./useWikiRulesApi";
import { WIKI_LIMITS, WIKI_RULES_SCREEN, type WikiRulesTabId } from "./wikiConfig";
import { wikiRulesMessages as t } from "./rulesScreenMessages";

type Obj = Record<string, unknown>;
const P = WIKI_RULES_SCREEN.params;
const isConflict = (e: unknown): boolean => e instanceof ApiError && (e.code === ERROR_CODES.VERSION_CONFLICT || e.status === 412);
const asSpecIssue = (i: WikiIssue): SpecIssue => i as unknown as SpecIssue;

/** 규칙 문서가 가리키는 본문 파일(한 파일 참조들 먼저, 그 다음 목록 항목의 파일). 어느 속성이 파일을 가리키는지는 데이터(`wikiData.json`)다. */
export function ruleFileLinks(def: Readonly<Obj>, fields: typeof WIKI_RULES_SCREEN.fileFields = WIKI_RULES_SCREEN.fileFields): RuleFileLink[] {
  const out: RuleFileLink[] = [];
  const fileOf = (ref: unknown): string | undefined => {
    const file = typeof ref === "object" && ref !== null ? (ref as Obj)[fields.fileKey] : undefined;
    return typeof file === "string" && file !== "" ? file : undefined;
  };
  for (const key of fields.single) {
    const file = fileOf(def[key]);
    if (file !== undefined) out.push({ file, kind: "instructions" });
  }
  for (const key of fields.list) {
    const items = def[key];
    if (!Array.isArray(items)) continue;
    for (const item of items) {
      const file = fileOf(item);
      if (file === undefined) continue;
      const label = fields.labelKeys.map((k) => (item as Obj)[k]).find((v): v is string => typeof v === "string" && v !== "");
      out.push({ file, kind: "template", ...(label === undefined ? {} : { label }) });
    }
  }
  return out;
}

export interface WikiRulesEditorProps {
  space: WikiRulesSpace;
  id: string;
  params: URLSearchParams;
  setParams: (next: URLSearchParams, options?: { replace?: boolean }) => void;
  /** 저장 안 한 변경이 생기거나 없어질 때 */
  onDirtyChange: (dirty: boolean) => void;
  /** 규칙을 지운 뒤(목록을 새로 읽고 선택을 풀어야 한다) */
  onDeleted: (name: string) => void;
}

export function WikiRulesEditor({ space, id, params, setParams, onDirtyChange, onDeleted }: WikiRulesEditorProps) {
  const ruleQ = useWikiRulesView(space, id);
  const filesQ = useWikiRuleFiles(space, id);
  const invalidate = useInvalidateWiki();
  const schema = useMemo(() => getContractSchema("WikiRulesDefinition") as SchemaNode, []);
  const [rulesDraft, setRulesDraft] = useState<Obj | null>(null);
  const [filesDraft, setFilesDraft] = useState<FileEntry[] | null>(null);
  const [baseHash, setBaseHash] = useState<string | null>(null);
  const [checked, setChecked] = useState<readonly WikiIssue[] | null>(null);
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [fileErrors, setFileErrors] = useState<Readonly<Record<string, string>>>({});
  const [warnings, setWarnings] = useState<readonly Issue[]>([]);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [epoch, setEpoch] = useState(0);

  const view = ruleQ.data?.value;
  const server = view?.rules as unknown as Obj | undefined;
  const serverHash = ruleQ.data?.version_hash ?? "";
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
  const value: Obj = rulesDraft ?? server ?? {};
  const files = filesDraft ?? origin;
  // 서버가 처음 준 검사 이슈(열 때)와 [검사]·자동 검사 결과 중 최근 것을 보인다
  const issues: readonly WikiIssue[] = checked ?? view?.issues ?? [];
  const errorCount = issues.filter((i) => i.severity === "error").length;
  const warnCount = issues.length - errorCount;

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
    setEpoch((n) => n + 1);
  };

  const ticket = useRef(0);
  const runCheck = async (body: Obj, paths: readonly string[]) => {
    const mine = ++ticket.current;
    setChecking(true);
    try {
      const result = await space.client.checkWikiRules({ rules: body, files: [...paths] });
      if (mine === ticket.current) {
        setChecked(result.issues ?? []);
        setFailure(null);
      }
    } catch (e) {
      if (mine === ticket.current) setFailure(e instanceof Error && e.message !== "" ? e.message : t.editor.checkFailed);
    } finally {
      if (mine === ticket.current) setChecking(false);
    }
  };
  const check = () => void runCheck(value, files.map((f) => f.path));

  // 초안이 바뀌고 잠시 뒤 서버 검사(웹은 정규식·글롭·조건을 평가하지 않는다)
  const latestCheck = useRef(runCheck);
  useEffect(() => {
    latestCheck.current = runCheck;
  });
  const draftKey = dirty ? JSON.stringify([rulesDraft, filesDraft?.map((f) => f.path)]) : "";
  useEffect(() => {
    if (draftKey === "") return;
    const timer = setTimeout(() => {
      const paths = (filesDraft ?? origin).map((f) => f.path);
      void latestCheck.current(rulesDraft ?? server ?? {}, paths);
    }, WIKI_LIMITS.ruleCheckDebounceMs);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftKey]);

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
        const saved = await space.client.putWikiRules(id, rulesDraft as unknown as WikiRulesDefinition, hash);
        hash = saved.version_hash ?? hash;
        warns.push(...(saved.issues ?? []));
        setRulesDraft(null);
      }
      if (filesDraft !== null && filesDirty) {
        const errors: Record<string, string> = {};
        for (const f of plan.puts) {
          try {
            const saved = await space.client.putWikiRulesFile(id, f.path, f.bytes ?? f.text ?? "", hash, f.mediaType);
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
              const saved = await space.client.deleteWikiRulesFile(id, path, hash);
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
        const kind = classifyWikiError(e, t.editor.saveFailed);
        setFailure(kind.kind === "unavailable" || kind.kind === "notFound" ? t.editor.saveFailed : "message" in kind && kind.message !== "" ? kind.message : t.editor.saveFailed);
      }
      setBaseHash(hash);
    } finally {
      setSaving(false);
    }
  };

  const overwrite = async () => {
    const fresh = await space.client.getWikiRules(id);
    await save(fresh.version_hash ?? serverHash);
  };

  const remove = async () => {
    const name = String((server?.["name"] as string | undefined) ?? id);
    try {
      await space.client.deleteWikiRules(id, serverHash);
      setConfirmDelete(false);
      discard();
      onDeleted(name);
    } catch (e) {
      setConfirmDelete(false);
      setFailure(e instanceof Error && e.message !== "" ? e.message : t.delete.failed);
    }
  };

  if (ruleQ.isPending) return <ListSkeleton rows={6} />;
  if (ruleQ.isError || server === undefined || view === undefined) return <FailureBlock error={ruleQ.error} title={t.editor.loadFailed} onRetry={() => void ruleQ.refetch()} />;

  const name = typeof value["name"] === "string" && value["name"] !== "" ? (value["name"] as string) : id;
  const wanted = params.get(P.tab);
  const active: WikiRulesTabId = WIKI_RULES_SCREEN.tabs.find((x) => x.id === wanted)?.id ?? WIKI_RULES_SCREEN.tabs[0]?.id ?? "rules";
  const setParam = (key: string, v: string) => {
    const next = new URLSearchParams(params);
    next.set(key, v);
    setParams(next, { replace: true });
  };
  const usedBy = view.used_by ?? [];
  const usedNames = usedBy.map((w) => (w.name !== undefined && w.name !== "" ? w.name : w.id)).join(", ");
  const advanced = WIKI_RULES_SCREEN.includeAdvanced;

  const panels: Record<WikiRulesTabId, ReactNode> = {
    rules: (
      <RuleSectionsForm
        key={epoch}
        schema={schema}
        value={value}
        onChange={editRules}
        issues={issues.map(asSpecIssue)}
        readonly={readonly || saving}
        sectionId={params.get(P.section)}
        onSectionChange={(sid) => setParam(P.section, sid)}
        navLabel={t.editor.sections}
        idPrefix="wiki-rules-form"
        extraFields={WIKI_RULE_WIDGET_FIELDS}
        includeAdvanced={advanced}
        sectionNote={(section) => (advanced.includes(section.path[0] as string) ? <p className="app-muted wiki-hint">{t.editor.syntaxHint}</p> : null)}
      />
    ),
    files: filesQ.isPending ? (
      <ListSkeleton rows={4} />
    ) : filesQ.isError ? (
      <ErrorBlock title={t.files.loadFailed} message={filesQ.error.message} retryLabel={t.editor.reload} onRetry={() => void filesQ.refetch()} />
    ) : (
      <WikiRuleFilesPanel
        links={ruleFileLinks(value)}
        files={files}
        originFiles={origin}
        onChange={editFiles}
        errors={fileErrors}
        onDismissError={(path) => setFileErrors((cur) => Object.fromEntries(Object.entries(cur).filter(([k]) => k !== path)))}
        onSave={() => void (dirty && !readonly && !showConflict && save(baseHash ?? serverHash))}
        disabled={readonly || saving}
      />
    ),
    versions: (
      <div className="wiki-rule-versions">
        <p className="app-muted">{t.versions.note}</p>
        <VersionHistory
          base={definitionBase(WIKI_RULES_SCREEN.collection, id)}
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
  const items: TabItem[] = WIKI_RULES_SCREEN.tabs.map((x) => ({ id: x.id, label: t.tabs[x.labelKey] ?? x.id, title: t.tabs[x.labelKey] ?? x.id, content: panels[x.id] }));

  return (
    <div
      className="wiki-rule-editor"
      data-testid="wiki-rule-editor"
      onKeyDown={(e) => {
        if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) {
          e.preventDefault();
          if (dirty && !readonly && !showConflict) void save(baseHash ?? serverHash);
        }
      }}
    >
      <div className="wiki-toolbar" role="group" aria-label={t.editor.toolbar}>
        <h2 className="wiki-section-title ac-ellipsis">{name}</h2>
        <Button size="sm" loading={checking} onClick={check}>{checking ? t.editor.checking : t.editor.check}</Button>
        {checked === null && (view.issues ?? []).length === 0 ? null : issues.length === 0 ? (
          <span className="app-muted" role="status">{t.editor.checkOk}</span>
        ) : (
          <span className="wiki-check-chip" role="status" data-testid="wiki-rule-check" data-tone={errorCount > 0 ? "danger" : "warning"}>{t.editor.checkChip(warnCount, errorCount)}</span>
        )}
        <span className="wiki-spacer" />
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
          label={<><span aria-hidden="true">⋯</span><span className="ac-sr-only">{t.editor.more}</span></>}
          panelLabel={t.editor.more}
          blockedReason={readonly ? space.readOnlyReason : undefined}
          items={[{ id: "delete", label: t.editor.delete, danger: true, onSelect: () => setConfirmDelete(true) }]}
        />
      </div>
      {usedBy.length === 0 ? null : <Banner tone="info" data-testid="wiki-rule-usedby">{t.usedBy(usedNames)}</Banner>}
      {readonly ? <Banner tone="warning" data-testid="wiki-rule-readonly">{space.readOnlyReason ?? t.editor.readonly}</Banner> : null}
      {failure === null ? null : <Banner tone="danger">{failure}</Banner>}
      {warnings.length === 0 ? null : (
        <Banner tone="warning" actions={<Button size="sm" onClick={() => setWarnings([])}>{t.editor.dismiss}</Button>}>
          {t.editor.savedWithIssues}
          <ul className="wiki-issue-lines">{warnings.map((w, i) => <li key={`${w.code}:${i}`}>{w.message}</li>)}</ul>
        </Banner>
      )}
      {showConflict ? (
        <Banner
          tone="warning"
          title={t.editor.conflictTitle}
          data-testid="wiki-rule-conflict"
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
        <Disclosure summary={t.editor.issuesFold(warnCount, errorCount)}>
          <ul className="wiki-issue-lines" data-testid="wiki-rule-issues">
            {issues.map((i, idx) => <li key={`${i.code}:${i.path ?? ""}:${idx}`} data-tone={i.severity === "error" ? "danger" : "warning"}>{i.message}{i.path ? <span className="app-muted wiki-mono"> {i.path}</span> : null}</li>)}
          </ul>
        </Disclosure>
      )}
      <Tabs tabs={items} activeId={active} onChange={(next) => setParam(P.tab, next)} ariaLabel={t.tabs["label"] ?? ""} lazy />
      <ConfirmDialog open={confirmDelete} title={t.delete.title(name)} confirmLabel={t.delete.confirm} cancelLabel={t.delete.cancel} danger onConfirm={() => void remove()} onCancel={() => setConfirmDelete(false)}>
        <p>{t.delete.body}</p>
        {usedBy.length > 0 ? <p data-testid="wiki-rule-delete-usedby">{t.delete.usedBy(usedBy.length)}: {usedNames}</p> : space.projectId === null ? <p className="app-muted">{t.delete.library}</p> : null}
      </ConfirmDialog>
    </div>
  );
}
