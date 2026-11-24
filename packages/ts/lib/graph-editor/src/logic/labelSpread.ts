/**
 * 연결선 라벨 겹침 풀기. 같은 노드에서 갈라지는 연결선들은 앞 구간을 함께 쓰므로 기본 위치(경로 한가운데)의 라벨이 서로 겹친다.
 * 사용자가 위치를 정하지 않은(고정이 아닌) 라벨만 경로를 따라 옮겨 겹치지 않는 자리를 찾는다. 저장 데이터는 바꾸지 않는 화면 전용 값이다.
 */
import type { PathPointAt } from "../shapes/types";

/** 라벨 크기를 재지 못했을 때 쓰는 크기(px, 쌓인 칩 기준 넉넉하게). 재었으면 그 크기를 쓴다. */
export const LABEL_BOX = { width: 140, height: 56 } as const;
/** 라벨 사이에 남길 틈(px). */
export const LABEL_GAP = 6;
/** 기본 위치(0.5) 다음으로 시도할 경로 비율: 0.5에서 가까운 것부터 0.04 간격으로 양쪽 번갈아(0.06~0.94). */
export const LABEL_T_CANDIDATES: readonly number[] = (() => {
  const out = [0.5];
  for (let k = 1; k <= 11; k++) out.push(Math.round((0.5 + 0.04 * k) * 100) / 100, Math.round((0.5 - 0.04 * k) * 100) / 100);
  return out;
})();

export interface SpreadInput {
  id: string;
  /** 경로 위 비율 t의 점. */
  labelAt: (t: number) => Pick<PathPointAt, "x" | "y">;
  /** 사용자가 위치를 정했거나(label_t·오프셋) 화면에 보이지 않아 옮기지 않는 라벨. `t`는 지금 자리. */
  fixed?: { t: number; offset?: { x: number; y: number } | undefined } | undefined;
  /** 화면에 보이는 라벨인가(보이지 않는 라벨은 겹침 계산에서 뺀다). 기본 true. */
  visible?: boolean | undefined;
  /** 잰 라벨 크기(px). 없으면 `box`(기본 `LABEL_BOX`). */
  size?: { width: number; height: number } | undefined;
}

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** 라벨이 피할 사각형(좌상단 x·y와 크기). */
export interface ObstacleRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

const coversRect = (a: Box, r: ObstacleRect): boolean =>
  Math.abs(a.x - (r.x + r.width / 2)) < (a.width + r.width) / 2 && Math.abs(a.y - (r.y + r.height / 2)) < (a.height + r.height) / 2;

const overlaps = (a: Box, b: Box): boolean =>
  Math.abs(a.x - b.x) < (a.width + b.width) / 2 + LABEL_GAP && Math.abs(a.y - b.y) < (a.height + b.height) / 2 + LABEL_GAP;

/** 노드를 덮어도 봐주는 정도(px): 라벨 가장자리가 노드 안으로 이만큼까지 들어가는 것은 허용한다(좁은 틈에서 라벨끼리 겹치지 않게 하려는 타협). */
export const LABEL_NODE_TOLERANCE = 24;

const shrink = (r: ObstacleRect, by: number): ObstacleRect => ({ x: r.x + by, y: r.y + by, width: Math.max(0, r.width - 2 * by), height: Math.max(0, r.height - 2 * by) });

/** 되짚기 탐색이 시도할 최대 후보 수(라벨이 아주 많을 때 멈추지 않게). 넘으면 이 장애물 세트는 실패로 본다. */
const SEARCH_BUDGET = 4000;

/**
 * 장애물 한 세트로 자리를 잡는다. 입력 순서대로 앞 후보(0.5에 가까운 것)부터 시도하되, 뒤 라벨이 자리를 못 찾으면 앞 라벨을 다른 후보로 물려 다시 찾는다(되짚기).
 * 모든 라벨이 겹치지 않는 자리를 찾으면 `ok`.
 */
