/**
 * 자동 경로 라우터(graph-edges §4.2). 노드 사각형을 피하는 직각 경로를 격자 위 A*로 찾는 순수 함수 모음이다.
 * React·DOM·React Flow에 의존하지 않는다. 비용·패딩·격자·탐색 상한은 전부 `RouteOptions`로 주입한다.
 *
 * 규칙(기본값):
 * - 노드 사각형을 패딩 16px 부풀린 장애물로 본다. 격자 8px, 직각 이동만.
 * - 비용: 직진 1(격자 한 칸), 꺾임 +4, 이미 계산된 다른 엣지와 교차 +8(엣지 id 순).
 * - 핸들 면 바깥쪽 스텁(16px)은 장애물을 무시하고, 소스·타깃 자기 노드는 스텁 끝부터 장애물이다.
 * - 탐색 상한(확장 20,000회 또는 엣지당 8ms)을 넘으면 경유점 없는 `smoothstep` 경로로 대체하고 `fallback`을 켠다.
 * - 결과는 (장애물 목록, 엣지 입력, 앞선 엣지들의 입력)의 해시로 엣지별 메모한다.
 *
 * 격자선은 8px 배수에 엣지의 시작·끝·경유점 좌표를 더한 것이라 노드가 격자에 맞지 않아도 끝점이 정확히 맞는다.
 */
import { ARROW_GAP, DEFAULT_EDGE_RADIUS, EDGE_STUB, MAX_EDGE_RADIUS, MAX_WAYPOINTS, orthogonalPath, orthogonalPoints, roundedPolylinePath, sideNormal, simplifyPolyline } from "./edgePath";
import { nudgeParallel } from "./nudge";
import type { Point } from "./ops";
import type { EdgeEndpoint, EdgePathInput, EdgePathResult, Side } from "../shapes/types";

