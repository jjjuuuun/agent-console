import { useEffect, useMemo, useState } from "react";
import type { DefinitionMove, MovePlan, Project } from "@agent-console/contracts/projects";
import { Banner, Button, Dialog, Spinner } from "@agent-console/ui";
import { isRequiredMove, mergeMovePlans, moveKey, selectMoves, type ProjectsClient } from "@agent-console/projects";
import { describeError } from "../../app/errors";
import { projectMessages as t } from "./messages";

/** 옮길 정의 하나(종류 이름은 호출자가 데이터로 준다). */
export interface MoveItem {
  kind: string;
  id: string;
  name?: string;
}

export interface MoveToProjectDialogProps {
  items: readonly MoveItem[];
  projects: readonly Project[];
  /** 처음 고르는 목적지(null = 공용) */
  initialTarget?: string | null;
  client: ProjectsClient;
  onClose: () => void;
  /** 적용이 끝난 뒤(서버가 돌려준 실제 이동과 경고) */
  onApplied: (result: MovePlan) => void;
}

const SHARED = "";

/**
 * "프로젝트로 이동…" 대화상자: 목적지를 고르면 서버가 계산한 옮기기 계획(참조 닫힘, 경고)을 보여 주고,
 * 권하는 연관 항목을 함께 옮길지 고른 뒤 적용한다. 여러 정의를 한 번에 옮길 수 있다.
 * 계산·적용은 `client`(주입)가 한다. 열 때마다 새로 시작하도록 호출자가 `open`일 때만 렌더한다.
 */
export function MoveToProjectDialog({ items, projects, initialTarget = null, client, onClose, onApplied }: MoveToProjectDialogProps) {
  const [target, setTarget] = useState<string>(initialTarget ?? SHARED);
  const [plan, setPlan] = useState<MovePlan | null>(null);
  const [planning, setPlanning] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [include, setInclude] = useState<ReadonlySet<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const itemsKey = items.map((i) => `${i.kind}/${i.id}`).join("|");

  useEffect(() => {
    let cancelled = false;
    const to = target === SHARED ? null : target;
    Promise.all(items.map((i) => client.getMovePlan({ kind: i.kind, id: i.id, to })))
      .then((plans) => {
        if (cancelled) return;
        const merged = mergeMovePlans(plans);
        setPlan(merged);
        // 권하는 연관 항목은 기본으로 함께 옮긴다
        setInclude(new Set((merged?.moves ?? []).filter((m) => !isRequiredMove(m)).map(moveKey)));
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setPlan(null);
          setError(describeError(e, t.move.planFailed).message);
        }
      })
      .finally(() => {
        if (!cancelled) setPlanning(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, target, itemsKey]);

  const moves = useMemo(() => plan?.moves ?? [], [plan]);
  const related = useMemo(() => moves.filter((m) => !isRequiredMove(m)), [moves]);
  const requiredCount = moves.length - related.length;
  const warnings = plan?.warnings ?? [];
  const nothing = !planning && error === null && moves.length === 0;
  const nameOf = (m: DefinitionMove) => m.name ?? m.id;

  const apply = () => {
    if (plan === null) return;
    setBusy(true);
    setError(null);
    client
      .applyMove(selectMoves(plan, include))
      .then((result) => onApplied(result))
      .catch((e: unknown) => setError(describeError(e, t.move.failed).message))
      .finally(() => setBusy(false));
  };
  const itemSummary = items.length === 1 ? (items[0]?.name ?? items[0]?.id ?? "") : t.move.items(items.length);

  return (
    <Dialog
      open
      title={`${t.move.title}: ${itemSummary}`}
      onClose={onClose}
      actions={
        <>
          <Button onClick={onClose}>{t.manage.cancel}</Button>
          <Button variant="primary" loading={busy} disabled={planning || plan === null || nothing} onClick={apply}>{t.move.apply}</Button>
        </>
      }
    >
      <div className="lib-form prj-move">
        {error === null ? null : <Banner tone="danger">{error}</Banner>}
        <div className="lib-field">
          <label htmlFor="prj-move-target">{t.move.target}</label>
          <select id="prj-move-target" className="ac-input" value={target} onChange={(e) => { setTarget(e.target.value); setPlanning(true); setError(null); }} disabled={busy}>
            <option value={SHARED}>{t.move.toShared}</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
        {planning ? <p className="app-muted" role="status"><Spinner /> {t.move.planning}</p> : null}
        {nothing ? <p className="app-muted" role="status">{t.move.noChange}</p> : null}
        {!planning && requiredCount > 0 && items.length > 1 ? <p className="app-muted">{t.move.items(requiredCount)}</p> : null}
        {related.length > 0 ? (
          <fieldset className="prj-related">
            <legend>{t.move.related}</legend>
            <p className="app-muted lib-field-note">{t.move.relatedHint}</p>
            {related.map((m) => {
              const key = moveKey(m);
              return (
                <label key={key} className="prj-check">
                  <input
                    type="checkbox"
                    checked={include.has(key)}
                    onChange={(e) => {
                      const next = new Set(include);
                      if (e.target.checked) next.add(key);
                      else next.delete(key);
                      setInclude(next);
                    }}
                  />
                  <span className="ac-ellipsis">{nameOf(m)}</span>
                  <span className="app-muted ac-mono">{m.kind}</span>
                </label>
              );
            })}
          </fieldset>
        ) : null}
        {warnings.length > 0 ? (
          <Banner tone="warning" title={t.move.warnings}>
            <ul className="lib-issue-list">
              {warnings.map((w, i) => (
                <li key={`${w.code}-${i}`}>{w.message}</li>
              ))}
            </ul>
          </Banner>
        ) : null}
      </div>
    </Dialog>
  );
}
