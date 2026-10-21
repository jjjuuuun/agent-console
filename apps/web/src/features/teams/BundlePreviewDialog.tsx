import { useState } from "react";
import type { BundlePreview, Graph, Issue, ResourceBundle } from "@agent-console/contracts";
import { Button, Dialog, ProvenanceBadge } from "@agent-console/ui";
import { ErrorBlock } from "../../app/ErrorBlock";
import { stringifyValue } from "../../lib/format";
import { Skeleton } from "../settings";
import { libraryMessages as lm, modeLabel } from "../library";
import { DraftNotice } from "./DraftNotice";
import { teamMessages as t } from "./messages";
import { useDraftPreview } from "./useDraftPreview";

const PREVIEW_CHARS = 600;

/** 칸 값 하나를 문자열 조각 목록으로(목록이면 항목별, 아니면 하나). */
export function slotParts(value: unknown): string[] {
  return Array.isArray(value) ? value.map((v) => stringifyValue(v)) : [stringifyValue(value)];
}

function Part({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const long = text.length > PREVIEW_CHARS;
  return (
    <div>
      <pre className="ac-pre app-json">{long && !open ? `${text.slice(0, PREVIEW_CHARS)}…` : text}</pre>
      {long ? (
        <button type="button" className="app-link-btn" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? t.bundle.showLess : t.bundle.showMore}
        </button>
      ) : null}
    </div>
  );
}

/** 칸(slots)별 값 미리보기와 출처 목록. 비밀은 서버가 가려서 준다. 칸·종류 이름은 서버 문자열이다. */
/** 경고 `path`(JSON Pointer)가 칸 키로 시작하면 그 칸의 경고다(데이터 비교, 칸 이름은 모른다). */
export function warningsOfSlot(warnings: readonly Issue[], slot: string): Issue[] {
  return warnings.filter((w) => {
    const path = w.path;
    if (typeof path !== "string") return false;
    const parts = path.split("/").filter((p) => p !== "");
    // 경고 path는 칸 키로 시작한다(번들 문서 기준이면 `slots` 다음 마디)
    const key = parts[0] === "slots" ? parts[1] : parts[0];
    return key === slot;
  });
}

/** 묶음 경고 영역: 서버 메시지·path·code를 그대로 보인다(줄이거나 숨기지 않는다). 경고가 없으면 영역이 없다. */
export function BundleWarnings({ warnings }: { warnings: readonly Issue[] }) {
  if (warnings.length === 0) return null;
  return (
    <section className="team-bundle-warnings" aria-label={t.bundle.warningsRegion}>
      <h3 className="app-block-subtitle">
        <span aria-hidden="true">▲ </span>
        {t.bundle.warningsTitle(warnings.length)}
      </h3>
      <ul>
        {warnings.map((w, i) => (
          <li key={`${i}:${w.code}`} className="app-sev" data-severity={w.severity}>
            <span aria-hidden="true">{w.severity === "error" ? "✕" : w.severity === "warning" ? "▲" : "ℹ"} </span>
            <span className="team-bundle-warning-text">{w.message}</span>
            {typeof w.path === "string" ? <span className="app-muted lib-mono"> {w.path}</span> : null}
            <span className="app-muted lib-mono"> {w.code}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function BundleView({ bundle, warnings = [] }: { bundle: ResourceBundle; warnings?: readonly Issue[] }) {
  const slots = Object.entries(bundle.slots ?? {});
  if (slots.length === 0 && warnings.length === 0) return <p className="app-muted">{t.bundle.empty}</p>;
  return (
    <div className="lib-form">
      <BundleWarnings warnings={warnings} />
      {slots.length === 0 ? <p className="app-muted">{t.bundle.empty}</p> : null}
      <p className="app-muted lib-field-note">{t.bundle.secretMasked}</p>
      {slots.map(([slot, value], index) => (
        <section key={slot} aria-label={`${t.bundle.slot} ${slot}`} className="lib-fieldset">
          <h3 className="app-block-subtitle lib-mono">
            {slot}
            {warningsOfSlot(warnings, slot).length > 0 ? (
              <span className="app-sev team-slot-warn" data-severity="warning"> <span aria-hidden="true">▲</span> {warningsOfSlot(warnings, slot).length}<span className="ac-sr-only"> {t.bundle.slotWarnings(warningsOfSlot(warnings, slot).length)}</span></span>
            ) : null}
          </h3>
          {slotParts(value).map((text, i) => (
            <Part key={i} text={text} />
          ))}
          {(bundle.sources?.[slot] ?? []).length > 0 ? (
            <div>
              <span className="lib-field-label">{t.bundle.sources}</span>
              <ul className="lib-ref-list">
                {(bundle.sources?.[slot] ?? []).map((s, i) => (
                  <li key={`${s.ref}:${i}`}>
                    <span className="lib-mono">{s.ref}</span>{" "}
                    {s.layer ? <ProvenanceBadge layer={{ id: s.layer, label: s.layer, index: index + 1 }} variant="set" /> : null}{" "}
                    {s.mode ? <span className="ac-tag">{modeLabel(s.mode)}</span> : null}{" "}
                    {s.resource_type ? <span className="app-muted">{s.resource_type}</span> : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      ))}
    </div>
  );
}

export interface BundlePreviewDialogProps {
  graphId: string;
  nodeId: string;
  nodeLabel: string;
  /** 저장 전 변경이 있는 팀 구성 초안. 있으면 초안 기준으로 계산한다(저장하지 않음) */
  draft?: Graph | undefined;
  /** 이 노드가 저장된 팀 구성에 있는가(서버가 초안 경로를 모를 때의 폴백 판단) */
  savedNode: boolean;
  onClose: () => void;
}

/** 이 노드가 실행 때 받을 실행 묶음 미리보기와 묶음 경고(`BundlePreview`). 저장본 `GET`, 초안 `POST /graphs/bundle-preview`. */
export function BundlePreviewDialog({ graphId, nodeId, nodeLabel, draft, savedNode, onClose }: BundlePreviewDialogProps) {
  const q = useDraftPreview<BundlePreview, Graph>({
    keyBase: ["bundle-preview", graphId, nodeId],
    draftInput: draft,
    savedEnabled: savedNode,
    loadSaved: (rest) => rest.getNodeBundlePreview(graphId, nodeId),
    loadDraft: (rest, graph) => rest.previewDraftBundle({ graph, node_id: nodeId }),
  });
  const needSave = !q.isDraft && (draft !== undefined || !savedNode);
  return (
    <Dialog open title={`${t.bundle.title}: ${nodeLabel}`} onClose={onClose} wide actions={<><Button onClick={q.refetch} disabled={needSave}>{t.bundle.refresh}</Button><Button variant="primary" onClick={onClose}>{t.bundle.close}</Button></>}>
      <DraftNotice isDraft={q.isDraft} updating={q.updating} error={q.isDraft && q.isError && q.data !== undefined ? q.error : null} onRetry={q.refetch} />
      {needSave ? (
        <p className="app-muted">{t.bundle.saveFirst}</p>
      ) : q.isLoading ? (
        <div role="status"><p className="app-muted">{t.bundle.loading}</p><Skeleton rows={3} /></div>
      ) : q.isError && q.data === undefined ? (
        <ErrorBlock title={t.bundle.failed} message={q.error?.message ?? ""} retryLabel={lm.retry} onRetry={q.refetch} />
      ) : (
        <div style={q.updating ? { opacity: 0.6 } : undefined}>
          <BundleView bundle={q.data?.bundle ?? {}} warnings={q.data?.warnings ?? []} />
        </div>
      )}
    </Dialog>
  );
}