/** 장애물로 보는 노드 사각형(캔버스 절대 좌표). */
export interface RouteObstacle {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

/** 경로 비용. */
export interface RouteCosts {
  /** 격자 한 칸 직진 */
  straight: number;
  /** 꺾임 1회 */
  bend: number;
  /** 이미 계산된 다른 엣지와 교차 1회 */
  cross: number;
}

/** 라우터 설정. 모두 생략 가능(기본값은 `DEFAULT_ROUTE_OPTIONS`). */
export interface RouteOptions {
  /** 노드를 부풀리는 여백 px */
  padding?: number;
  /** 격자 간격 px */
  grid?: number;
  costs?: Partial<RouteCosts>;
  /** 엣지당 최대 노드 확장 수 */
  maxExpansions?: number;
  /** 엣지당 최대 계산 시간 ms */
  maxMillis?: number;
  /** 핸들 기준 스텁 길이 px */
  stub?: number;
  /** 핸들에서 면 바깥으로 선을 띄우는 거리 px(`buildEdgePath`와 같은 값) */
  arrowGap?: number;
  /** 엣지별 메모 항목 상한. 넘으면 비운다 */
  cacheLimit?: number;
  /** 같은 줄에서 겹치는 평행 선분을 벌리는 간격 px. 0이면 끈다(겹침 완화 안 함) */
  nudge?: number;
  /** 시계(ms). 시간 상한 테스트용으로 주입한다. 생략 = `performance.now` */
  now?: () => number;
}

export const DEFAULT_ROUTE_COSTS: Readonly<RouteCosts> = { straight: 1, bend: 4, cross: 8 };

export const DEFAULT_ROUTE_OPTIONS = {
  padding: 16,
  grid: 8,
  maxExpansions: 20_000,
  maxMillis: 8,
  stub: EDGE_STUB,
  arrowGap: ARROW_GAP,
  cacheLimit: 2_000,
  nudge: 6,
} as const;

/** 장애물 없는 단독 자동 경로(`autoPath`)의 기본 상한. 장애물이 없어 확장 수 상한이 끝을 보장하므로 시계 상한은 넉넉히 둔다(5.2R.42). */
export const DEFAULT_AUTO_PATH_OPTIONS = { maxMillis: 1000, maxExpansions: DEFAULT_ROUTE_OPTIONS.maxExpansions } as const;

/** 엣지 하나의 경로 요청. 끝점은 핸들 경계 위의 점이다(`buildEdgePath` 입력과 같음). */
export interface RouteEdgeRequest {
  id: string;
  source: EdgeEndpoint;
  target: EdgeEndpoint;
  /** 있으면 그 점을 순서대로 반드시 지난다(최대 16개) */
  waypoints?: readonly Point[] | null;
  /** 소스 노드 id. 있으면 그 노드는 스텁 끝부터 장애물이다 */
  sourceNodeId?: string;
  targetNodeId?: string;
  /** 모서리 반경. 생략 = 8 */
  radius?: number | null;
}

/** 라우터 결과 한 건. */
export interface RoutedEdge {
  id: string;
  path: EdgePathResult;
  /** 직각 꺾은선(양 끝 포함). 폴백이면 폴백 경로의 점 */
  points: readonly Point[];
  /** 탐색 상한 초과 또는 경로 없음으로 `smoothstep`(경유점 없이)로 대체했는가 */
  fallback: boolean;
}

/**
 * 연결선 라우터. 구현을 바꿔 끼울 수 있다(예: 평행선 분리·교차 최소화를 더 잘하는 외부 라우터).
 * 같은 입력이면 같은 결과를 내야 한다.
 */
export interface EdgeRouter {
  readonly id: string;
  /** 엣지를 id 순으로 계산한다. 반환 Map의 순서도 id 순. */
  route(edges: readonly RouteEdgeRequest[], obstacles: readonly RouteObstacle[]): ReadonlyMap<string, RoutedEdge>;
}

/** 메모 통계(테스트·진단용). */
export interface RouterStats {
  hits: number;
  misses: number;
  fallbacks: number;
  /** 새로 계산한 엣지들의 A* 노드 확장 합계 */
  expansions: number;
}

export interface AStarRouter extends EdgeRouter {
  clearCache(): void;
  stats(): Readonly<RouterStats>;
}

/** 폴백 표식. 렌더 쪽에서 `{...routeFallbackAttrs(r)}`로 엣지 요소에 붙인다(시각 표시 없음, 테스트용). */
export const ROUTE_FALLBACK_ATTR = "data-route-fallback" as const;
export const routeFallbackAttrs = (r: Pick<RoutedEdge, "fallback">): { "data-route-fallback"?: "true" } =>
  r.fallback ? { [ROUTE_FALLBACK_ATTR]: "true" } : {};

// ---------------------------------------------------------------------------------------------
// 내부 구현

type Dir = 0 | 1 | 2 | 3; // 오른쪽, 왼쪽, 아래, 위
const SIDE_DIR: Readonly<Record<Side, Dir>> = { right: 0, left: 1, bottom: 2, top: 3 };
const EPS = 1e-6;
const BUCKET = 128;
/** 휴리스틱 가중(1에 아주 가깝게). 같은 f의 넓은 평탄 구간에서 목표 쪽을 먼저 확장해 확장 수를 크게 줄인다. */
const TIE = 1.001;

const clamp = (v: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, v));
const near = (a: number, b: number): boolean => Math.abs(a - b) < EPS;
const finite = (p: Point): boolean => Number.isFinite(p.x) && Number.isFinite(p.y);

/** 53비트 문자열 해시(cyrb53). 메모 키용이며 암호용이 아니다. */
function hash53(str: string, seed = 0): number {
  let h1 = 0xdeadbeef ^ seed;
  let h2 = 0x41c6ce57 ^ seed;
  for (let i = 0; i < str.length; i += 1) {
    const ch = str.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return 4294967296 * (2097151 & h2) + (h1 >>> 0);
}

/** 정렬된 두 배열을 합치고 거의 같은 값은 하나로 줄인다. */
function mergeLines(a: readonly number[], b: readonly number[]): number[] {
  const out: number[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length || j < b.length) {
    const v = j >= b.length || (i < a.length && (a[i] as number) <= (b[j] as number)) ? (a[i++] as number) : (b[j++] as number);
    if (out.length === 0 || v - (out[out.length - 1] as number) > EPS) out.push(v);
  }
  return out;
}

/** 정렬된 배열에서 v와 같은 값의 위치. 없으면 -1. */
function findLine(lines: readonly number[], v: number): number {
  let lo = 0;
  let hi = lines.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const m = lines[mid] as number;
    if (near(m, v)) return mid;
    if (m < v) lo = mid + 1;
    else hi = mid - 1;
  }
  return -1;
}

