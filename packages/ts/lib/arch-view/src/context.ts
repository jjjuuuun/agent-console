import { createContext, useContext } from "react";
import type { ArchitectureCellView, ArchitectureEdgeView } from "@agent-console/contracts/architecture";
import type { ArchViewMessages } from "./messages";
import type { Highlighted } from "./model";
import type { ArchLevel, ArchSelection, CellRenderer, MetricKindSpec } from "./types";

/** 노드·연결 컴포넌트가 공유하는 읽기 전용 값(React Flow 노드 데이터에는 id만 싣는다). */
export interface DiagramContextValue {
  level: ArchLevel;
  mode: "live" | "layout";
  messages: ArchViewMessages;
  tones: Readonly<Record<string, string>>;
  metricKinds: Readonly<Record<string, MetricKindSpec>>;
  cellRenderers: Readonly<Record<string, CellRenderer>>;
  cells: Readonly<Record<string, ArchitectureCellView>>;
  edges: Readonly<Record<string, ArchitectureEdgeView>>;
  cellLabels: Readonly<Record<string, string>>;
  selection: ArchSelection | null;
  highlight: Highlighted;
  activate: (target: ArchSelection) => void;
  drill: (cellId: string, group?: string | null) => void;
}

export const DiagramContext = createContext<DiagramContextValue | null>(null);

export function useDiagram(): DiagramContextValue {
  const v = useContext(DiagramContext);
  if (!v) throw new Error("ArchitectureDiagram 안에서만 쓸 수 있습니다.");
  return v;
}
