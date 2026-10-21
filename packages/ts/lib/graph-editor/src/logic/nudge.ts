/**
 * 연결선 겹침 완화(graph-edges §4.2, ux-overhaul §10.2 규칙 7). 순수 함수.
 * 라우터가 낸 직각 꺾은선들에서 같은 줄 위에서 길이가 겹치는 선분을 찾아 `gap`px씩 나란히 벌린다.
 * - 끝점·스텁 선분(첫·마지막)과 경유점이 있는 엣지의 선분은 움직이지 않는다(자리만 차지한다).
 * - 벌린 결과(이동한 선분과 이웃 두 선분)가 다른 노드의 패딩 포함 사각형(자기 끝 노드는 실제 사각형)을 지나면 그 선분은 그대로 둔다.
 * - 입력 순서와 무관하게 엣지 id 순으로 결정적이다.
 */
import type { Point } from "./ops";

export interface NudgeEdge {
  id: string;
  /** 직각 꺾은선(양 끝 포함) */
  points: readonly Point[];
  /** true면 어떤 선분도 옮기지 않는다(경유점이 있거나 대체 경로) */
  locked?: boolean;
  /** 첫·마지막 선분이 사각형 안에서 시작·끝나는 노드(검사에서 제외) */
  sourceNodeId?: string;
  targetNodeId?: string;
}