/** 작은 이진 최소 힙(f 기준). */
class MinHeap {
  private f: number[] = [];
  private v: number[] = [];
  get size(): number {
    return this.f.length;
  }
  push(f: number, v: number): void {
    const F = this.f;
    const V = this.v;
    let i = F.length;
    F.push(f);
    V.push(v);
    while (i > 0) {
      const p = (i - 1) >> 1;
      if ((F[p] as number) <= f) break;
      F[i] = F[p] as number;
      V[i] = V[p] as number;
      i = p;
    }
    F[i] = f;
    V[i] = v;
  }
  pop(): number {
    const F = this.f;
    const V = this.v;
    const top = V[0] as number;
    const lf = F.pop() as number;
    const lv = V.pop() as number;
    const n = F.length;
    if (n > 0) {
      let i = 0;
      for (;;) {
        let c = 2 * i + 1;
        if (c >= n) break;
        if (c + 1 < n && (F[c + 1] as number) < (F[c] as number)) c += 1;
        if ((F[c] as number) >= lf) break;
        F[i] = F[c] as number;
        V[i] = V[c] as number;
        i = c;
      }
      F[i] = lf;
      V[i] = lv;
    }
    return top;
  }
}

interface Resolved {
  padding: number;
  grid: number;
  costs: RouteCosts;
  maxExpansions: number;
  maxMillis: number;
  stub: number;
  arrowGap: number;
  cacheLimit: number;
  nudge: number;
  now: () => number;
}

function resolveOptions(o: RouteOptions): Resolved {
  const d = DEFAULT_ROUTE_OPTIONS;
  const pos = (v: number | undefined, dflt: number): number => (v !== undefined && Number.isFinite(v) && v > 0 ? v : dflt);
  const nonNeg = (v: number | undefined, dflt: number): number => (v !== undefined && Number.isFinite(v) && v >= 0 ? v : dflt);
  return {
    padding: nonNeg(o.padding, d.padding),
    grid: pos(o.grid, d.grid),
    costs: {
      straight: pos(o.costs?.straight, DEFAULT_ROUTE_COSTS.straight),
      bend: nonNeg(o.costs?.bend, DEFAULT_ROUTE_COSTS.bend),
      cross: nonNeg(o.costs?.cross, DEFAULT_ROUTE_COSTS.cross),
    },
    maxExpansions: pos(o.maxExpansions, d.maxExpansions),
    maxMillis: pos(o.maxMillis, d.maxMillis),
    stub: nonNeg(o.stub, d.stub),
    arrowGap: nonNeg(o.arrowGap, d.arrowGap),
    cacheLimit: pos(o.cacheLimit, d.cacheLimit),
    nudge: nonNeg(o.nudge, d.nudge),
    now: o.now ?? (() => performance.now()),
  };
}

/** 장애물 색인: 큰 칸(버킷)마다 겹치는 장애물 목록. */
class ObstacleIndex {
  private readonly buckets = new Map<number, RouteObstacle[]>();
  /** 부풀린 장애물 경계 좌표(정렬·중복 제거) */
  readonly lineX: number[];
  readonly lineY: number[];
  constructor(
    obstacles: readonly RouteObstacle[],
    private readonly padding: number,
  ) {
    const xs = new Set<number>();
    const ys = new Set<number>();
    for (const o of obstacles) {
      xs.add(o.x - padding);
      xs.add(o.x + o.width + padding);
      ys.add(o.y - padding);
      ys.add(o.y + o.height + padding);
    }
    // 가장자리 바깥으로 돌아 들어갈 수 있게 전체 바깥쪽에 한 줄씩 더 둔다.
    for (const set of [xs, ys]) {
      if (set.size === 0) continue;
      set.add(Math.min(...set) - padding);
      set.add(Math.max(...set) + padding);
    }
    this.lineX = [...xs].sort((a, b) => a - b);
    this.lineY = [...ys].sort((a, b) => a - b);
    for (const o of obstacles) {
      const x0 = Math.floor((o.x - padding) / BUCKET);
      const x1 = Math.floor((o.x + o.width + padding) / BUCKET);
      const y0 = Math.floor((o.y - padding) / BUCKET);
      const y1 = Math.floor((o.y + o.height + padding) / BUCKET);
      for (let bx = x0; bx <= x1; bx += 1) {
        for (let by = y0; by <= y1; by += 1) {
          const k = (bx + 32768) * 65536 + (by + 32768);
          const list = this.buckets.get(k);
          if (list) list.push(o);
          else this.buckets.set(k, [o]);
        }
      }
    }
  }
  /**
   * 점이 부풀린 사각형의 안쪽(경계 제외)인가. 소스·타깃 노드(`own`)는 여백이 줄어들 수 있다.
   */
  blocked(x: number, y: number, own: OwnInflation): boolean {
    const list = this.buckets.get((Math.floor(x / BUCKET) + 32768) * 65536 + (Math.floor(y / BUCKET) + 32768));
    if (!list) return false;
    for (let i = 0; i < list.length; i += 1) {
      const o = list[i] as RouteObstacle;
      let inf = this.padding;
      if (o.id === own.srcId && own.srcInf < inf) inf = own.srcInf;
      if (o.id === own.dstId && own.dstInf < inf) inf = own.dstInf;
      if (x > o.x - inf + EPS && x < o.x + o.width + inf - EPS && y > o.y - inf + EPS && y < o.y + o.height + inf - EPS) return true;
    }
    return false;
  }
}

