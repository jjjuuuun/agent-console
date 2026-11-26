/**
 * 연결선 라벨 겹침 풀기. 같은 노드에서 갈라지는 연결선들은 앞 구간을 함께 쓰므로 기본 위치(경로 한가운데)의 라벨이 서로 겹친다.
 * 사용자가 위치를 정하지 않은(고정이 아닌) 라벨만 경로를 따라 옮겨 겹치지 않는 자리를 찾는다. 저장 데이터는 바꾸지 않는 화면 전용 값이다.
 */
import type { PathPointAt } from "../shapes/types";

/** 라벨 크기를 재지 못했을 때 쓰는 크기(px, 쌓인 칩 기준 넉넉하게). 재었으면 그 크기를 쓴다. */
export const LABEL_BOX = { width: 140, height: 56 } as const;
/** 라벨 사이에 남길 틈(흐름 px). `LabelSpacing`을 주지 않는 호출(단독 사용)의 기본값이다. 편집기는 화면 px 기준 `LABEL_SPACING_DEFAULTS`를 쓴다. */
export const LABEL_GAP = 6;

/**
 * 라벨 배치 간격 설정(모두 선택). 길이는 따로 적지 않으면 "화면 px"이고 줌으로 흐름 px로 바꿔 쓴다.
 * 자리가 모자라면 간격 `gap`→`minGap`, 노드 본문 가림 0→`nodeTolerance`, 칩 접기(아이콘·`+N`, `fold`), 포트 가림 허용 순으로 양보한다(라벨끼리 겹침 0은 양보하지 않는다).
 */
export interface LabelSpacing {
  /** 라벨 사이 목표 간격(화면 px). 기본 8 */
  gap?: number | undefined;
  /** 자리가 모자랄 때 허용하는 최소 간격(화면 px). 기본 4 */
  minGap?: number | undefined;
  /** 자리가 모자랄 때 라벨이 노드 본문 안으로 들어가도 봐주는 깊이(흐름 px). 기본 8, 0이면 봐주지 않는다 */
  nodeTolerance?: number | undefined;
  /** 포트 원 바깥에 더 비워 두는 여백(흐름 px). 기본 4 */
  portClearance?: number | undefined;
  /** 화면 px → 흐름 px 변환에 쓰는 줌의 하한. 기본 0.5 */
  minZoom?: number | undefined;
  /** 같은 줌의 상한. 기본 1 */
  maxZoom?: number | undefined;
  /** 줌 조작이 끝난 뒤 다시 풀기까지 기다리는 시간(ms). 기본 200 */
  settleMs?: number | undefined;
  /** 간격·봐주기로도 자리가 모자랄 때 칩을 아이콘·`+N`으로 접어 자리를 줄이는가. 기본 true */
  fold?: boolean | undefined;
  /** 접은 칩의 크기를 아직 재지 못했을 때 쓰는 폭(흐름 px). 접어 본 칩은 잰 크기를 쓴다. 기본 44 */
  foldedWidth?: number | undefined;
  /** 같은 높이(흐름 px). 기본 26 */
  foldedHeight?: number | undefined;
}

/** `Required<LabelSpacing>`에서 숫자 값만 뽑은 키. */
type NumericKey = Exclude<keyof Required<LabelSpacing>, "fold">;
/** 해석된 간격 설정. */
export type ResolvedLabelSpacing = Required<Omit<LabelSpacing, "fold">> & { fold: boolean };

/** `LabelSpacing`의 기본값(목표 수치). */
export const LABEL_SPACING_DEFAULTS = { gap: 8, minGap: 4, nodeTolerance: 8, portClearance: 4, minZoom: 0.5, maxZoom: 1, settleMs: 200, fold: true, foldedWidth: 44, foldedHeight: 26 } as const satisfies Required<LabelSpacing>;

