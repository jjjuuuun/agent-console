import type { ReactNode } from "react";
import type {
  ArchitectureCellView,
  ArchitectureEdgeView,
  ArchitectureMembership,
  ArchitectureMetric,
  ArchitectureSelector,
} from "@agent-console/contracts/architecture";
import type { ArchViewMessages } from "./messages";

/** 캔버스 좌표의 점. */
export type Pt = readonly [number, number];
/** 왼쪽 위 기준 사각형(캔버스 좌표). */
export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** 지금 이벤트 표를 걸러 둔 대상. 묶음은 `id` = 칸 id, `group` = 묶음 값(null = 이름 없음). */
export type ArchSelection =
  | { kind: "cell"; id: string; group?: undefined }
  | { kind: "edge"; id: string; group?: undefined }
  | { kind: "group"; id: string; group: string | null }
  | { kind: "unassigned"; id: string; group?: undefined };

export type ArchSelectionKind = ArchSelection["kind"];
/** `auto` = 폭 맞춤이 기본이고 높이가 모자라면 전체 맞춤 또는 잘림 표시(`autoFit`). */
export type ArchFitMode = "auto" | "width" | "contain" | "none";
export type ArchViewMode = "diagram" | "list";
/** `full` = 전체 표시, `summary` = 요약 표시(숫자만). */
export type ArchLevel = "full" | "summary";

/** 연결 style의 선 모양. 값은 토큰 변수 이름(`--ac-…`)만 받는다. */
export interface EdgeStyleSpec {
  stroke: string;
  /** 점선 패턴 토큰 변수(`--ac-edge-pattern-N`). 없으면 실선. */
  dash?: string;
}

/** 지표 이름을 어떻게 적을지. */
export interface MetricKindSpec {
  kind: "times" | "failures" | "tokenCount" | "millis" | "number";
  /** 값이 늘 추정인 지표(수집 상태와 별개로 "추정"을 붙인다). */
  inferred?: boolean;
}

/** 칸 안쪽을 그리는 확장(X24 `cellRenderers`, 칸의 `view` 키로 고른다). 칸 껍데기(버튼·상태 표기)는 컴포넌트가 그린다. */
export interface CellRenderProps {
  cell: ArchitectureCellView;
  level: ArchLevel;
  messages: ArchViewMessages;
  /** 기본 본문(제목·설명·지표 줄). 감싸거나 덧붙일 때 쓴다. */
  defaultBody: ReactNode;
}
export type CellRenderer = (props: CellRenderProps) => ReactNode;

/** 서버가 준 선택 정보의 부분 집합. */
export type { ArchitectureSelector, ArchitectureMetric, ArchitectureMembership, ArchitectureCellView, ArchitectureEdgeView };

/** 이벤트 표를 걸러낼 수 없어 선택하지 못한 이유. */
export type BlockedReason = "not_collected" | "structural";