/** 한 엣지의 소스·타깃 노드 id와 줄어든 여백. */
interface OwnInflation {
  srcId: string | undefined;
  srcInf: number;
  dstId: string | undefined;
  dstInf: number;
}

interface Seg {
  /** 고정 좌표(가로 선분이면 y, 세로 선분이면 x) */
  c: number;
  a: number;
  b: number;
}

/** 이미 계산된 엣지의 선분 색인(교차 비용용). 가로·세로 선분을 큰 칸별로 보관한다. */
class Occupancy {
  private readonly h = new Map<number, Seg[]>();
  private readonly v = new Map<number, Seg[]>();
  private static key(bx: number, by: number): number {
    return (bx + 32768) * 65536 + (by + 32768);
  }
  add(points: readonly Point[]): void {
    for (let i = 1; i < points.length; i += 1) {
      const p = points[i - 1] as Point;
      const q = points[i] as Point;
      if (near(p.y, q.y)) this.insert(this.h, { c: p.y, a: Math.min(p.x, q.x), b: Math.max(p.x, q.x) }, true);
      else if (near(p.x, q.x)) this.insert(this.v, { c: p.x, a: Math.min(p.y, q.y), b: Math.max(p.y, q.y) }, false);
    }
  }
  private insert(map: Map<number, Seg[]>, seg: Seg, horizontal: boolean): void {
    const cb = Math.floor(seg.c / BUCKET);
    for (let k = Math.floor(seg.a / BUCKET); k <= Math.floor(seg.b / BUCKET); k += 1) {
      const key = horizontal ? Occupancy.key(k, cb) : Occupancy.key(cb, k);
      const list = map.get(key);
      if (list) list.push(seg);
      else map.set(key, [seg]);
    }
  }
  /** 이동 선분(축 정렬)이 기존 선분과 엇갈리는 횟수. 끝점이 닿기만 하는 경우는 세지 않는다. */
  crossings(x0: number, y0: number, x1: number, y1: number): number {
    if (this.h.size === 0 && this.v.size === 0) return 0;
    let n = 0;
    if (near(y0, y1)) {
      const lo = Math.min(x0, x1);
      const hi = Math.max(x0, x1);
      const by = Math.floor(y0 / BUCKET);
      for (let bx = Math.floor(lo / BUCKET); bx <= Math.floor(hi / BUCKET); bx += 1) {
        for (const s of this.v.get(Occupancy.key(bx, by)) ?? []) {
          if (s.c > lo + EPS && s.c < hi - EPS && y0 > s.a + EPS && y0 < s.b - EPS && Math.floor(s.c / BUCKET) === bx) n += 1;
        }
      }
    } else {
      const lo = Math.min(y0, y1);
      const hi = Math.max(y0, y1);
      const bx = Math.floor(x0 / BUCKET);
      for (let by = Math.floor(lo / BUCKET); by <= Math.floor(hi / BUCKET); by += 1) {
        for (const s of this.h.get(Occupancy.key(bx, by)) ?? []) {
          if (s.c > lo + EPS && s.c < hi - EPS && x0 > s.a + EPS && x0 < s.b - EPS && Math.floor(s.c / BUCKET) === by) n += 1;
        }
      }
    }
    return n;
  }
}

