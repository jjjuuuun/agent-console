import { useId } from "react";
import type { ExportFile, ExportRootInfo } from "@agent-console/contracts";
import { Spinner } from "@agent-console/ui";
import type { ConflictPolicy, SubdirProblem } from "./exportLogic";
import { CONFLICT_POLICIES } from "./exportLogic";
import { exportMessages as t } from "./messages";

export interface DestinationStepProps {
  destination: "archive" | "folder";
  onDestination: (d: "archive" | "folder") => void;
  /** 비어 있으면 폴더 쓰기 선택지를 그리지 않는다 */
  roots: readonly ExportRootInfo[];
  rootId: string;
  onRoot: (id: string) => void;
  subdir: string;
  onSubdir: (s: string) => void;
  subdirProblem: SubdirProblem | undefined;
  subdirServerError: string | undefined;
  onConflict: ConflictPolicy;
  onOnConflict: (p: ConflictPolicy) => void;
  /** 폴더 기준으로 다시 계산한 미리보기 파일(충돌 개수 표시용) */
  planFiles: readonly ExportFile[] | undefined;
  planFetching: boolean;
  busy: boolean;
  error: { message: string; conflictPaths: string[] } | null;
}

/** ④ 내보낼 곳: 보관 파일(항상) / 폴더에 쓰기(루트가 있을 때만). 기본 충돌 처리는 `fail`. */
export function DestinationStep(p: DestinationStepProps) {
  const base = useId();
  const root = p.roots.find((r) => r.id === p.rootId);
  const conflicts = (p.planFiles ?? []).filter((f) => f.action === "conflict");
  return (
    <fieldset className="exp-dest" disabled={p.busy}>
      <legend className="ac-sr-only">{t.dest.group}</legend>
      <label className="exp-radio">
        <input type="radio" name={`${base}-dest`} checked={p.destination === "archive"} onChange={() => p.onDestination("archive")} />
        <span>
          <strong>{t.dest.archive}</strong>
          <span className="app-muted exp-note"> {t.dest.archiveHint}</span>
        </span>
      </label>
      {p.roots.length > 0 ? (
        <>
          <label className="exp-radio">
            <input type="radio" name={`${base}-dest`} checked={p.destination === "folder"} onChange={() => p.onDestination("folder")} />
            <strong>{t.dest.folder}</strong>
          </label>
          {p.destination === "folder" ? (
            <div className="exp-folder">
              <div className="exp-field">
                <label htmlFor={`${base}-root`}>{t.dest.root}</label>
                {p.roots.length === 1 ? (
                  <span id={`${base}-root`} className="exp-fixed">{root?.label || root?.id}</span>
                ) : (
                  <select id={`${base}-root`} className="ac-input" value={p.rootId} onChange={(e) => p.onRoot(e.target.value)}>
                    {p.roots.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.label || r.id}
                      </option>
                    ))}
                  </select>
                )}
                {root?.path ? (
                  <span className="lib-mono app-muted app-wrap" aria-label={t.dest.rootPath}>
                    {root.path}
                  </span>
                ) : null}
              </div>
              <div className="exp-field">
                <label htmlFor={`${base}-subdir`}>{t.dest.subdir}</label>
                <input
                  id={`${base}-subdir`}
                  className="ac-input lib-mono"
                  value={p.subdir}
                  aria-invalid={p.subdirProblem !== undefined || p.subdirServerError !== undefined}
                  aria-describedby={`${base}-subdir-msg`}
                  onChange={(e) => p.onSubdir(e.target.value)}
                />
                <span id={`${base}-subdir-msg`} className={p.subdirProblem !== undefined || p.subdirServerError !== undefined ? "exp-field-error app-wrap" : "app-muted exp-note"}>
                  {p.subdirProblem !== undefined ? t.dest.problems[p.subdirProblem] : (p.subdirServerError ?? t.dest.subdirHint)}
                </span>
              </div>
              <div role="radiogroup" aria-label={t.dest.onConflict} className="exp-conflict">
                <span>{t.dest.onConflict}</span>
                {CONFLICT_POLICIES.map((policy) => (
                  <label key={policy} className="exp-radio">
                    <input type="radio" name={`${base}-conflict`} checked={p.onConflict === policy} onChange={() => p.onOnConflict(policy)} />
                    <span>
                      <strong>{t.dest.conflictOptions[policy]?.title}</strong>
                      <span className="app-muted exp-note"> {t.dest.conflictOptions[policy]?.hint}</span>
                    </span>
                  </label>
                ))}
              </div>
              <p className="app-muted exp-note" role="status">
                {p.planFetching ? <Spinner label={t.preview.refreshing} /> : null}
                {p.planFiles !== undefined ? t.dest.conflictsNow(conflicts.length) : null}
              </p>
              {conflicts.length > 0 ? (
                <ul className="exp-conflict-list lib-mono" aria-label={t.dest.conflictPaths}>
                  {conflicts.map((f) => (
                    <li key={f.path}>{f.path}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </>
      ) : null}
      {p.busy ? (
        <p role="status" className="app-muted">
          <Spinner label={t.dest.exporting} /> {t.dest.exporting}
        </p>
      ) : null}
      {p.error !== null ? (
        <div role="alert" className="exp-error">
          <p className="app-wrap">{p.error.message}</p>
          {p.error.conflictPaths.length > 0 ? (
            <>
              <p>{t.dest.conflictFailed}</p>
              <ul className="lib-mono" aria-label={t.dest.conflictPaths}>
                {p.error.conflictPaths.map((path) => (
                  <li key={path}>{path}</li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      ) : null}
    </fieldset>
  );
}