/** 빠진 값을 기본값으로 채운다(음수·NaN은 기본값). */
export function resolveLabelSpacing(s: LabelSpacing | undefined): ResolvedLabelSpacing {
  const pick = (k: NumericKey): number => {
    const v = s?.[k];
    return typeof v === "number" && Number.isFinite(v) && v >= 0 ? v : LABEL_SPACING_DEFAULTS[k];
  };
  const minZoom = Math.max(0.01, pick("minZoom"));
  const gap = pick("gap");
  return { gap, minGap: Math.min(gap, pick("minGap")), nodeTolerance: pick("nodeTolerance"), portClearance: pick("portClearance"), minZoom, maxZoom: Math.max(minZoom, pick("maxZoom")), settleMs: pick("settleMs"), fold: s?.fold ?? LABEL_SPACING_DEFAULTS.fold, foldedWidth: pick("foldedWidth"), foldedHeight: pick("foldedHeight") };
}

/** 화면 px 간격을 줌으로 나눠 흐름 px로 바꾼다(줌은 [minZoom, maxZoom]로 자른다). */
export function flowGap(screenPx: number, zoom: number, s: Pick<ResolvedLabelSpacing, "minZoom" | "maxZoom">): number {
  const z = Math.min(s.maxZoom, Math.max(s.minZoom, Number.isFinite(zoom) && zoom > 0 ? zoom : 1));
  return screenPx / z;
}
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
  /** 접을 수 있는 라벨인가(아이콘·`+N`으로 줄일 칩이 있는가). 기본 false. 사용자가 위치를 정한 라벨은 접지 않는다 */
  foldable?: boolean | undefined;
  /** 접었을 때의 잰 크기(px). 없으면 `LabelSpacing.foldedWidth`·`foldedHeight` */
  foldedSize?: { width: number; height: number } | undefined;
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
  /** true면 포트처럼 우선 보호하는 사각형(노드 본문 봐주기 단계에서도 줄이지 않는다). 기본 false = 노드 본문 */
  protect?: boolean | undefined;
}

const coversRect = (a: Box, r: ObstacleRect): boolean =>
  Math.abs(a.x - (r.x + r.width / 2)) < (a.width + r.width) / 2 && Math.abs(a.y - (r.y + r.height / 2)) < (a.height + r.height) / 2;

const overlaps = (a: Box, b: Box, gap: number): boolean =>
  Math.abs(a.x - b.x) < (a.width + b.width) / 2 + gap && Math.abs(a.y - b.y) < (a.height + b.height) / 2 + gap;

/** 단독 호출(`LabelSpacing` 없음)에서 노드를 덮어도 봐주는 깊이(흐름 px). 편집기는 `LabelSpacing.nodeTolerance`(기본 8)를 쓴다. */
export const LABEL_NODE_TOLERANCE = 24;

const shrink = (r: ObstacleRect, by: number): ObstacleRect => ({ ...r, x: r.x + by, y: r.y + by, width: Math.max(0, r.width - 2 * by), height: Math.max(0, r.height - 2 * by) });

/** 되짚기 탐색이 시도할 최대 후보 수(라벨이 아주 많을 때 멈추지 않게). 넘으면 이 장애물 세트는 실패로 본다. */
const SEARCH_BUDGET = 4000;

/**
 * 장애물 한 세트로 자리를 잡는다. 입력 순서대로 앞 후보(0.5에 가까운 것)부터 시도하되, 뒤 라벨이 자리를 못 찾으면 앞 라벨을 다른 후보로 물려 다시 찾는다(되짚기).
 * 모든 라벨이 겹치지 않는 자리를 찾으면 `ok`.
 */