/** 탐색 상태 저장소. 라우터 하나가 재사용한다(엣지마다 배열을 새로 만들지 않기 위해). */
class Scratch {
  g = new Float64Array(0);
  parent = new Int32Array(0);
  stamp = new Int32Array(0);
  closed = new Int32Array(0);
  gen = 0;
  ensure(n: number): void {
    if (this.g.length >= n) return;
    const size = Math.max(n, this.g.length * 2, 1024);
    this.g = new Float64Array(size);
    this.parent = new Int32Array(size);
    this.stamp = new Int32Array(size);
    this.closed = new Int32Array(size);
    this.gen = 0;
  }
}

/** 한 엣지의 탐색 문맥. 좌표는 탐색선 번호(ix, iy)로 다룬다. */
interface Search {
  cfg: Resolved;
  index: ObstacleIndex;
  own: OwnInflation;
  occupancy: Occupancy;
  scratch: Scratch;
  X: readonly number[];
  Y: readonly number[];
  expansions: number;
  deadline: number;
}

interface SegmentResult {
  points: Point[];
  /** 마지막 이동 방향 */
  dir: Dir | -1;
}

/**
 * 한 구간(from → to)의 A*. 상태 = (탐색선 교점, 진행 방향). `startDir`가 -1이면 첫 이동 방향 제약 없음,
 * `goalDir`가 -1이면 도착 방향 제약 없음. 시작·도착 점은 장애물 검사를 하지 않는다.
 * 상한 초과·경로 없음이면 null.
 */
function searchSegment(ctx: Search, fx: number, fy: number, startDir: Dir | -1, gx: number, gy: number, goalDir: Dir | -1): SegmentResult | null {
  const { cfg, X, Y, scratch: sc } = ctx;
  const { grid, costs } = cfg;
  const nxl = X.length;
  const stride = nxl * Y.length;
  sc.ensure(stride * 5);
  sc.gen += 1;
  const gen = sc.gen;
  const tx = X[gx] as number;
  const ty = Y[gy] as number;
  const unit = costs.straight / grid;
  const h = (ix: number, iy: number): number => {
    const x = X[ix] as number;
    const y = Y[iy] as number;
    return ((Math.abs(x - tx) + Math.abs(y - ty)) * unit + (ix !== gx && iy !== gy ? costs.bend : 0)) * TIE;
  };
  const heap = new MinHeap();
  const startKey = (fy * nxl + fx) * 5 + (startDir < 0 ? 4 : startDir);
  sc.g[startKey] = 0;
  sc.parent[startKey] = -1;
  sc.stamp[startKey] = gen;
  heap.push(h(fx, fy), startKey);
  while (heap.size > 0) {
    const key = heap.pop();
    if (sc.closed[key] === gen) continue;
    sc.closed[key] = gen;
    const dir = key % 5;
    const cell = (key - dir) / 5;
    const ix = cell % nxl;
    const iy = (cell - ix) / nxl;
    const g = sc.g[key] as number;
    if (ix === gx && iy === gy && (goalDir < 0 || dir === goalDir)) {
      const pts: Point[] = [];
      for (let k = key; k >= 0; k = sc.parent[k] as number) {
        const d = k % 5;
        const c = (k - d) / 5;
        const cx = c % nxl;
        pts.push({ x: X[cx] as number, y: Y[(c - cx) / nxl] as number });
      }
      pts.reverse();
      return { points: pts, dir: dir === 4 ? -1 : (dir as Dir) };
    }
    ctx.expansions += 1;
    if (ctx.expansions > cfg.maxExpansions || ((ctx.expansions & 15) === 0 && cfg.now() > ctx.deadline)) return null;
    const x = X[ix] as number;
    const y = Y[iy] as number;
    for (let d = 0; d < 4; d += 1) {
      if (dir < 4 && d === (dir ^ 1)) continue;
      const jx = d === 0 ? ix + 1 : d === 1 ? ix - 1 : ix;
      const jy = d === 2 ? iy + 1 : d === 3 ? iy - 1 : iy;
      if (jx < 0 || jx >= nxl || jy < 0 || jy >= Y.length) continue;
      const nx = X[jx] as number;
      const ny = Y[jy] as number;
      const isGoal = jx === gx && jy === gy;
      if (!isGoal && ctx.index.blocked(nx, ny, ctx.own)) continue;
      if (ctx.index.blocked((x + nx) / 2, (y + ny) / 2, ctx.own)) continue;
      let cost = (Math.abs(nx - x) + Math.abs(ny - y)) * unit;
      if (dir < 4 && d !== dir) cost += costs.bend;
      if (costs.cross > 0) cost += ctx.occupancy.crossings(x, y, nx, ny) * costs.cross;
      const ng = g + cost;
      const nk = (jy * nxl + jx) * 5 + d;
      if (sc.stamp[nk] === gen && ng >= (sc.g[nk] as number)) continue;
      sc.stamp[nk] = gen;
      sc.g[nk] = ng;
      sc.parent[nk] = key;
      heap.push(ng + h(jx, jy), nk);
    }
  }
  return null;
}