function place(inputs: readonly SpreadInput[], box: { width: number; height: number }, obstacles: readonly ObstacleRect[]): { out: Map<string, number>; ok: boolean } {
  const placed: Box[] = [];
  for (const i of inputs) {
    if (i.fixed === undefined || i.visible === false) continue;
    const p = i.labelAt(i.fixed.t);
    placed.push({ x: p.x + (i.fixed.offset?.x ?? 0), y: p.y + (i.fixed.offset?.y ?? 0), ...(i.size ?? box) });
  }
  const movable = inputs.filter((i) => i.fixed === undefined && i.visible !== false);
  const chosen: number[] = [];
  let budget = SEARCH_BUDGET;
  const dfs = (k: number): boolean => {
    const i = movable[k];
    if (i === undefined) return true;
    const size = i.size ?? box;
    for (const t of LABEL_T_CANDIDATES) {
      if (budget-- <= 0) return false;
      const at: Box = { ...i.labelAt(t), ...size };
      if (placed.some((b) => overlaps(b, at)) || obstacles.some((r) => coversRect(at, r))) continue;
      placed.push(at);
      chosen[k] = t;
      if (dfs(k + 1)) return true;
      placed.pop();
    }
    return false;
  };
  const ok = dfs(0);
  const out = new Map<string, number>();
  if (ok) movable.forEach((i, k) => { if (chosen[k] !== 0.5) out.set(i.id, chosen[k] ?? 0.5); });
  return { out, ok };
}

/**
 * 고정이 아닌 보이는 라벨마다 겹치지 않는 경로 비율을 돌려준다(입력 순서대로 자리를 잡는다).
 * 겹치지 않는 라벨은 결과에 넣지 않는다(기본 위치 유지). 빈 자리가 없으면 기본 위치를 유지한다.
 * 라벨끼리 겹치지 않는 것이 노드를 덮지 않는 것보다 우선이다: 장애물을 다 피해서는 자리가 모자라면 장애물을 `LABEL_NODE_TOLERANCE`만큼 봐주고,
 * 그래도 모자라면 장애물을 무시한다. 앞 라벨이 자리를 차지해 뒤 라벨이 못 찾는 경우를 막으려고 되짚으며 찾는다.
 *
 * @param inputs 연결선들(라우터 결과의 `path.labelAt` 등)
 * @param box 크기를 재지 못한 라벨의 크기
 * @param obstacles 라벨이 덮지 않았으면 하는 사각형들(노드 등, 좌상단 기준)
 * @returns 연결선 id → 비율 t
 */
export function spreadLabels(
  inputs: readonly SpreadInput[],
  box: { width: number; height: number } = LABEL_BOX,
  obstacles: readonly ObstacleRect[] = [],
): Map<string, number> {
  const tries: (readonly ObstacleRect[])[] = obstacles.length === 0 ? [[]] : [obstacles, obstacles.map((r) => shrink(r, LABEL_NODE_TOLERANCE)), []];
  for (const set of tries) {
    const r = place(inputs, box, set);
    if (r.ok) return r.out;
  }
  return greedy(inputs, box);
}

/** 되짚기로도 자리를 못 찾았을 때(라벨이 너무 많거나 자리가 없음): 앞에서부터 겹치지 않는 첫 후보를 고르고, 없으면 기본 위치를 둔다. */
function greedy(inputs: readonly SpreadInput[], box: { width: number; height: number }): Map<string, number> {
  const out = new Map<string, number>();
  const placed: Box[] = [];
  for (const i of inputs) {
    if (i.fixed === undefined || i.visible === false) continue;
    const p = i.labelAt(i.fixed.t);
    placed.push({ x: p.x + (i.fixed.offset?.x ?? 0), y: p.y + (i.fixed.offset?.y ?? 0), ...(i.size ?? box) });
  }
  for (const i of inputs) {
    if (i.fixed !== undefined || i.visible === false) continue;
    const size = i.size ?? box;
    const at = (t: number): Box => ({ ...i.labelAt(t), ...size });
    const t = LABEL_T_CANDIDATES.find((c) => !placed.some((b) => overlaps(b, at(c)))) ?? 0.5;
    placed.push(at(t));
    if (t !== 0.5) out.set(i.id, t);
  }
  return out;
}