function place(
  inputs: readonly SpreadInput[],
  box: { width: number; height: number },
  obstacles: readonly ObstacleRect[],
  gap: number,
  fold: { width: number; height: number } | null,
): { out: Map<string, number>; folded: Set<string>; ok: boolean } {
  const placed: Box[] = [];
  for (const i of inputs) {
    if (i.fixed === undefined || i.visible === false) continue;
    const p = i.labelAt(i.fixed.t);
    placed.push({ x: p.x + (i.fixed.offset?.x ?? 0), y: p.y + (i.fixed.offset?.y ?? 0), ...(i.size ?? box) });
  }
  const movable = inputs.filter((i) => i.fixed === undefined && i.visible !== false);
  const chosen: number[] = [];
  const foldedAt: boolean[] = [];
  let budget = SEARCH_BUDGET;
  const dfs = (k: number): boolean => {
    const i = movable[k];
    if (i === undefined) return true;
    // 접지 않은 크기로 모든 자리를 먼저 시도하고, 안 되면 접은 크기로 시도한다
    const forms: { size: { width: number; height: number }; folded: boolean }[] = [{ size: i.size ?? box, folded: false }];
    if (fold !== null && i.foldable === true) forms.push({ size: i.foldedSize ?? fold, folded: true });
    for (const f of forms) {
      for (const t of LABEL_T_CANDIDATES) {
        if (budget-- <= 0) return false;
        const at: Box = { ...i.labelAt(t), ...f.size };
        if (placed.some((b) => overlaps(b, at, gap)) || obstacles.some((r) => coversRect(at, r))) continue;
        placed.push(at);
        chosen[k] = t;
        foldedAt[k] = f.folded;
        if (dfs(k + 1)) return true;
        placed.pop();
      }
    }
    return false;
  };
  const ok = dfs(0);
  const out = new Map<string, number>();
  const folded = new Set<string>();
  if (ok) {
    movable.forEach((i, k) => {
      if (chosen[k] !== 0.5) out.set(i.id, chosen[k] ?? 0.5);
      if (foldedAt[k] === true) folded.add(i.id);
    });
  }
  return { out, folded, ok };
}

/**
 * 고정이 아닌 보이는 라벨마다 겹치지 않는 경로 비율을 돌려준다(입력 순서대로 자리를 잡는다).
 * 겹치지 않는 라벨은 결과에 넣지 않는다(기본 위치 유지). 빈 자리가 없으면 기본 위치를 유지한다.
 * 라벨끼리 겹치지 않는 것이 가장 우선이다. 자리가 모자라면 다음 순서로 양보한다:
 * 간격 `gap`→`minGap` → 노드 본문 가림 0→`nodeTolerance` → 칩 접기(`foldable` 라벨을 아이콘·`+N` 크기로) → 본문 더 덮기(포트는 지킴) → 포트 가림 허용(`protect` 사각형 무시) → 노드도 무시.
 * 접기는 `spreadLabelLayout`이 알려 준다(`spreadLabels`는 위치만 돌려준다).
 * 앞 라벨이 자리를 차지해 뒤 라벨이 못 찾는 경우를 막으려고 되짚으며 찾는다.
 *
 * @param inputs 연결선들(라우터 결과의 `path.labelAt` 등)
 * @param box 크기를 재지 못한 라벨의 크기
 * @param obstacles 라벨이 덮지 않았으면 하는 사각형들(노드·포트, 좌상단 기준, 흐름 좌표)
 * @param spacing 간격 설정. 생략하면 옛 동작(흐름 px 간격 `LABEL_GAP`, 노드 봐주기 `LABEL_NODE_TOLERANCE`, 포트 구분 없음)
 * @param zoom 지금 줌(`spacing`이 있을 때 화면 px 간격을 흐름 px로 바꾸는 데 쓴다. 기본 1)
 * @returns 연결선 id → 비율 t
 */
export function spreadLabels(
  inputs: readonly SpreadInput[],
  box: { width: number; height: number } = LABEL_BOX,
  obstacles: readonly ObstacleRect[] = [],
  spacing?: LabelSpacing,
  zoom = 1,
): Map<string, number> {
  return spreadLabelLayout(inputs, box, obstacles, spacing, zoom).positions;
}

/** `spreadLabelLayout`의 결과. */
export interface LabelLayout {
  /** 연결선 id → 경로 비율 t(기본 위치 0.5인 라벨은 없다) */
  positions: Map<string, number>;
  /** 접어서 자리를 잡은 라벨의 연결선 id */
  folded: Set<string>;
}