/** 소스·타깃 노드를 스텁 끝에서 장애물로 만드는 여백: 스텁 끝이 부풀린 사각형 안에 들어가지 않을 만큼만 줄인다. */
function ownInflation(padding: number, rect: RouteObstacle | undefined, p: Point): number {
  if (!rect) return padding;
  const dx = Math.max(rect.x - p.x, 0, p.x - (rect.x + rect.width));
  const dy = Math.max(rect.y - p.y, 0, p.y - (rect.y + rect.height));
  return Math.min(padding, Math.max(dx, dy));
}

interface ComputeOutput {
  points: Point[] | null;
  expansions: number;
}

function computeEdge(
  cfg: Resolved,
  index: ObstacleIndex,
  byId: ReadonlyMap<string, RouteObstacle>,
  occupancy: Occupancy,
  scratch: Scratch,
  req: RouteEdgeRequest,
  s: EdgeEndpoint,
  t: EdgeEndpoint,
  waypoints: readonly Point[],
): ComputeOutput {
  const ns = sideNormal(s.side);
  const nt = sideNormal(t.side);
  const start1: Point = { x: s.x + ns.x * cfg.stub, y: s.y + ns.y * cfg.stub };
  const end1: Point = { x: t.x + nt.x * cfg.stub, y: t.y + nt.y * cfg.stub };
  const srcRect = req.sourceNodeId !== undefined ? byId.get(req.sourceNodeId) : undefined;
  const dstRect = req.targetNodeId !== undefined ? byId.get(req.targetNodeId) : undefined;
  const srcInf = ownInflation(cfg.padding, srcRect, start1);
  const dstInf = ownInflation(cfg.padding, dstRect, end1);
  const own: OwnInflation = { srcId: req.sourceNodeId, srcInf, dstId: req.targetNodeId, dstInf };
  const stops: Point[] = [start1, ...waypoints, end1];
  const xs = stops.map((p) => p.x);
  const ys = stops.map((p) => p.y);
  // 이 엣지만의 탐색선: 끝점·경유점, 그 ±패딩, 사이 중간선, 자기 노드의 줄어든 경계.
  const exX = [...xs, ...xs.map((v) => v - cfg.padding), ...xs.map((v) => v + cfg.padding), ...mids(xs, cfg.grid)];
  const exY = [...ys, ...ys.map((v) => v - cfg.padding), ...ys.map((v) => v + cfg.padding), ...mids(ys, cfg.grid)];
  for (const [rect, inf] of [[srcRect, srcInf], [dstRect, dstInf]] as const) {
    if (!rect || inf >= cfg.padding) continue;
    exX.push(rect.x - inf, rect.x + rect.width + inf);
    exY.push(rect.y - inf, rect.y + rect.height + inf);
  }
  const X = mergeLines(index.lineX, exX.sort((a, b) => a - b));
  const Y = mergeLines(index.lineY, exY.sort((a, b) => a - b));
  const ctx: Search = { cfg, index, own, occupancy, scratch, X, Y, expansions: 0, deadline: cfg.now() + cfg.maxMillis };
  const out: Point[] = [{ x: s.x, y: s.y }];
  let dir: Dir | -1 = SIDE_DIR[s.side];
  for (let i = 0; i < stops.length - 1; i += 1) {
    const a = stops[i] as Point;
    const b = stops[i + 1] as Point;
    const last = i === stops.length - 2;
    const goalDir: Dir | -1 = last ? ((SIDE_DIR[t.side] ^ 1) as Dir) : -1;
    const seg = searchSegment(ctx, findLine(X, a.x), findLine(Y, a.y), dir, findLine(X, b.x), findLine(Y, b.y), goalDir);
    if (!seg) return { points: null, expansions: ctx.expansions };
    out.push(...seg.points);
    dir = seg.dir;
  }
  out.push({ x: t.x, y: t.y });
  return { points: simplifyPolyline(out), expansions: ctx.expansions };
}