export interface NudgeRect {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

interface Seg {
  edge: number;
  index: number;
  horizontal: boolean;
  /** 줄 좌표(가로면 y, 세로면 x) */
  line: number;
  lo: number;
  hi: number;
  movable: boolean;
}

const EPS = 0.5;
/** 스텁 등 이웃 선분이 이 길이 아래로 줄어들면 옮기지 않는다 */
const MIN_NEIGHBOR = 4;
/** 한 선분을 옮기면 이웃 선분 길이가 바뀌어 새 겹침이 생길 수 있어 훑는 최대 횟수 */
const MAX_PASSES = 4;

function segsOf(edges: readonly NudgeEdge[]): Seg[] {
  const out: Seg[] = [];
  edges.forEach((e, edge) => {
    const n = e.points.length;
    for (let i = 0; i < n - 1; i += 1) {
      const a = e.points[i] as Point;
      const b = e.points[i + 1] as Point;
      const horizontal = Math.abs(a.y - b.y) < 1e-6;
      if (!horizontal && Math.abs(a.x - b.x) >= 1e-6) continue; // 직각이 아닌 선분은 무시
      const line = horizontal ? a.y : a.x;
      const lo = horizontal ? Math.min(a.x, b.x) : Math.min(a.y, b.y);
      const hi = horizontal ? Math.max(a.x, b.x) : Math.max(a.y, b.y);
      if (hi - lo < 1e-6) continue;
      out.push({ edge, index: i, horizontal, line, lo, hi, movable: e.locked !== true && i >= 1 && i <= n - 3 });
    }
  });
  return out;
}

/** 선분이 (부풀린) 사각형 내부를 지나는가. 경계에 닿는 것은 지나는 것이 아니다 */
function hitsRect(a: Point, b: Point, r: NudgeRect, inflate: number): boolean {
  const l = r.x - inflate;
  const rr = r.x + r.width + inflate;
  const t = r.y - inflate;
  const bb = r.y + r.height + inflate;
  if (rr <= l || bb <= t) return false;
  return Math.max(a.x, b.x) > l && Math.min(a.x, b.x) < rr && Math.max(a.y, b.y) > t && Math.min(a.y, b.y) < bb;
}

/** 서로 다른 엣지 선분이 겹치는 묶음(연결 요소). 한 묶음에 엣지가 둘 이상일 때만 돌려준다. */
function clusters(group: readonly Seg[]): Seg[][] {
  const sorted = [...group].sort((a, b) => a.lo - b.lo || a.edge - b.edge);
  const out: Seg[][] = [];
  let cur: Seg[] = [];
  let reach = Number.NEGATIVE_INFINITY;
  for (const s of sorted) {
    if (cur.length > 0 && s.lo >= reach - EPS) {
      out.push(cur);
      cur = [];
      reach = Number.NEGATIVE_INFINITY;
    }
    cur.push(s);
    reach = Math.max(reach, s.hi);
  }
  if (cur.length > 0) out.push(cur);
  return out.filter((c) => new Set(c.map((s) => s.edge)).size > 1);
}

/** 묶음 안 움직일 수 있는 선분의 오프셋. 못 움직이는 선분이 있으면 그 줄은 비워 두고 ±gap, ±2gap… 순으로 쓴다. */
function offsets(count: number, gap: number, hasFixed: boolean): number[] {
  if (hasFixed) {
    return Array.from({ length: count }, (_, i) => (i % 2 === 0 ? 1 : -1) * (Math.floor(i / 2) + 1) * gap);
  }
  return Array.from({ length: count }, (_, i) => (i - (count - 1) / 2) * gap);
}

/**
 * 겹치는 평행 선분을 벌린 점 목록을 돌려준다(바뀐 엣지만 담는다).
 * @param edges 엣지별 직각 꺾은선
 * @param rects 노드 사각형(패딩 없는 실제 크기)
 * @param padding 다른 노드 둘레로 비워 둘 여백 px(라우터의 패딩과 같게)
 * @param gap 벌릴 간격 px(0 이하이면 아무것도 하지 않는다)
 */
export function nudgeParallel(edges: readonly NudgeEdge[], rects: readonly NudgeRect[], gap: number, padding = 0): Map<string, Point[]> {
  const result = new Map<string, Point[]>();
  if (!(gap > 0) || edges.length < 2) return result;
  // 엣지 id 순으로 정렬해 입력 순서와 무관하게 만든다
  edges = [...edges].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const pts = edges.map((e) => e.points.map((p) => ({ x: p.x, y: p.y })));
  /** 선분 하나를 `d`만큼 옮긴다. 이웃이 뒤집히거나 다른 노드 여백을 지나면 아무것도 바꾸지 않고 false. */
  const tryMove = (seg: Seg, d: number): boolean => {
    if (Math.abs(d) < 1e-6) return true;
    const e = edges[seg.edge] as NudgeEdge;
    const p = pts[seg.edge] as Point[];
    const i = seg.index;
    const axis: "x" | "y" = seg.horizontal ? "y" : "x";
    const a = p[i] as Point;
    const b = p[i + 1] as Point;
    const before = p[i - 1] as Point;
    const after = p[i + 2] as Point;
    // 이웃 선분은 `axis` 방향으로 늘거나 준다. 방향이 뒤집히거나 너무 짧아지면 옮기지 않는다.
    const okNeighbor = (far: Point, near: Point): boolean => {
      const oldLen = near[axis] - far[axis];
      const newLen = near[axis] + d - far[axis];
      return Math.sign(oldLen) === Math.sign(newLen) && Math.abs(newLen) >= MIN_NEIGHBOR;
    };
    if (!okNeighbor(before, a) || !okNeighbor(after, b)) return false;
    const na = { ...a, [axis]: a[axis] + d };
    const nb = { ...b, [axis]: b[axis] + d };
    const checks: [Point, Point][] = [
      [na, nb],
      [before, na],
      [nb, after],
    ];
    for (const [from, to] of checks) {
      for (const r of rects) {
        const own = r.id === e.sourceNodeId || r.id === e.targetNodeId;
        if (hitsRect(from, to, r, own ? 0 : padding)) return false;
      }
    }
    p[i] = na;
    p[i + 1] = nb;
    return true;
  };
  /** 한 묶음을 옮긴다: 기준 줄을 0, ±gap/2, ±gap 순으로 밀어 가며 모두 들어가는 첫 배치를 쓴다(좁은 통로에서 한쪽으로 몰기). 모두 실패하면 가능한 선분만 옮긴다. */
  const applyCluster = (plan: { seg: Seg; target: number }[]): void => {
    const shifts = [0, -gap / 2, gap / 2, -gap, gap];
    for (const sh of shifts) {
      const done: { seg: Seg; a: Point; b: Point }[] = [];
      let ok = true;
      for (const { seg, target } of plan) {
        const p = pts[seg.edge] as Point[];
        const snap = { seg, a: p[seg.index] as Point, b: p[seg.index + 1] as Point };
        if (!tryMove(seg, target + sh - seg.line)) {
          ok = false;
          break;
        }
        done.push(snap);
      }
      if (ok) return;
      for (const { seg, a, b } of done) {
        const p = pts[seg.edge] as Point[];
        p[seg.index] = a;
        p[seg.index + 1] = b;
      }
    }
    for (const { seg, target } of plan) tryMove(seg, target - seg.line);
  };
  /** 현재 점 기준으로 한 번 훑는다. 가로선을 옮기면 세로선 길이가 바뀌어 새로 겹칠 수 있으므로 호출부가 되풀이한다. */
  const pass = (): void => {
    // 같은 줄뿐 아니라 `gap`보다 가까운 줄(3px 간격 등)도 한 묶음으로 본다: 줄 좌표 순으로 이웃과 gap 미만이면 이어 붙인다.
    const groups: Seg[][] = [];
    for (const horizontal of [true, false]) {
      const all = segsOf(edges.map((e, k) => ({ ...e, points: pts[k] as Point[] }))).filter((s) => s.horizontal === horizontal).sort((a, b) => a.line - b.line);
      let cur: Seg[] = [];
      for (const s of all) {
        if (cur.length > 0 && s.line - (cur[cur.length - 1] as Seg).line >= gap - EPS) {
          groups.push(cur);
          cur = [];
        }
        cur.push(s);
      }
      if (cur.length > 0) groups.push(cur);
    }
    for (const g of groups) {
      if (g.length < 2) continue;
      for (const c of clusters(g)) {
        const movable = c.filter((s) => s.movable).sort((a, b) => a.line - b.line || a.edge - b.edge || a.index - b.index);
        if (movable.length === 0) continue;
        const fixed = c.find((s) => !s.movable);
        // 같은 엣지가 한 묶음에 두 번 들어오면(U자 되접힘) 하나만 움직인다
        const seen = new Set<number>();
        const uniq = movable.filter((s) => (seen.has(s.edge) ? false : (seen.add(s.edge), true)));
        const offs = offsets(uniq.length, gap, fixed !== undefined);
        // 기준 줄: 못 움직이는 선분이 있으면 그 줄, 없으면 움직일 선분들의 평균 줄
        const base = fixed !== undefined ? fixed.line : uniq.reduce((acc, q) => acc + q.line, 0) / uniq.length;
        applyCluster(uniq.map((seg, i) => ({ seg, target: base + (offs[i] as number) })));
      }
    }
  };
  for (let k = 0; k < MAX_PASSES; k += 1) {
    const snapshot = JSON.stringify(pts);
    pass();
    if (JSON.stringify(pts) === snapshot) break;
  }
  edges.forEach((e, idx) => {
    const p = pts[idx] as Point[];
    if (p.some((q, k) => q.x !== (e.points[k] as Point).x || q.y !== (e.points[k] as Point).y)) result.set(e.id, p);
  });
  return result;
}
