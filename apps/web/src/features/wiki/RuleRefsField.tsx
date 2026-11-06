/**
 * 스키마 폼 위젯 `wiki-rule-refs`(계약 `KNOWN_UI_WIDGETS.WIKI_RULE_REFS`): 위키가 쓰는 규칙 id 목록을 `RuleListEditor`(순서·빼기·더하기)로 편집한다.
 * 필드 컴포넌트는 `SchemaFormFieldProps`만 받고 규칙 요약·더할 수 있는 목록·열기/가져오기 콜백은 `RuleRefsProvider` 문맥에서 읽는다(API를 모른다).
 */
import { createContext, useContext, useMemo, type ReactNode } from "react";
import type { SchemaFormFieldProps } from "@agent-console/schema-form";
import { RuleListEditor, type RuleSummary } from "@agent-console/wiki-view";
import type { WikiRuleRef } from "@agent-console/contracts/wiki";
import { sectionDomId } from "./rulesSections";
import { wikiTabMessages } from "./tabMessages";

export interface RuleRefsEnv {
  /** 서버가 합친 규칙 줄(이름·누락 표시). 아직 저장하지 않은 id는 여기 없다 */
  refs: readonly WikiRuleRef[];
  /** 규칙 id → 요약(이 공간 규칙 목록에서) */
  summaries: Readonly<Record<string, RuleSummary>>;
  /** 이 공간의 아직 안 쓴 규칙은 위젯이 `summaries`에서 뺀다 — 전체 규칙 목록 */
  all: readonly RuleSummary[];
  onOpen?: ((id: string) => void) | undefined;
  onImport?: ((id?: string) => void) | undefined;
  /** 규칙을 뺐을 때(되돌리기 토스트용): `restore`를 부르면 뺀 목록을 되돌린다 */
  onRemoved?: ((restore: () => void) => void) | undefined;
  readOnlyReason?: string | undefined;
}

const EMPTY: RuleRefsEnv = { refs: [], summaries: {}, all: [] };
const Ctx = createContext<RuleRefsEnv>(EMPTY);

export function RuleRefsProvider({ env, children }: { env: RuleRefsEnv; children: ReactNode }) {
  return <Ctx.Provider value={env}>{children}</Ctx.Provider>;
}

export function RuleRefsField({ value, onChange, label, disabled, readonly }: SchemaFormFieldProps) {
  const env = useContext(Ctx);
  const ids = useMemo(() => (Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : []), [value]);
  const refs = useMemo<WikiRuleRef[]>(
    () =>
      ids.map((id) => {
        const known = env.refs.find((r) => r.id === id);
        if (known !== undefined) return known;
        const s = env.summaries[id];
        return s?.name === undefined ? { id } : { id, name: s.name };
      }),
    [ids, env.refs, env.summaries],
  );
  const available = useMemo(() => env.all.filter((r) => !ids.includes(r.id)), [env.all, ids]);
  const locked = disabled === true || readonly === true || env.readOnlyReason !== undefined;
  return (
    <div id={sectionDomId("used")} className="wiki-rulerefs" role="group" aria-label={label}>
      <p className="app-muted wiki-hint">{wikiTabMessages.rules.usedHint}</p>
      <RuleListEditor
        value={refs}
        summaries={env.summaries}
        available={available}
        onChange={(next, change) => {
          onChange(next);
          if (change.type === "remove") env.onRemoved?.(() => onChange(ids));
        }}
        {...(env.onOpen === undefined ? {} : { onOpen: env.onOpen })}
        {...(env.onImport === undefined ? {} : { onImport: env.onImport })}
        readOnly={locked}
        {...(env.readOnlyReason === undefined ? {} : { readOnlyReason: env.readOnlyReason })}
      />
    </div>
  );
}