/** 연속한 정거장 좌표 사이의 가운데(격자에 맞춤). Z자 꺾임이 놓일 선이 된다. */
function mids(vs: readonly number[], grid: number): number[] {
  const out: number[] = [];
  for (let i = 1; i < vs.length; i += 1) out.push(Math.round((((vs[i - 1] as number) + (vs[i] as number)) / 2) / grid) * grid);
  return out;
}

function describeEdge(req: RouteEdgeRequest, wps: readonly Point[], radius: number): string {
  const e = (p: EdgeEndpoint): string => `${p.x},${p.y},${p.side}`;
  return `${req.id}|${e(req.source)}|${e(req.target)}|${wps.map((p) => `${p.x},${p.y}`).join(";")}|${req.sourceNodeId ?? ""}|${req.targetNodeId ?? ""}|${radius}`;
}

/**
 * A* 직각 라우터를 만든다. 반환 객체는 엣지별 메모를 가진다(장애물·엣지 입력이 같으면 다시 계산하지 않는다).
 * 순수 계산이지만 메모 때문에 상태를 가지므로, 호출자별로 하나씩 만든다.
 *
 * @param options 패딩·격자·비용·탐색 상한·스텁(모두 생략 가능)
 */
export function createAStarRouter(options: RouteOptions = {}): AStarRouter {
  const cfg = resolveOptions(options);
  const cache = new Map<number, RoutedEdge>();
  const scratch = new Scratch();
  const inner: Resolved = { ...cfg, stub: Math.max(0, cfg.stub - cfg.arrowGap) };
  const stats: RouterStats = { hits: 0, misses: 0, fallbacks: 0, expansions: 0 };
  const optionsKey = `${cfg.padding}|${cfg.grid}|${cfg.costs.straight},${cfg.costs.bend},${cfg.costs.cross}|${cfg.maxExpansions}|${cfg.stub}|${cfg.arrowGap}`;

  return {
    id: "astar-orthogonal",
    clearCache: () => cache.clear(),
    stats: () => ({ ...stats }),
    route(edges, obstacles) {
      const sortedObs = [...obstacles].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
      const obsKey = sortedObs.map((o) => `${o.id},${o.x},${o.y},${o.width},${o.height}`).join(";");
      const obsHash = hash53(`${optionsKey}#${obsKey}`);
      const byId = new Map(sortedObs.map((o) => [o.id, o] as const));
      const index = new ObstacleIndex(sortedObs, cfg.padding);
      if (cache.size > cfg.cacheLimit) cache.clear();
      const occupancy = new Occupancy();
      const result = new Map<string, RoutedEdge>();
      const sorted = [...edges].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
      let chain = obsHash;
      const meta = new Map<string, { radius: number; locked: boolean; req: RouteEdgeRequest }>();
      for (const req of sorted) {
        const wps = (req.waypoints ?? []).filter(finite).slice(0, MAX_WAYPOINTS);
        const radius = clamp(req.radius ?? DEFAULT_EDGE_RADIUS, 0, MAX_EDGE_RADIUS);
        // 앞선 엣지들이 교차 비용에 영향을 주므로 해시에 앞선 엣지의 입력을 이어 붙인다.
        chain = hash53(`${chain}#${describeEdge(req, wps, radius)}`);
        const cached = cache.get(chain);
        let routed: RoutedEdge;
        if (cached) {
          stats.hits += 1;
          routed = cached;
        } else {
          stats.misses += 1;
          routed = routeOne(cfg, inner, index, byId, occupancy, scratch, req, wps, radius, stats);
          if (routed.fallback) stats.fallbacks += 1;
          cache.set(chain, routed);
        }
        occupancy.add(routed.points);
        result.set(req.id, routed);
        meta.set(req.id, { radius, locked: routed.fallback || wps.length > 0, req });
      }
      if (cfg.nudge > 0 && result.size > 1) {
        // 겹침 완화: 캐시 항목은 건드리지 않고 결과 Map에서만 바꾼 사본으로 교체한다.
        const moved = nudgeParallel(
          [...result.values()].map((r) => {
            const m = meta.get(r.id) as { radius: number; locked: boolean; req: RouteEdgeRequest };
            return { id: r.id, points: r.points, locked: m.locked, ...(m.req.sourceNodeId !== undefined ? { sourceNodeId: m.req.sourceNodeId } : {}), ...(m.req.targetNodeId !== undefined ? { targetNodeId: m.req.targetNodeId } : {}) };
          }),
          sortedObs,
          cfg.nudge,
          cfg.padding,
        );
        for (const [id, points] of moved) {
          const m = meta.get(id) as { radius: number };
          result.set(id, { id, path: roundedPolylinePath(points, m.radius), points, fallback: false });
        }
      }
      return result;
    },
  };
}

