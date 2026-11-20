import { useState } from "react";
import { Link } from "react-router";
import type { Issue } from "@agent-console/contracts";
import type { MemoryRetentionPlan, MemoryRetentionResult, MemoryScopeRef } from "@agent-console/contracts/memory";
import { RetentionPreview } from "@agent-console/memory-view";
import { Banner, Button, ConfirmDialog, Icon } from "@agent-console/ui";
import { AutoTargets, type AutoTargetsProps } from "./AutoTargets";
import { RuleEditorDialog } from "./RuleEditorDialog";
import { RULE_ACTIONS, RULE_FIELDS } from "./memorySettingsConfig";
import { memorySettingsMessages as t } from "./messages";
import { ruleKey, useRetentionPreview } from "./useRetentionPreview";
import { IssueList } from "./IssueList";

type Obj = Record<string, unknown>;
const idOf = (r: Obj): string => (typeof r[RULE_FIELDS.id] === "string" ? (r[RULE_FIELDS.id] as string) : "");
const actionOf = (r: Obj): string => (typeof r[RULE_FIELDS.action] === "string" ? (r[RULE_FIELDS.action] as string) : RULE_ACTIONS.archive);

export interface RetentionPanelProps {
  /** 설정 초안의 규칙 목록(선언 순서 = 적용 순서) */
  rules: readonly Obj[];
  /** 저장된 규칙 목록 */
  savedRules: readonly Obj[];
  onChange: (next: Obj[]) => void;
  /** 규칙 한 개의 계약 스키마(편집기 폼) */
  ruleSchema: Obj;
  /** 설정에 저장하지 않은 변경이 있다(적용은 저장된 규칙으로 하므로 막는다) */
  dirty: boolean;
  /** 자동 실행 주기 글(설치자 값). null = 자동 실행 꺼짐 */
  everyText: string | null;
  /** 조건 요약 글 */
  summarize: (rule: Obj) => string;
  /** 규칙 목록 후보를 설정 섹션에 넣어 서버 검사한다 */
  check: (rules: Obj[]) => Promise<readonly Issue[]>;
  plan: (rules: Obj[]) => Promise<MemoryRetentionPlan>;
  apply: () => Promise<MemoryRetentionResult>;
  scopeText: (scope: MemoryScopeRef) => string;
  /** 적용 결과의 [메모리에서 보기] 링크(정리가 남긴 쓴 주체 필터). 메모리 화면이 없으면 null */
  resultHref: (targetId: string) => string | null;
  /**
   * 미리보기·적용 대상 저장소(`screen-memory` §10.6.3). 선택지가 2개 이상이면 선택 컨트롤, 1개면 글자만, 생략하면 그리지 않는다.
   * 규칙은 하나이고 어느 저장소에 미리보기·적용할지만 고른다. 값(`id`)은 호출한 쪽의 것이고 이 컴포넌트는 뜻을 모른다.
   */
  target?: { value: string; /** 비교·결과 링크에 쓰는 실제 저장소 키(생략하면 value). 고른 값과 별개로, 현재 프로젝트가 바뀌면 같이 바뀌어야 한다 */ key?: string; options: readonly { id: string; label: string }[]; onChange: (id: string) => void };
  /** 자동 정리 대상 세 칸(생략하면 그리지 않는다) */
  autoTargets?: AutoTargetsProps;
  /** 자동 실행 상태 줄 뒤에 붙이는 설명(예: 자동 정리가 어느 저장소만 다루는지). 없으면 붙이지 않는다 */
  autoNote?: string | undefined;
  onApplied?: () => void;
  disabled?: boolean;
  checkDelayMs?: number;
}

type Editor = { index: number; rule: Obj; isNew: boolean } | null;

