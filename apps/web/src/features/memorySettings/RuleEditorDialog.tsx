import { useMemo, useState } from "react";
import type { Issue } from "@agent-console/contracts";
import type { MemoryRetentionPlan, MemoryScopeRef } from "@agent-console/contracts/memory";
import { RetentionPreview } from "@agent-console/memory-view";
import { SchemaForm, type UiSchema } from "@agent-console/schema-form";
import { Button, Dialog, Tabs } from "@agent-console/ui";
import { CONDITION_WIDGET_NAME, CONFIG_FIELDS } from "../delegation";
import { dropFilledNulls } from "./dropFilled";
import { IssueList } from "./IssueList";
import { LIMITS, RULE_FIELDS } from "./memorySettingsConfig";
import { memorySettingsMessages as t } from "./messages";
import { ruleKey, useRetentionPreview } from "./useRetentionPreview";
import { useDebouncedCheck } from "./useDebouncedCheck";

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

/** 규칙 스키마에서 조건 필드를 찾는다: `x-ui.widget`이 조건 위젯이거나 조건 모델(`ConditionSpec`)을 가리키는 속성. 속성 이름을 모른다. */
export function conditionFieldOf(schema: Obj): string | undefined {
  const props = schema["properties"];
  if (!isObj(props)) return undefined;
  for (const [key, raw] of Object.entries(props)) {
    if (!isObj(raw)) continue;
    const widget = isObj(raw["x-ui"]) ? raw["x-ui"]["widget"] : undefined;
    const ref = typeof raw["$ref"] === "string" ? raw["$ref"] : "";
    if (widget === CONDITION_WIDGET_NAME || ref.endsWith("/ConditionSpec")) return key;
  }
  return undefined;
}

export interface RuleEditorDialogProps {
  /** 규칙 한 개의 계약 스키마 */
  schema: Obj;
  rule: Obj;
  /** 새 규칙이면 true(id 입력 가능) */
  isNew: boolean;
  /** 이미 있는 다른 규칙 id */
  otherIds: ReadonlySet<string>;
  /** 이 규칙을 설정 섹션에 넣어 서버 검사한다 */
  check: (rule: Obj) => Promise<readonly Issue[]>;
  /** 이 규칙 하나로 정리 계획을 만든다 */
  plan: (rules: Obj[]) => Promise<MemoryRetentionPlan>;
  scopeText: (scope: MemoryScopeRef) => string;
  onApply: (rule: Obj) => void;
  onClose: () => void;
  checkDelayMs?: number;
}

/** 정리 규칙 편집기(대화상자): 왼쪽 폼(스키마 폼 + 조건 위젯), 오른쪽 [검사 결과 | 미리보기]. 서버 호출은 props로 받는다. */
export function RuleEditorDialog({ schema, rule: initial, isNew, otherIds, check, plan, scopeText, onApply, onClose, checkDelayMs = LIMITS.checkDelayMs }: RuleEditorDialogProps) {
  const [rule, setRule] = useState<Obj>(initial);
  const [tab, setTab] = useState<"check" | "preview">("check");
  const [composing, setComposing] = useState(false);
  const idKey = RULE_FIELDS.id;
  const id = typeof rule[idKey] === "string" ? rule[idKey].trim() : "";
  const dup = otherIds.has(id);
  const runnable = id !== "" && !dup;
  const key = ruleKey([rule]);
  const result = useDebouncedCheck(key, () => check(rule), runnable, checkDelayMs, composing);
  const errors = result.issues.filter((i) => i.severity === "error").length;
  const blocked = !runnable || result.phase === "checking" || errors > 0;
  const preview = useRetentionPreview(plan);
  const conditionKey = useMemo(() => conditionFieldOf(schema), [schema]);
  const formSchema = useMemo(() => {
    const out = { ...schema };
    delete out["title"];
    delete out["description"];
    return out;
  }, [schema]);
  const ui = useMemo<UiSchema>(() => {
    const out: Obj = {};
    if (conditionKey !== undefined) out[conditionKey] = { "ui:field": CONDITION_WIDGET_NAME, "ui:options": { $rootSchema: schema, $pointer: `/${conditionKey}` } };
    if (!isNew) out[idKey] = { "ui:readonly": true };
    return out as UiSchema;
  }, [conditionKey, schema, isNew, idKey]);
  const submit = () => {
    if (!blocked) onApply({ ...rule, [idKey]: id });
  };
  return (
    <Dialog
      open
      size="xl"
      title={isNew ? t.retention.editorNew : t.retention.editorEdit(id)}
      onClose={onClose}
      actions={
        <>
          <Button onClick={onClose}>{t.cancel}</Button>
          <Button variant="primary" disabled={blocked} onClick={submit}>{t.apply}</Button>
        </>
      }
    >
      <div className="memset-rule" onCompositionStart={() => setComposing(true)} onCompositionEnd={() => setComposing(false)}>
        <div className="memset-rule-form">
          <SchemaForm
            schema={formSchema as never}
            uiSchema={ui}
            value={rule}
            onChange={(next) => setRule((v) => dropFilledNulls(next ?? {}, v) as Obj)}
            customFields={CONFIG_FIELDS}
            rawJsonToggle={false}
            idPrefix="memset-rule"
          />
          {dup ? <p className="memset-warn" role="alert">{t.retention.idTaken}</p> : null}
        </div>
        <div className="memset-rule-side">
          <Tabs
            ariaLabel={t.retention.editorNew}
            activeId={tab}
            onChange={(v) => setTab(v as "check" | "preview")}
            tabs={[
              {
                id: "check",
                label: t.retention.tabCheck,
                content: (
                  <div aria-live="polite" className="memset-rule-pane">
                    {!runnable ? <p className="memset-note app-muted">{dup ? t.retention.idTaken : t.kindEditor.idEmpty}</p> : result.phase === "checking" ? (
                      <p className="memset-note app-muted">{t.kindEditor.checking}</p>
                    ) : result.phase === "failed" ? (
                      <p className="memset-note memset-warn">{t.kindEditor.checkFailed} <Button size="sm" onClick={result.retry}>{t.retry}</Button></p>
                    ) : result.issues.length === 0 ? (
                      <p className="memset-note app-muted">{t.kindEditor.checkOk}</p>
                    ) : (
                      <IssueList issues={result.issues} label={t.kindEditor.issues} />
                    )}
                  </div>
                ),
              },
              {
                id: "preview",
                label: t.retention.tabPreview,
                content: (
                  <div className="memset-rule-pane">
                    <RetentionPreview
                      plan={preview.state.plan}
                      ruleCount={1}
                      loading={preview.state.loading}
                      error={preview.state.error}
                      previewedAt={preview.state.at}
                      onPreview={() => preview.preview([{ ...rule, [idKey]: id }])}
                      scopeText={scopeText}
                    />
                  </div>
                ),
              },
            ]}
          />
        </div>
      </div>
    </Dialog>
  );
}