function shift(e: EdgeEndpoint, gap: number): EdgeEndpoint {
  const n = sideNormal(e.side);
  return { x: e.x + n.x * gap, y: e.y + n.y * gap, side: e.side };
}

function routeOne(
  cfg: Resolved,
  inner: Resolved,
  index: ObstacleIndex,
  byId: ReadonlyMap<string, RouteObstacle>,
  occupancy: Occupancy,
  scratch: Scratch,
  req: RouteEdgeRequest,
  wps: readonly Point[],
  radius: number,
  counter: RouterStats,
): RoutedEdge {
  const s = shift(req.source, cfg.arrowGap);
  const t = shift(req.target, cfg.arrowGap);
  // 스텁은 핸들 기준 길이에서 arrowGap을 뺀 값(shifted 끝점 기준)이다.
  const { points, expansions } = computeEdge(inner, index, byId, occupancy, scratch, req, s, t, wps);
  counter.expansions += expansions;
  if (points && points.length >= 2) {
    return { id: req.id, path: roundedPolylinePath(points, radius), points, fallback: false };
  }
  return fallbackEdge(req.id, s, t, inner.stub, radius);
}

function fallbackEdge(id: string, s: EdgeEndpoint, t: EdgeEndpoint, stub: number, radius: number): RoutedEdge {
  const input: EdgePathInput = { source: s, target: t, waypoints: [], radius, bend: 0.5, stub };
  const path = orthogonalPath(input);
  const points = orthogonalPoints(input);
  return { id, path, points, fallback: true };
}

/**
 * 모양 `auto`의 단독 `build`: 장애물을 모르는 상태(노드 정보 없음)의 자동 경로.
 * 경유점을 순서대로 지나는 최소 비용 직각 경로이며, 탐색 실패 시 경유점 없는 직각 경로로 대체한다.
 * 노드 회피는 호출자가 `EdgeRouter.route`에 장애물을 넘겨 쓴다(렌더 연결은 편집기 쪽).
 */
export const autoPath: (input: EdgePathInput) => EdgePathResult = createAutoPath();

/** `autoPath`의 탐색 상한 옵션. 생략하면 `DEFAULT_AUTO_PATH_OPTIONS`. */
export interface AutoPathOptions {
  /** 엣지당 최대 계산 시간 ms */
  maxMillis?: number;
  /** 엣지당 최대 노드 확장 수 */
  maxExpansions?: number;
}

/**
 * 단독 `auto` 모양의 `build` 함수를 만든다(상한을 옵션으로 받는다).
 * `build` 입력은 이미 arrowGap이 적용된 점이라 gap 0, 스텁은 입력값 그대로 쓴다.
 * 장애물 없는 한 엣지라 확장 수 상한(maxExpansions)이 끝을 보장한다. 기본 8ms 시계 상한은 부하에서 fallback(경유점 소실)을 낳는다(5.2R.42).
 */
export function createAutoPath(options: AutoPathOptions = {}): (input: EdgePathInput) => EdgePathResult {
  const maxMillis = options.maxMillis ?? DEFAULT_AUTO_PATH_OPTIONS.maxMillis;
  const maxExpansions = options.maxExpansions ?? DEFAULT_AUTO_PATH_OPTIONS.maxExpansions;
  return (input) => {
    const router = createAStarRouter({ arrowGap: 0, stub: input.stub, maxMillis, maxExpansions });
    const req: RouteEdgeRequest = { id: "auto", source: input.source, target: input.target, waypoints: input.waypoints, radius: input.radius };
    const r = router.route([req], []).get("auto") as RoutedEdge;
    return r.path;
  };
}