/** 정리 규칙 목록 + 편집기 + 미리보기/적용(표현 전용). 설정 문서에는 초안만 바꾸고 서버 호출은 props로 받는다. */
export function RetentionPanel(p: RetentionPanelProps) {
  const [editor, setEditor] = useState<Editor>(null);
  const [confirm, setConfirm] = useState(false);
  const [applying, setApplying] = useState(false);
  const [done, setDone] = useState<{ result: MemoryRetentionResult; at: number; target: string } | null>(null);
  /** 미리보기를 한 대상(대상이 바뀌면 그 미리보기로 적용하지 못하게 막는다) */
  const [previewedTarget, setPreviewedTarget] = useState<string | null>(null);
  const targetValue = p.target === undefined ? null : (p.target.key ?? p.target.value);
  const [applyError, setApplyError] = useState(false);
  const preview = useRetentionPreview(p.plan);
  const key = ruleKey(p.rules);
  const savedKeys = new Set(p.savedRules.map((r) => JSON.stringify(r)));
  const count = preview.state.plan?.count ?? 0;
  const items = preview.state.plan?.items ?? [];
  const archives = items.filter((i) => i.action === RULE_ACTIONS.archive).length;
  const deletes = items.filter((i) => i.action === RULE_ACTIONS.delete).length;
  const reason = p.dirty ? t.retention.blocked.unsaved : preview.state.plan === null ? t.retention.blocked.none : previewedTarget !== targetValue ? t.retention.blocked.targetChanged : preview.state.key !== key ? t.retention.blocked.stale : count === 0 ? t.retention.blocked.empty : null;
  const hasDelete = p.rules.some((r) => actionOf(r) === RULE_ACTIONS.delete);
  const savedDelete = p.savedRules.some((r) => actionOf(r) === RULE_ACTIONS.delete);

  const move = (i: number, d: -1 | 1) => {
    const next = [...p.rules];
    const [item] = next.splice(i, 1);
    if (item === undefined) return;
    next.splice(i + d, 0, item);
    p.onChange(next);
  };
  const open = (index: number, isNew: boolean) => setEditor({ index, isNew, rule: isNew ? { [RULE_FIELDS.id]: "", [RULE_FIELDS.action]: RULE_ACTIONS.archive } : (p.rules[index] ?? {}) });
  const doApply = () => {
    setConfirm(false);
    setApplying(true);
    setApplyError(false);
    p.apply().then(
      (result) => {
        setDone({ result, at: Math.floor(Date.now() / 1000), target: targetValue ?? "" });
        setApplying(false);
        preview.reset();
        p.onApplied?.();
      },
      () => {
        setApplyError(true);
        setApplying(false);
      },
    );
  };
  const failed = done?.result.issues ?? [];
  const resultLink = done === null ? null : p.resultHref(done.target);
  return (
    <section className="memset-panel" aria-label={t.retention.label} data-testid="memset-retention">
      <div className="memset-listhead">
        <h3 className="memset-title">{t.retention.title(p.rules.length)}</h3>
        <Button size="sm" disabled={p.disabled === true} onClick={() => open(p.rules.length, true)}>+ {t.retention.add}</Button>
      </div>
      <p className="memset-note app-muted">{t.retention.help}</p>
      {p.rules.length === 0 ? (
        <div className="memset-empty">
          <p className="memset-strong">{t.retention.empty}</p>
          <p className="app-muted memset-note">{t.retention.emptyBody}</p>
        </div>
      ) : (
        <ol className="memset-rows" aria-label={t.retention.label}>
          {p.rules.map((r, i) => {
            const id = idOf(r);
            const action = actionOf(r);
            const changed = !savedKeys.has(JSON.stringify(r));
            const unseen = changed && preview.state.seen[id] !== JSON.stringify(r);
            return (
              <li key={`${id}:${i}`} className="memset-rule-row" data-rule-id={id}>
                <span className="memset-cell memset-order">
                  <span className="memset-num">{i + 1}</span>
                  <Button size="sm" variant="ghost" aria-label={t.retention.up(id)} disabled={i === 0 || p.disabled === true} onClick={() => move(i, -1)}>↑</Button>
                  <Button size="sm" variant="ghost" aria-label={t.retention.down(id)} disabled={i === p.rules.length - 1 || p.disabled === true} onClick={() => move(i, 1)}>↓</Button>
                </span>
                <span className="memset-cell memset-mono ac-ellipsis" title={id}>{id}</span>
                <span className="memset-cell ac-ellipsis" title={typeof r["description"] === "string" ? (r["description"] as string) : undefined}>
                  {typeof r["description"] === "string" && r["description"] !== "" ? r["description"] : p.summarize(r)}
                </span>
                <span className="memset-cell">
                  <span className="memset-chip-static" data-tone={action === RULE_ACTIONS.delete ? "danger" : undefined}>
                    {action === RULE_ACTIONS.delete ? <span className="memset-danger-icon" aria-hidden="true" /> : null}
                    {t.retention.action[action] ?? action}
                  </span>
                  {unseen ? <span className="memset-warn-inline"> <span className="app-sev" data-severity="warning" aria-hidden="true">▲</span> {t.retention.noPreview}</span> : null}
                </span>
                <span className="memset-cell memset-actions" role="group" aria-label={t.retention.actionsFor(id)}>
                  <Button size="sm" disabled={p.disabled === true} onClick={() => open(i, false)}>{t.retention.edit}</Button>
                  <Button size="sm" variant="danger" disabled={p.disabled === true} onClick={() => p.onChange(p.rules.filter((_, n) => n !== i) as Obj[])}>{t.retention.remove}</Button>
                </span>
              </li>
            );
          })}
        </ol>
      )}
      <p className="memset-note app-muted">{p.everyText === null ? t.retention.autoOff : `${t.retention.autoOn(p.everyText)}${p.autoNote ?? ""}`}</p>
      {p.autoTargets === undefined ? null : <AutoTargets {...p.autoTargets} />}
      {p.everyText !== null && savedDelete ? <Banner tone="warning">{t.retention.autoDelete(p.everyText)}</Banner> : null}
      <div className="memset-preview" aria-label={t.retention.previewTitle} role="group">
        {p.target === undefined ? null : (
          <div className="memset-target" data-testid="memset-retention-target">
            {p.target.options.length > 1 ? (
              <>
                <label htmlFor="memset-retention-target" className="memset-target-label">{t.retention.target}</label>
                <select id="memset-retention-target" className="memset-target-select" value={p.target.value} onChange={(e) => p.target?.onChange(e.target.value)}>
                  {p.target.options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                </select>
              </>
            ) : (
              <span><span className="memset-target-label">{t.retention.target}</span> <strong>{p.target.options[0]?.label ?? ""}</strong></span>
            )}
          </div>
        )}
        <RetentionPreview
          plan={preview.state.plan}
          ruleCount={p.rules.length}
          loading={preview.state.loading}
          error={preview.state.error}
          previewedAt={preview.state.at}
          onPreview={() => { setPreviewedTarget(targetValue); preview.preview([...p.rules]); }}
          onApply={() => setConfirm(true)}
          canApply={reason === null && !applying}
          applyBlockedReason={reason}
          result={done?.result ?? null}
          resultAt={done?.at ?? null}
          scopeText={p.scopeText}
        />
        {applyError ? <p className="memset-warn" role="alert">{t.retention.applyFailed}</p> : null}
        {failed.length > 0 ? <div><p className="memset-note">{t.retention.failedIssues}</p><IssueList issues={failed} label={t.retention.failedIssues} /></div> : null}
        {done !== null && resultLink !== null ? <Link className="memset-link" to={resultLink}>{t.retention.viewInMemory} <Icon name="external-link" /></Link> : null}
      </div>
      {editor === null ? null : (
        <RuleEditorDialog
          schema={p.ruleSchema}
          rule={editor.rule}
          isNew={editor.isNew}
          otherIds={new Set(p.rules.filter((_, n) => n !== editor.index).map(idOf))}
          check={(rule) => p.check(p.rules.length === editor.index ? [...p.rules, rule] : p.rules.map((r, n) => (n === editor.index ? rule : r)))}
          plan={p.plan}
          scopeText={p.scopeText}
          onClose={() => setEditor(null)}
          onApply={(rule) => {
            p.onChange(editor.isNew ? [...p.rules, rule] : p.rules.map((r, n) => (n === editor.index ? rule : r)));
            setEditor(null);
          }}
          {...(p.checkDelayMs === undefined ? {} : { checkDelayMs: p.checkDelayMs })}
        />
      )}
      <ConfirmDialog
        open={confirm}
        title={t.retention.confirmTitle}
        confirmLabel={t.retention.confirmApply}
        cancelLabel={t.cancel}
        danger={hasDelete}
        onCancel={() => setConfirm(false)}
        onConfirm={doApply}
      >
        <p className="ac-text">{t.retention.confirmBody(count, archives, deletes)}</p>
        {deletes > 0 ? <Banner tone="danger">{t.retention.confirmDanger}</Banner> : null}
      </ConfirmDialog>
    </section>
  );
}
