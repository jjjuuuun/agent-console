import { useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import type { CopyApplyItemResult, CopyApplyRequest, CopyApplyResult, CopyPlan, CopyPlanItem, CopyPlanRequest } from "@agent-console/contracts/projects";
import type { DefinitionKey, SpaceRef } from "@agent-console/contracts";
import {
  actionChoicesFor,
  buildApplyRequest,
  canSubmit,
  copyItemKey,
  COPY_REASON_REQUESTED,
  defaultActionFor,
  firstUsableRequested,
  initialSelections,
  selectAction,
  skipWarnings,
  summarizeResult,
  summarizeSelections,
  targetStateLabel,
  validateNewId,
  type CopySelection,
  type CopySelections,
  type ProjectsText,
  type ResultSummary,
} from "@agent-console/projects";
import { KNOWN_COPY_ACTIONS } from "@agent-console/contracts/constants";
import { Banner, Button, Choice, Dialog } from "@agent-console/ui";
import { describeError } from "../../app/errors";
import { FixButtons } from "../../app/fix";
import { useDelayed } from "../../app/useDelayed";
import type { SpaceItem } from "./useSpaceItems";
import "./copyPlan.css";

/** 복사 방향: 제목·제출 문구 키가 달라진다(`copy.<direction>.title`, `copy.submit.<direction>`). */
export type CopyDirection = "import" | "save" | "move";

/** 적용이 끝났을 때 호출자에게 주는 정보(구성 표 새로 읽기·자동 선택·토스트에 쓴다). */
export interface CopyOutcome {
  summary: ResultSummary;
  /** 요청 항목 중 사용할 수 있게 된 첫 항목(새 이름이면 새 id). 없으면 null */
  first: { kind: string; id: string } | null;
  /** 충돌·오류 없이 모두 끝났는가(대화상자가 스스로 닫힌다) */
  allOk: boolean;
}

export interface CopyPlanDialogProps {
  direction: CopyDirection;
  /** "가져오고 실행" 제출 문구 */
  submitStyle?: "default" | "run";
  /** 프로젝트 쪽 표시: 제목의 이름과 안내 문구의 폴더 */
  projectName: string;
  /** 서버가 준 구성 폴더 이름. 모르면 생략(짝 문장 `*_unknown`을 쓴다) */
  projectDir?: string | undefined;
  source: SpaceRef;
  target: SpaceRef;
  initialStep: "pick" | "plan";
  /** `initialStep`이 plan일 때 바로 계획할 항목 */
  initialItems?: readonly DefinitionKey[];
  /** 고르기 단계 목록(원본 공간의 정의) */
  candidates: readonly SpaceItem[];
  candidatesLoading?: boolean;
  candidatesFailed?: boolean;
  onCandidatesRetry?: () => void;
  /** 대상 공간에 이미 있는 정의(같은 이름 칩·새 이름 검사) */
  targetItems: readonly { kind: string; id: string }[];
  /** 원본이 비었을 때 목록 자리에 붙일 링크(예: [공용 구성 화면으로]) */
  emptyAction?: ReactNode;
  /** 값이 있으면 "복사한 뒤 원본에서 지우기" 체크를 보이고 이 값이 기본이다 */
  removeSourceDefault?: boolean;
  planCopy: (request: CopyPlanRequest) => Promise<CopyPlan>;
  applyCopy: (request: CopyApplyRequest) => Promise<CopyApplyResult>;
  text: ProjectsText;
  /** 적용 응답을 받을 때마다(전부 성공이든 아니든) */
  onApplied?: (outcome: CopyOutcome) => void;
  onClose: () => void;
}

type Step = "pick" | "plan" | "result";
type PlanState = { status: "idle" } | { status: "loading" } | { status: "error"; message: string } | { status: "ready"; plan: CopyPlan };

/**
 * 복사 계획 대화상자(screen-projects §5.1): 고르기 → 계획 → 결과. 데이터와 호출은 모두 props로 받는다(API·전역 상태를 모른다).
 * 동작 규칙(기본 동작·제출 가능·건너뜀 경고·요약)은 `@agent-console/projects`의 복사 도우미가 정하고, 이 컴포넌트는 그리기만 한다.
 * 열 때마다 새로 시작하도록 호출자는 열려 있을 때만 마운트한다.
 */
export function CopyPlanDialog(props: CopyPlanDialogProps) {
  const { text, direction } = props;
  const uid = useId();
  const [step, setStep] = useState<Step>(props.initialStep);
  const [query, setQuery] = useState("");
  const [kindFilter, setKindFilter] = useState("");
  const [picked, setPicked] = useState<ReadonlyMap<string, DefinitionKey>>(() => new Map((props.initialItems ?? []).map((i) => [copyItemKey(i), i])));
  const [includeRefs, setIncludeRefs] = useState(true);
  const [planState, setPlanState] = useState<PlanState>(props.initialStep === "plan" ? { status: "loading" } : { status: "idle" });
  const [selections, setSelections] = useState<CopySelections>(new Map());
  const [removeSource, setRemoveSource] = useState(props.removeSourceDefault === true);
  const [results, setResults] = useState<ReadonlyMap<string, CopyApplyItemResult>>(new Map());
  const [planned, setPlanned] = useState<ReadonlyMap<string, CopyPlanItem>>(new Map());
  const [busy, setBusy] = useState(false);
  const [applyError, setApplyError] = useState<ReturnType<typeof describeError> | null>(null);
  const token = useRef(0);
  const latest = useRef(props);
  useEffect(() => {
    latest.current = props;
  });
  const slow = useDelayed(planState.status === "loading", 150);
  const searchRef = useRef<HTMLInputElement>(null);

  /** 계획을 요청하고 도착하면 상태를 채운다(상태 변경은 응답 콜백에서만 — 마운트 효과에서도 부를 수 있다). */
  const fetchPlan = useCallback((items: readonly DefinitionKey[], include: boolean) => {
    const mine = ++token.current;
    const { planCopy, source, target } = latest.current;
    planCopy({ source, target, items: items.map((i) => ({ kind: i.kind, id: i.id })), include_references: include }).then(
      (plan) => {
        if (mine !== token.current) return;
        setPlanState({ status: "ready", plan });
        setSelections((prev) => {
          const fresh = initialSelections(plan);
          for (const [k, v] of prev) if (fresh.has(k)) fresh.set(k, v);
          return fresh;
        });
        setPlanned((prev) => {
          const next = new Map(prev);
          for (const it of plan.items ?? []) next.set(copyItemKey(it), it);
          return next;
        });
      },
      (e: unknown) => {
        if (mine !== token.current) return;
        setPlanState({ status: "error", message: describeError(e, text({ key: "copy.plan.failed" })).message });
      },
    );
  }, [text]);

  /** 사용자 동작(다음·다시 시도·포함 토글·다시 계획)으로 계획을 새로 받는다. */
  const runPlan = useCallback((items: readonly DefinitionKey[], include: boolean) => {
    setPlanState({ status: "loading" });
    setApplyError(null);
    fetchPlan(items, include);
  }, [fetchPlan]);

  // 계획 단계로 바로 열린 진입(행 동작·fix 버튼)은 열자마자 계획한다(처음 상태가 이미 loading).
  useEffect(() => {
    if (props.initialStep === "plan") fetchPlan(props.initialItems ?? [], true);
    else searchRef.current?.focus();
    return () => {
      token.current += 1;
    };
    // 열 때 한 번만(호출자가 열려 있을 때만 마운트)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const plan = planState.status === "ready" ? planState.plan : null;
  const items = useMemo(() => plan?.items ?? [], [plan]);
  const targetIds = useMemo(() => {
    const m = new Map<string, Set<string>>();
    for (const t of props.targetItems) m.set(t.kind, (m.get(t.kind) ?? new Set()).add(t.id));
    return m;
  }, [props.targetItems]);
  const takenFor = useCallback((item: { kind: string }) => targetIds.get(item.kind) ?? new Set<string>(), [targetIds]);

  const sums = plan === null ? null : summarizeSelections(plan, selections);
  const submit = plan === null ? { allowed: false, reason: "empty" as const } : canSubmit(plan, selections, takenFor);
  const warnings = plan === null ? [] : skipWarnings(plan, selections);
  const unsetCount = sums?.unset ?? 0;

  const goPlan = () => {
    const chosen = [...picked.values()];
    if (chosen.length === 0) return;
    setStep("plan");
    runPlan(chosen, includeRefs);
  };

  const apply = async () => {
    if (plan === null || !submit.allowed || busy) return;
    setBusy(true);
    setApplyError(null);
    try {
      const request = buildApplyRequest(plan, selections, { source: props.source, target: props.target, removeSource });
      const response = await props.applyCopy(request);
      const merged = new Map(results);
      for (const r of response.items ?? []) merged.set(copyItemKey(r), r);
      setResults(merged);
      const summary = summarizeResult({ items: [...merged.values()] });
      const first = firstUsableRequested({ items: [...planned.values()] }, { items: [...merged.values()] });
      props.onApplied?.({ summary, first, allOk: summary.allOk });
      if (summary.allOk) props.onClose();
      else setStep("result");
    } catch (e) {
      setApplyError(describeError(e, text({ key: "copy.plan.failed" })));
    } finally {
      setBusy(false);
    }
  };

  const replan = (keys: readonly { kind: string; id: string }[]) => {
    setStep("plan");
    runPlan(keys, false);
  };

  const title = text({ key: `copy.${direction}.title`, params: { name: props.projectName } });
  const submitKey = props.submitStyle === "run" ? "copy.submit.run" : `copy.submit.${direction}`;
  const resultSummary = summarizeResult({ items: [...results.values()] });

  // 고르기 단계 데이터
  const kinds = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of props.candidates) m.set(c.kind, c.kindTitle);
    return [...m];
  }, [props.candidates]);
  const q = query.trim().toLowerCase();
  const visible = useMemo(
    () =>
      props.candidates
        .filter((c) => (kindFilter === "" || c.kind === kindFilter) && (q === "" || c.name.toLowerCase().includes(q) || c.id.toLowerCase().includes(q) || (c.description ?? "").toLowerCase().includes(q)))
        .sort((a, b) => a.kindTitle.localeCompare(b.kindTitle, "ko") || a.name.localeCompare(b.name, "ko", { numeric: true })),
    [props.candidates, kindFilter, q],
  );
  const togglePick = (c: SpaceItem) =>
    setPicked((cur) => {
      const next = new Map(cur);
      const key = copyItemKey(c);
      if (!next.delete(key)) next.set(key, { kind: c.kind, id: c.id });
      return next;
    });
  const toggleAllVisible = () =>
    setPicked((cur) => {
      const next = new Map(cur);
      const all = visible.every((c) => next.has(copyItemKey(c)));
      for (const c of visible) {
        if (all) next.delete(copyItemKey(c));
        else next.set(copyItemKey(c), { kind: c.kind, id: c.id });
      }
      return next;
    });

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      if (step === "pick") goPlan();
      else if (step === "plan") void apply();
    }
  };

  const reasonText = (i: CopyPlanItem) => {
    if (i.reason === COPY_REASON_REQUESTED) return text({ key: "copy.plan.reason_requested" });
    const by = (i.referenced_by ?? []).map((r) => (r.name !== undefined && r.name !== "" ? r.name : r.id)).join(", ");
    return text({ key: "copy.plan.reason_referenced", params: { by } });
  };

  const setSelection = (item: { kind: string; id: string; blocked?: boolean | undefined }, action: string | null) =>
    item.blocked === true ? undefined : setSelections((cur) => selectAction(cur, item, action, takenFor(item)));
  const setNewId = (item: { kind: string; id: string }, newId: string) =>
    setSelections((cur) => {
      const next = new Map(cur);
      const prev: CopySelection = next.get(copyItemKey(item)) ?? { action: KNOWN_COPY_ACTIONS.RENAME };
      next.set(copyItemKey(item), { ...prev, newId });
      return next;
    });
  const SKIP = KNOWN_COPY_ACTIONS.SKIP;
  const RENAME = KNOWN_COPY_ACTIONS.RENAME;
  const OVERWRITE = KNOWN_COPY_ACTIONS.OVERWRITE;

  const requested = items.filter((i) => i.reason === COPY_REASON_REQUESTED).length;
  const blockedText = submit.reason === "need_choice" ? text({ key: "copy.plan.need_choice", params: { n: unsetCount } })
    : submit.reason === "bad_new_id" ? text({ key: "copy.plan.bad_new_id" })
    : submit.reason === "all_skipped" ? text({ key: "copy.plan.all_skipped" })
    : submit.reason === "empty" ? text({ key: "copy.plan.empty" }) : null;
  const libraryTarget = props.target.project_id == null;

  const body = (
    <div className="cpd" data-step={step} onKeyDown={onKey}>
      {applyError === null ? null : (
        <Banner tone="danger">
          <span>{applyError.message}</span>
          <FixButtons fix={applyError.fix} onNavigate={props.onClose} />
        </Banner>
      )}
      {step === "pick" ? (
        <>
          <p className="cpd-intro app-muted">
            {direction === "save"
              ? text({ key: "copy.save.intro", params: { name: props.projectName } })
              : props.projectDir === undefined
                ? text({ key: "copy.import.intro_unknown", params: { name: props.projectName } })
                : text({ key: "copy.import.intro", params: { name: props.projectName, dir: props.projectDir } })}
          </p>
          <div className="cpd-filter">
            <input
              ref={searchRef}
              type="search"
              className="ac-input"
              aria-label={text({ key: "copy.pick.search" })}
              placeholder={text({ key: "copy.pick.search_placeholder" })}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  document.getElementById(`${uid}-list`)?.querySelector<HTMLInputElement>("input[type=checkbox]")?.focus();
                }
              }}
            />
            <label className="cpd-kind">
              <span className="app-muted">{text({ key: "copy.pick.kind" })}</span>
              <select className="ac-input" value={kindFilter} onChange={(e) => setKindFilter(e.target.value)}>
                <option value="">{text({ key: "copy.pick.kind_all" })}</option>
                {kinds.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
              </select>
            </label>
          </div>
          {props.candidatesLoading ? (
            <p className="app-muted" role="status">{text({ key: "copy.pick.loading" })}</p>
          ) : props.candidatesFailed && props.candidates.length === 0 ? (
            <p className="cpd-error" role="alert">
              {text({ key: "copy.pick.failed" })} <Button size="sm" variant="ghost" onClick={props.onCandidatesRetry}>{text({ key: "copy.plan.retry" })}</Button>
            </p>
          ) : props.candidates.length === 0 ? (
            <div className="cpd-empty">
              <p>{text({ key: direction === "save" ? "copy.pick.empty_project" : "copy.pick.empty_library" })}</p>
              {props.emptyAction}
            </div>
          ) : visible.length === 0 ? (
            <p className="app-muted">{text({ key: "copy.pick.no_match", params: { query: query.trim() } })}</p>
          ) : (
            <ul id={`${uid}-list`} className="cpd-list" aria-label={text({ key: "copy.pick.list" })} onKeyDown={(e) => {
              if ((e.ctrlKey || e.metaKey) && (e.key === "a" || e.key === "A")) {
                e.preventDefault();
                toggleAllVisible();
              }
            }}>
              {visible.map((c) => {
                const key = copyItemKey(c);
                const exists = targetIds.get(c.kind)?.has(c.id) === true;
                return (
                  <li key={key} className="cpd-pick-row" data-checked={picked.has(key) ? "true" : undefined}>
                    <Choice checked={picked.has(key)} onChange={() => togglePick(c)} className="cpd-pick-choice">
                      <span className="cpd-name ac-ellipsis" title={c.name}>{c.name}</span>
                    </Choice>
                    <span className="prj-kind-chip ac-ellipsis cpd-kind-chip" title={c.kindTitle}>{c.kindTitle}</span>
                    {c.description ? <span className="cpd-desc app-muted ac-ellipsis" title={c.description}>{c.description}</span> : <span className="cpd-desc" />}
                    {exists ? <span className="cpd-exists app-muted">{text({ key: libraryTarget ? "copy.pick.exists_library" : "copy.pick.exists" })}</span> : null}
                  </li>
                );
              })}
            </ul>
          )}
        </>
      ) : null}

      {step === "plan" ? (
        <>
          {planState.status === "loading" || planState.status === "idle" ? (
            slow ? (
              <div className="cpd-skeleton" role="status" aria-label={text({ key: "copy.plan.loading" })}>
                {[0, 1, 2, 3].map((n) => <div key={n} className="cpd-skeleton-row" />)}
              </div>
            ) : <span className="ac-sr-only" role="status">{text({ key: "copy.plan.loading" })}</span>
          ) : planState.status === "error" ? (
            <p className="cpd-error" role="alert">
              {text({ key: "copy.plan.failed" })}: {planState.message}{" "}
              <Button size="sm" variant="ghost" onClick={() => runPlan([...picked.values()], includeRefs)}>{text({ key: "copy.plan.retry" })}</Button>
            </p>
          ) : (
            <>
              <div className="cpd-plan-head">
                <span>{text({ key: "copy.plan.counts", params: { requested, referenced: items.length - requested } })}</span>
                <Choice
                  checked={includeRefs}
                  onChange={(e) => {
                    setIncludeRefs(e.target.checked);
                    runPlan(requested === 0 ? [...picked.values()] : items.filter((i) => i.reason === COPY_REASON_REQUESTED), e.target.checked);
                  }}
                >
                  {text({ key: "copy.plan.include_refs" })}
                </Choice>
              </div>
              {includeRefs ? null : <Banner tone="info">{text({ key: "copy.plan.refs_off_note" })}</Banner>}
              {(plan?.warnings ?? []).map((w, n) => <Banner key={`${w.code}:${n}`} tone="warning">{w.message}</Banner>)}
              <ul className="cpd-plan" aria-label={title}>
                {items.map((item) => {
                  const key = copyItemKey(item);
                  const blocked = item.blocked === true;
                  const sel = blocked ? { action: SKIP } : (selections.get(key) ?? { action: defaultActionFor(item) });
                  const allChoices = actionChoicesFor(item);
                  // 막힌 항목은 건너뛰기만 보인다(복사·덮어쓰기·새 이름으로 바꿀 수 없다)
                  const choices = blocked ? allChoices.filter((c) => c.action === SKIP) : allChoices;
                  const blockedReasons = blocked ? (item.issues ?? []).filter((i) => i.severity === "error").map((i) => i.message) : [];
                  const skipped = sel.action === SKIP;
                  const needsChoice = sel.action === null;
                  const taken = takenFor(item);
                  const others = items.flatMap((o) => (o !== item && o.kind === item.kind && selections.get(copyItemKey(o))?.action === RENAME ? [selections.get(copyItemKey(o))?.newId ?? ""] : []));
                  const idProblem = sel.action === RENAME ? validateNewId(sel.newId, [...taken, ...others]) : null;
                  const warn = warnings.find((w) => copyItemKey(w.item) === key);
                  const name = item.name !== undefined && item.name !== "" ? item.name : item.id;
                  return (
                    <li key={key} className="cpd-plan-row" data-invalid={needsChoice ? "true" : undefined} data-skipped={skipped ? "true" : undefined} data-blocked={blocked ? "true" : undefined}>
                      <div className="cpd-plan-main">
                        <input
                          type="checkbox"
                          className="cpd-include"
                          aria-label={text({ key: "copy.plan.include_row", params: { name } })}
                          checked={!skipped}
                          disabled={busy || blocked}
                          onChange={(e) => setSelection(item, e.target.checked ? defaultActionFor(item) : SKIP)}
                        />
                        <div className="cpd-item">
                          <div className="cpd-item-name">
                            <strong className="ac-ellipsis" title={name}>{name}</strong>
                            <span className="prj-kind-chip">{props.candidates.find((c) => c.kind === item.kind)?.kindTitle ?? item.kind}</span>
                          </div>
                          <div className="cpd-item-reason app-muted ac-ellipsis">{reasonText(item)}</div>
                        </div>
                        <span className="cpd-state" data-state={item.target_state}>{text(targetStateLabel(item.target_state))}</span>
                        <select
                          className="ac-input cpd-action"
                          aria-label={`${name}: ${text({ key: "copy.plan.col_action" })}`}
                          aria-invalid={needsChoice ? true : undefined}
                          value={sel.action ?? ""}
                          disabled={busy || blocked}
                          onChange={(e) => setSelection(item, e.target.value === "" ? null : e.target.value)}
                        >
                          {needsChoice ? <option value="">{text({ key: "copy.action.choose" })}</option> : null}
                          {choices.map((c) => <option key={c.action} value={c.action}>{text(c.label)}</option>)}
                        </select>
                      </div>
                      {blocked ? (
                        <div className="cpd-note cpd-danger" role="note">
                          <strong>{text({ key: "copy.plan.blocked" })}</strong>
                          {blockedReasons.map((r, n) => <span key={n}> {r}</span>)}
                        </div>
                      ) : null}
                      {sel.action === OVERWRITE ? (
                        <p className="cpd-note cpd-danger">{text({ key: libraryTarget ? "copy.plan.overwrite_warn_library" : "copy.plan.overwrite_warn" })}</p>
                      ) : null}
                      {sel.action === RENAME ? (
                        <div className="cpd-rename">
                          <label>
                            <span className="app-muted">{text({ key: "copy.plan.new_id" })}</span>
                            <input
                              type="text"
                              className="ac-input"
                              value={sel.newId ?? ""}
                              aria-invalid={idProblem !== null ? true : undefined}
                              onChange={(e) => setNewId(item, e.target.value)}
                            />
                          </label>
                          {idProblem === null ? <span className="cpd-note app-muted">{text({ key: "copy.plan.new_id_help" })}</span> : <span className="cpd-note cpd-danger">{text({ key: `copy.plan.new_id_${idProblem}` })}</span>}
                        </div>
                      ) : null}
                      {skipped && warn !== undefined ? <p className="cpd-note cpd-warning">{text(warn.message)}</p> : null}
                    </li>
                  );
                })}
              </ul>
              {props.removeSourceDefault === undefined ? null : (
                <div>
                  <Choice checked={removeSource} onChange={(e) => setRemoveSource(e.target.checked)}>{text({ key: "copy.plan.remove_source" })}</Choice>
                  <p className="cpd-note app-muted">{text({ key: "copy.plan.remove_source_help" })}</p>
                </div>
              )}
            </>
          )}
        </>
      ) : null}

      {step === "result" ? (
        <>
          <p className="cpd-result-head" role="status">{text({ key: "copy.result.partial", params: { total: resultSummary.total, ok: resultSummary.ok } })}</p>
          <ul className="cpd-plan" aria-label={title}>
            {resultSummary.rows.map((r) => (
              <li key={`${r.kind}:${r.id}`} className="cpd-plan-row" data-result={r.rowKind}>
                <div className="cpd-plan-main">
                  <div className="cpd-item">
                    <div className="cpd-item-name">
                      <strong className="ac-ellipsis" title={r.id}>{planned.get(copyItemKey(r))?.name || r.id}</strong>
                      <span className="prj-kind-chip">{props.candidates.find((c) => c.kind === r.kind)?.kindTitle ?? r.kind}</span>
                    </div>
                  </div>
                  <span className="cpd-result-status" data-kind={r.rowKind}>
                    {r.rowKind === "ok" ? "✓ " : r.rowKind === "skipped" ? "– " : r.rowKind === "conflict" ? "⚠ " : "✕ "}
                    {r.label !== null ? text(r.label) : r.issueMessage ?? text({ key: "copy.result.error_prefix" })}
                  </span>
                  {r.rowKind === "conflict" ? (
                    <Button size="sm" variant="secondary" onClick={() => replan([{ kind: r.kind, id: r.id }])}>{text({ key: "copy.result.replan" })}</Button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      <p className="cpd-independent app-muted">{text({ key: "copy.independent_note" })}</p>
    </div>
  );

  const actions =
    step === "pick" ? (
      <>
        <span className="cpd-foot-info app-muted" role="status">{text({ key: "copy.pick.selected", params: { n: picked.size } })}</span>
        <Button onClick={props.onClose}>{text({ key: "copy.cancel" })}</Button>
        <Button variant="primary" aria-disabled={picked.size === 0 ? "true" : undefined} onClick={() => picked.size > 0 && goPlan()}>{text({ key: "copy.pick.next" })}</Button>
      </>
    ) : step === "plan" ? (
      <>
        <span className="cpd-foot-info" role="status">
          {sums === null ? null : (
            <>
              <span className="app-muted">{text({ key: "copy.summary", params: { copy: sums.copy, reuse: sums.reuse, overwrite: sums.overwrite, rename: sums.rename, skip: sums.skip } })}</span>
              {blockedText !== null && plan !== null ? <span className="cpd-warning"> {blockedText}</span> : null}
            </>
          )}
        </span>
        {props.initialStep === "pick" ? <Button variant="ghost" disabled={busy} onClick={() => { token.current += 1; setStep("pick"); }}>{text({ key: "copy.back" })}</Button> : null}
        <Button disabled={busy} onClick={props.onClose}>{text({ key: "copy.cancel" })}</Button>
        <Button
          variant="primary"
          loading={busy}
          aria-disabled={!submit.allowed ? "true" : undefined}
          title={blockedText ?? undefined}
          onClick={() => void apply()}
        >
          {busy ? text({ key: "copy.submit.busy" }) : text({ key: submitKey, params: { n: sums?.writes ?? 0 } })}
        </Button>
      </>
    ) : (
      <>
        {resultSummary.conflicts > 0 ? (
          <Button variant="secondary" onClick={() => replan(resultSummary.conflictKeys)}>{text({ key: "copy.result.replan_all", params: { n: resultSummary.conflicts } })}</Button>
        ) : null}
        <Button variant="primary" onClick={props.onClose}>{text({ key: "copy.close" })}</Button>
      </>
    );

  return (
    <Dialog open title={title} size="lg" onClose={busy ? () => {} : props.onClose} actions={<div className="cpd-actions">{actions}</div>}>
      {body}
    </Dialog>
  );
}
