import type { ReactNode } from "react";
import type { ArchViewMessages } from "./messages";
import type { ArchFitMode, ArchViewMode } from "./types";

export interface ToolbarParts {
  zoom?: boolean;
  fit?: boolean;
  view?: boolean;
  legend?: boolean;
}

export interface ToolbarProps {
  parts: Required<ToolbarParts>;
  messages: ArchViewMessages;
  scale: number;
  fitMode: ArchFitMode;
  viewMode: ArchViewMode;
  legendOpen: boolean;
  legendId: string;
  onZoom: (factor: number) => void;
  onResetScale: () => void;
  onFitMode: (mode: ArchFitMode) => void;
  onViewMode: (mode: ArchViewMode) => void;
  onToggleLegend: () => void;
  legendButtonRef: React.Ref<HTMLButtonElement>;
  /** 오른쪽에 덧붙일 앱 컨트롤(프로필 선택·크게 보기 등). */
  extra?: ReactNode;
}

/** 도구줄: 확대·축소·배율·맞춤 · [그림|목록] · 범례. 아이콘 버튼은 `aria-label`+`title`. */
export function Toolbar(p: ToolbarProps) {
  const m = p.messages;
  const diagram = p.viewMode === "diagram";
  return (
    <div className="ac-arch-toolbar" role="toolbar" aria-label={m.fit}>
      {p.parts.zoom && diagram ? (
        <>
          <button type="button" className="ac-arch-btn" aria-label={m.zoomOut} title={`${m.zoomOut} (-)`} onClick={() => p.onZoom(1 / 1.25)}>−</button>
          <button type="button" className="ac-arch-btn ac-arch-scale" aria-label={m.scaleReset} title={m.scaleReset} onClick={p.onResetScale}>{`${Math.round(p.scale * 100)}%`}</button>
          <button type="button" className="ac-arch-btn" aria-label={m.zoomIn} title={`${m.zoomIn} (+)`} onClick={() => p.onZoom(1.25)}>+</button>
        </>
      ) : null}
      {p.parts.fit && diagram ? (
        <select className="ac-arch-select" aria-label={m.fit} value={p.fitMode === "none" ? "" : p.fitMode} onChange={(e) => (e.target.value === "100" ? p.onResetScale() : e.target.value ? p.onFitMode(e.target.value as ArchFitMode) : undefined)}>
          {p.fitMode === "none" ? <option value="" disabled>{m.fit}</option> : null}
          <option value="width">{m.fitWidth}</option>
          <option value="contain">{m.fitContain}</option>
          <option value="100">{m.fit100}</option>
        </select>
      ) : null}
      {p.parts.view ? (
        <div className="ac-arch-seg" role="group" aria-label={m.viewGroup}>
          <button type="button" className="ac-arch-btn" aria-pressed={diagram} onClick={() => p.onViewMode("diagram")}>{m.viewDiagram}</button>
          <button type="button" className="ac-arch-btn" aria-pressed={!diagram} onClick={() => p.onViewMode("list")}>{m.viewList}</button>
        </div>
      ) : null}
      {p.extra}
      {p.parts.legend ? (
        <button ref={p.legendButtonRef} type="button" className="ac-arch-btn ac-arch-legend-btn" aria-expanded={p.legendOpen} aria-controls={p.legendId} title={m.legend} onClick={p.onToggleLegend}>
          {m.legend}
        </button>
      ) : null}
    </div>
  );
}
