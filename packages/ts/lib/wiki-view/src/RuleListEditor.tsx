import type { WikiRuleCounts, WikiRuleRef } from "@agent-console/contracts/wiki";
import { ToneChip } from "@agent-console/markdown-doc";
import { useMemo, useState } from "react";
import { formatMessage, resolveMessages } from "./messages";

/** 규칙 하나의 요약(개수·지침 유무). 규칙 목록 응답(`WikiRulesListItem`)에서 온다. */
export interface RuleSummary {
  id: string;
  name?: string;
  counts?: WikiRuleCounts;
  has_instructions?: boolean;
}

export type RuleListChange =
  | { type: "move"; id: string; from: number; to: number }
  | { type: "remove"; id: string; index: number }
  | { type: "add"; id: string; index: number };

export interface RuleListEditorProps {
  /** 이 위키가 쓰는 규칙(순서가 합치는 순서). `missing`이면 공간에 없는 규칙. */
  value: readonly WikiRuleRef[];
  /** 규칙 id → 요약. 없으면 요약 줄을 그리지 않는다. */
  summaries?: Readonly<Record<string, RuleSummary>>;
  /** 이 공간의 아직 안 쓴 규칙(더하기 메뉴). */
  available?: readonly RuleSummary[];
  /** 순서·빼기·더하기. 새 목록 id는 `nextIds`로 받는다(저장은 호출자). */
  onChange: (nextIds: string[], change: RuleListChange) => void;
  /** [열기]: 규칙 화면 */
  onOpen?: (id: string) => void;
  /** [공용에서 가져오기…]: 있으면 메뉴 맨 아래와 누락 행에 나온다. 인자는 미리 검색할 id. */
  onImport?: (id?: string) => void;
  readOnly?: boolean;
  readOnlyReason?: string;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

/** 요약 줄 조각(개수 0은 뺀다). 문구 틀은 messages. */
function summaryText(s: RuleSummary | undefined, t: Readonly<Record<string, string>>): string {
  if (!s) return "";
  const parts: string[] = [];
  if (s.counts?.write) parts.push(formatMessage(t["rules.sum.write"] ?? "", { n: s.counts.write }));
  if (s.counts?.lint) parts.push(formatMessage(t["rules.sum.lint"] ?? "", { n: s.counts.lint }));
  if (s.counts?.templates) parts.push(formatMessage(t["rules.sum.templates"] ?? "", { n: s.counts.templates }));
  if (s.has_instructions) parts.push(t["rules.sum.instructions"] ?? "");
  return parts.join(" · ");
}

/**
 * "쓰는 규칙" 편집기: 순서(위에서부터 합쳐진다)·빼기·더하기. 규칙이 공간에 없으면 danger 행, 같은 id가 둘이면 warning 행.
 * 키보드: 행 안에서 Alt+↑/↓로 순서를 바꾼다. 읽기 전용이면 모든 변경 단추가 `aria-disabled`.
 * 규칙 id·이름은 서버 데이터이고 이 파일에 없다.
 */
export function RuleListEditor({ value, summaries, available = [], onChange, onOpen, onImport, readOnly = false, readOnlyReason, messages, className }: RuleListEditorProps) {
  const t = resolveMessages(messages);
  const [menu, setMenu] = useState(false);
  const ids = value.map((r) => r.id);
  const duplicates = useMemo(() => {
    const seen = new Set<string>();
    const dup = new Set<string>();
    for (const id of ids) (seen.has(id) ? dup : seen).add(id);
    return dup;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  const emit = (next: string[], change: RuleListChange) => {
    if (!readOnly) onChange(next, change);
  };
  const move = (i: number, to: number) => {
    if (to < 0 || to >= ids.length || to === i) return;
    const next = [...ids];
    const [item] = next.splice(i, 1);
    next.splice(to, 0, item!);
    emit(next, { type: "move", id: item!, from: i, to });
  };
  const remove = (i: number) => emit(ids.filter((_, k) => k !== i), { type: "remove", id: ids[i]!, index: i });
  const add = (id: string) => {
    emit([...ids, id], { type: "add", id, index: ids.length });
    setMenu(false);
  };
  const dis = readOnly ? true : undefined;
  return (
    <div className={`ac-wk-root ac-wk-rules${className ? ` ${className}` : ""}`}>
      {readOnly && readOnlyReason ? <p className="ac-wk-banner" data-tone="warning" role="status">{readOnlyReason}</p> : null}
      {value.length === 0 ? <p className="ac-wk-banner" data-tone="info" role="status">{t["rules.empty"]}</p> : (
        <ol className="ac-wk-rulelist" aria-label={t["rules.label"]}>
          {value.map((r, i) => {
            const s = summaries?.[r.id];
            const name = r.name && r.name !== "" ? r.name : s?.name && s.name !== "" ? s.name : r.id;
            const tone = r.missing ? "danger" : duplicates.has(r.id) ? "warning" : undefined;
            return (
              <li
                key={`${r.id}:${i}`}
                className="ac-wk-rule-row"
                data-tone={tone}
                onKeyDown={(e) => {
                  if (!e.altKey || e.nativeEvent.isComposing) return;
                  if (e.key === "ArrowUp") { e.preventDefault(); move(i, i - 1); }
                  else if (e.key === "ArrowDown") { e.preventDefault(); move(i, i + 1); }
                }}
              >
                <span className="ac-wk-num ac-wk-muted">{i + 1}</span>
                <div className="ac-wk-grow ac-wk-stack">
                  {r.missing ? (
                    <>
                      <span className="ac-wk-ellipsis"><ToneChip label={formatMessage(t["rules.missing"], { id: r.id })} tone="danger" /></span>
                      {onImport ? <button type="button" className="ac-wk-linkbtn" onClick={() => onImport(r.id)}>{t["rules.import"]}</button> : null}
                    </>
                  ) : (
                    <>
                      <span className="ac-wk-rule-name ac-wk-ellipsis" title={name}>{name}</span>
                      {duplicates.has(r.id) ? <span className="ac-wk-muted">{formatMessage(t["rules.duplicate"], { id: r.id })}</span> : null}
                      <span className="ac-wk-muted ac-wk-ellipsis">{summaryText(s, t)}</span>
                    </>
                  )}
                </div>
                {!r.missing && onOpen ? <button type="button" className="ac-wk-btn" onClick={() => onOpen(r.id)}>{formatMessage(t["rules.open"], { name })}</button> : null}
                <button type="button" className="ac-wk-iconbtn" aria-label={formatMessage(t["rules.up"], { name })} aria-disabled={dis ?? (i === 0 || undefined)} title={readOnly ? readOnlyReason : t["rules.up.tip"]} onClick={() => move(i, i - 1)}>
                  <span aria-hidden="true">↑</span>
                </button>
                <button type="button" className="ac-wk-iconbtn" aria-label={formatMessage(t["rules.down"], { name })} aria-disabled={dis ?? (i === value.length - 1 || undefined)} title={readOnly ? readOnlyReason : t["rules.down.tip"]} onClick={() => move(i, i + 1)}>
                  <span aria-hidden="true">↓</span>
                </button>
                <button type="button" className="ac-wk-btn" aria-label={formatMessage(t["rules.remove.label"], { name })} aria-disabled={dis} title={readOnly ? readOnlyReason : undefined} onClick={() => remove(i)}>
                  {t["rules.remove"]}
                </button>
              </li>
            );
          })}
        </ol>
      )}
      <div className="ac-wk-rule-add">
        <button type="button" className="ac-wk-btn" aria-haspopup="menu" aria-expanded={menu} aria-disabled={dis} title={readOnly ? readOnlyReason : undefined} onClick={() => !readOnly && setMenu((v) => !v)}>
          {t["rules.add"]}
        </button>
        {menu ? (
          <ul role="menu" aria-label={t["rules.add"]} className="ac-wk-menu" onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); setMenu(false); } }}>
            {available.length === 0 ? <li role="presentation" className="ac-wk-muted ac-wk-menu-note">{t["rules.add.none"]}</li> : null}
            {available.map((a) => (
              <li key={a.id} role="none">
                <button type="button" role="menuitem" className="ac-wk-menuitem" onClick={() => add(a.id)}>
                  <span className="ac-wk-ellipsis">{a.name && a.name !== "" ? a.name : a.id}</span>
                  <span className="ac-wk-muted ac-wk-ellipsis">{summaryText(a, t)}</span>
                </button>
              </li>
            ))}
            {onImport ? (
              <li role="none" className="ac-wk-menu-sep">
                <button type="button" role="menuitem" className="ac-wk-menuitem" onClick={() => { setMenu(false); onImport(); }}>{t["rules.import"]}</button>
              </li>
            ) : null}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