/** `spreadLabels`와 같되 접은 라벨 목록도 돌려준다. */
export function spreadLabelLayout(
  inputs: readonly SpreadInput[],
  box: { width: number; height: number } = LABEL_BOX,
  obstacles: readonly ObstacleRect[] = [],
  spacing?: LabelSpacing,
  zoom = 1,
): LabelLayout {
  type Try = { gap: number; set: readonly ObstacleRect[]; fold?: boolean };
  let fold: { width: number; height: number } | null = null;
  let tries: Try[];
  if (spacing === undefined) {
    const g = LABEL_GAP;
    tries = obstacles.length === 0 ? [{ gap: g, set: [] }] : [{ gap: g, set: obstacles }, { gap: g, set: obstacles.map((r) => shrink(r, LABEL_NODE_TOLERANCE)) }, { gap: g, set: [] }];
  } else {
    const sp = resolveLabelSpacing(spacing);
    if (sp.fold) fold = { width: sp.foldedWidth, height: sp.foldedHeight };
    const gapA = flowGap(sp.gap, zoom, sp);
    const gapB = flowGap(sp.minGap, zoom, sp);
    const ports = obstacles.filter((r) => r.protect === true);
    const nodes = obstacles.filter((r) => r.protect !== true);
    const tolerant = [...nodes.map((r) => shrink(r, sp.nodeTolerance)), ...ports];
    tries = [{ gap: gapA, set: obstacles }];
    if (gapB < gapA) tries.push({ gap: gapB, set: obstacles });
    if (sp.nodeTolerance > 0) tries.push({ gap: gapB, set: tolerant });
    // 봐주기로도 안 되면 칩을 접는다(본문 깊이는 지킨다). 그래도 안 되면 노드 본문을 더 덮어서라도 포트는 지키고(포트가 본문보다 우선), 그래도 안 되면 포트를 덮고, 마지막에 장애물을 모두 무시한다. 이 단계들도 접기를 쓴다
    if (fold !== null) tries.push({ gap: gapB, set: tolerant, fold: true });
    const rest: Try[] = [{ gap: gapB, set: ports }, { gap: gapB, set: nodes.map((r) => shrink(r, sp.nodeTolerance)) }, { gap: gapB, set: [] }];
    tries.push(...rest.map((t) => (fold !== null ? { ...t, fold: true } : t)));
    if (obstacles.length === 0) tries = [{ gap: gapA, set: [] }, ...(gapB < gapA ? [{ gap: gapB, set: [] }] : []), ...(fold !== null ? [{ gap: gapB, set: [], fold: true }] : [])];
  }
  for (const t of tries) {
    const r = place(inputs, box, t.set, t.gap, t.fold === true ? fold : null);
    if (r.ok) return { positions: r.out, folded: r.folded };
  }
  return { positions: greedy(inputs, box, tries[tries.length - 1]?.gap ?? LABEL_GAP), folded: new Set() };
}

/** 되짚기로도 자리를 못 찾았을 때(라벨이 너무 많거나 자리가 없음): 앞에서부터 겹치지 않는 첫 후보를 고르고, 없으면 기본 위치를 둔다. */
function greedy(inputs: readonly SpreadInput[], box: { width: number; height: number }, gap: number): Map<string, number> {
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
    const t = LABEL_T_CANDIDATES.find((c) => !placed.some((b) => overlaps(b, at(c), gap))) ?? 0.5;
    placed.push(at(t));
    if (t !== 0.5) out.set(i.id, t);
  }
  return out;
}

/** 노드 한 개의 포트(핸들) 상자 정보. 좌표는 노드 좌상단 기준 흐름 좌표다. */
export interface PortBox {
  id?: string | null | undefined;
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * 포트 원 + 바깥 여백을 라벨이 피할 장애물(`protect`)로 만든다.
 * @param nodes 노드 절대 위치와 포트 상자들
 * @param clearance 포트 바깥 여백(흐름 px)
 * @param skip 제외할 포트(예: 가장자리 띠 핸들)
 */
export function portObstacles(
  nodes: Iterable<{ x: number; y: number; ports: readonly PortBox[] }>,
  clearance: number,
  skip?: (p: PortBox) => boolean,
): ObstacleRect[] {
  const out: ObstacleRect[] = [];
  for (const n of nodes) {
    for (const p of n.ports) {
      if (skip?.(p) === true) continue;
      out.push({ x: n.x + p.x - clearance, y: n.y + p.y - clearance, width: p.width + 2 * clearance, height: p.height + 2 * clearance, protect: true });
    }
  }
  return out;
}
