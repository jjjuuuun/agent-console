/**
 * 핸들 배치 규칙(graph-edges §3.3). 포트별 면이 정해진 뒤 각 포트의 `offset`(기본 배치가 아닐 때의 위치)을 채운다.
 * 순수 함수이며 React Flow에 의존하지 않는다.
 */
import type { Side } from "../shapes/types";
import type { PortView } from "./ports";

/** 포트 행 높이(px). styles.css `.ac-ge-port-row`와 같다. */
export const PORT_ROW_HEIGHT = 24;
/** 위·아래 면에서 같은 면 핸들 사이 간격(px)과 최소 간격. */
export const EDGE_HANDLE_GAP = 24;
export const EDGE_HANDLE_MIN_GAP = 12;
/** 위·아래 면에서 좌우로 비워 두는 여유(px). */
export const EDGE_HANDLE_MARGIN = 16;
/** 노드 테두리 두께 합(px). 핸들 가로 위치는 안쪽 상자 기준이다. */
const BORDER = 3;

export interface PlaceHandlesInput {
  /** 면(`side`)이 이미 채워진 입력·출력 포트 */
  inputs: readonly PortView[];
  outputs: readonly PortView[];
  /** 노드 폭(px) */
  width: number;
  /** 칩 카드. 좌·우 면은 가장자리 한 점에 모으는 기존 규칙을 유지한다 */
  compact?: boolean;
  /** 기본 면(입력·출력). 이 면에 둔 한 종류만의 핸들은 포트 행 옆(기본 배치)에 남는다 */
  defaultSides?: { in: Side; out: Side };
  /**
   * 포트에 연결된 상대 노드들의 중심 평균(캔버스 좌표). 없으면(연결 없음) 그 포트는 순서를 바꾸지 않는다.
   * 같은 면 핸들을 상대 위치 순서(위·아래 면은 가로, 좌·우 면은 세로)로 늘어놓아 입출력 선이 서로 교차하는 것을 줄인다(§3.3).
   */
  peerOf?: (io: "in" | "out", portId: string) => { x: number; y: number } | undefined;
}

/**
 * 연결 상대가 있는 항목만 `key` 순으로 다시 늘어놓는다. 상대가 없는 항목은 제자리(자리 번호 유지).
 * 값이 같으면 원래 순서를 지킨다(안정 정렬).
 */
export function orderByPeer<T>(items: readonly T[], key: (item: T) => number | undefined): T[] {
  const slots: number[] = [];
  const keyed: { item: T; k: number; at: number }[] = [];
  items.forEach((item, at) => {
    const k = key(item);
    if (k !== undefined) {
      slots.push(at);
      keyed.push({ item, k, at });
    }
  });
  keyed.sort((a, b) => a.k - b.k || a.at - b.at);
  const out = [...items];
  slots.forEach((slot, i) => {
    out[slot] = (keyed[i] as { item: T }).item;
  });
  return out;
}

const isHorizontalEdge = (s: Side): boolean => s === "top" || s === "bottom";

/**
 * 포트마다 `offset`을 채운 사본을 돌려준다(입력은 바꾸지 않는다).
 * - 위·아래 면: 같은 면의 핸들을 가로로 균등 배치(간격 24, 폭 중앙 정렬, 좌우 여유 16 안, 넘치면 간격 축소·최소 12). 순서 = 입력 목록 → 출력 목록.
 * - 좌·우 면: 한 종류(입력만/출력만)이고 `defaultSides`와 같으면 기본 배치(offset 없음). 한 종류인데 반대 열이면 자기 행 중앙.
 *   입력·출력이 섞이면 그 면의 핸들 전체를 포트 영역 안에서 세로 균등 배치(간격 24, 영역보다 많으면 영역을 나눔).
 * - 아무 포트도 기본 배치가 아니면 입력과 같은 객체를 돌려준다(lr 기본 구성은 변화 없음).
 */
export function placeHandles(input: PlaceHandlesInput): { inputs: PortView[]; outputs: PortView[] } {
  const defaults = input.defaultSides ?? { in: "left", out: "right" };
  const all: { io: "in" | "out"; index: number; port: PortView }[] = [
    ...input.inputs.map((port, index) => ({ io: "in" as const, index, port })),
    ...input.outputs.map((port, index) => ({ io: "out" as const, index, port })),
  ];
  const sideOf = (p: PortView, io: "in" | "out"): Side => p.side ?? defaults[io];
  const offsets = new Map<PortView, number>();
  const rows = Math.max(input.inputs.length, input.outputs.length);
  const area = rows * PORT_ROW_HEIGHT;
  const inner = Math.max(0, input.width - BORDER);

  for (const side of ["top", "bottom", "left", "right"] as const) {
    let group = all.filter((a) => sideOf(a.port, a.io) === side);
    if (group.length === 0) continue;
    const peerOf = input.peerOf;
    if (peerOf !== undefined) {
      const axis = isHorizontalEdge(side) ? "x" : "y";
      // 좌·우 면은 입력·출력이 섞여 균등 배치될 때만 순서가 의미 있다(한 종류면 포트 행 순서가 곧 자리)
      if (isHorizontalEdge(side) || new Set(group.map((a) => a.io)).size > 1) group = orderByPeer(group, (a) => peerOf(a.io, a.port.id)?.[axis]);
    }
    if (isHorizontalEdge(side)) {
      const usable = Math.max(0, inner - 2 * EDGE_HANDLE_MARGIN);
      const gap =
        group.length <= 1 ? 0 : Math.max(EDGE_HANDLE_MIN_GAP, Math.min(EDGE_HANDLE_GAP, usable / (group.length - 1)));
      group.forEach((a, k) => offsets.set(a.port, inner / 2 + (k - (group.length - 1) / 2) * gap));
      continue;
    }
    if (input.compact) continue;
    const kinds = new Set(group.map((a) => a.io));
    if (kinds.size === 1) {
      const io = group[0]!.io;
      if (defaults[io] === side) continue; // 기본 배치: 포트 행 옆
      for (const a of group) offsets.set(a.port, a.index * PORT_ROW_HEIGHT + PORT_ROW_HEIGHT / 2);
    } else {
      const step = Math.min(PORT_ROW_HEIGHT, area / group.length);
      group.forEach((a, k) => offsets.set(a.port, (k + 0.5) * step));
    }
  }
  if (offsets.size === 0) return { inputs: input.inputs as PortView[], outputs: input.outputs as PortView[] };
  const apply = (p: PortView): PortView => {
    const o = offsets.get(p);
    return o === undefined ? p : { ...p, offset: o };
  };
  return { inputs: input.inputs.map(apply), outputs: input.outputs.map(apply) };
}
