/**
 * 연결선 경로 계산(graph-edges §2.1). 순수 함수이며 React Flow에 의존하지 않는다.
 * `buildEdgePath`가 입력을 보정(법선 방향 `ARROW_GAP`, 경유점 상한, 모양이 지원하는 값만 전달)한 뒤
 * 모양의 `build`를 부른다. 이 파일의 나머지는 내장 모양이 쓰는 기하 도우미다.
 */
import type { Point } from "./ops";
import type { EdgeEndpoint, EdgePathInput, EdgePathResult, EdgeSegment, EdgeShapeDescriptor, PathPointAt, Side } from "../shapes/types";

/** 선은 핸들 경계에서 면의 바깥 법선 방향으로 이만큼 떨어져 시작/끝난다(tokens 4.4). */
export const ARROW_GAP = 6;
/** 핸들에서 면 바깥쪽으로 먼저 내는 스텁 길이(16px). */
export const EDGE_STUB = 16;
/** 모서리 반경 기본값(8px)과 상한. */
export const DEFAULT_EDGE_RADIUS = 8;
export const MAX_EDGE_RADIUS = 24;
/** 연결 하나의 경유점 상한. */
export const MAX_WAYPOINTS = 16;
export const DEFAULT_BEND = 0.5;

const NORMALS: Readonly<Record<Side, Point>> = {
  left: { x: -1, y: 0 },
  right: { x: 1, y: 0 },
  top: { x: 0, y: -1 },
  bottom: { x: 0, y: 1 },
};

/** 면의 바깥 법선(단위 벡터). */
export const sideNormal = (side: Side): Point => NORMALS[side];

const clamp = (v: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, v));
const finite = (p: Point): boolean => Number.isFinite(p.x) && Number.isFinite(p.y);

/** `buildEdgePath` 입력. 끝점은 핸들 위치(선 끝이 아니라 핸들 경계)다. */
export interface BuildEdgePathInput {
  source: EdgeEndpoint;
  target: EdgeEndpoint;
  /** 경유점(캔버스 절대 좌표). 생략 = 없음 */
  waypoints?: readonly Point[] | null;
  shape: EdgeShapeDescriptor;
  /** 모서리 반경. 생략 = 8 */
  radius?: number | null;
  /** 꺾임 위치 0~1. 생략 = 0.5 */
  bend?: number | null;
  /** 면 바깥 오프셋. 생략 = `ARROW_GAP` */
  arrowGap?: number;
  /** 핸들 기준 스텁 길이. 생략 = `EDGE_STUB` */
  stub?: number;
}

/**
 * 모양 하나로 경로를 만든다.
 * - 끝점을 면의 바깥 법선 방향으로 `arrowGap`만큼 옮긴다(상하 면에서도 화살촉이 가려지지 않게).
 * - 모양이 지원하지 않는 값(`supportsWaypoints`·`supportsBend`·`supportsRadius`가 false)은 모양에 넘기지 않는다.
 * - 경유점은 앞에서부터 `MAX_WAYPOINTS`개까지, 좌표가 유한하지 않은 점은 버린다.
 */
export function buildEdgePath(input: BuildEdgePathInput): EdgePathResult {
  const gap = Math.max(0, input.arrowGap ?? ARROW_GAP);
  const shiftBy = (e: EdgeEndpoint): EdgeEndpoint => {
    const n = sideNormal(e.side);
    return { x: e.x + n.x * gap, y: e.y + n.y * gap, side: e.side };
  };
  const { shape } = input;
  const waypoints = shape.supportsWaypoints ? (input.waypoints ?? []).filter(finite).slice(0, MAX_WAYPOINTS) : [];
  const radius = shape.supportsRadius ? clamp(input.radius ?? DEFAULT_EDGE_RADIUS, 0, MAX_EDGE_RADIUS) : 0;
  const bend = shape.supportsBend ? clamp(input.bend ?? DEFAULT_BEND, 0, 1) : DEFAULT_BEND;
  return shape.build({
    source: shiftBy(input.source),
    target: shiftBy(input.target),
    waypoints,
    radius,
    bend,
    stub: Math.max(0, (input.stub ?? EDGE_STUB) - gap),
  });
}

// ---------------------------------------------------------------------------------------------
// 펼친 경로(선분 목록)에서 길이·라벨 위치를 구한다.

function makeResult(d: string, pts: readonly Point[], labelOverride?: (t: number) => PathPointAt): EdgePathResult {
  const segments: EdgeSegment[] = [];
  let length = 0;
  for (let i = 1; i < pts.length; i += 1) {
    const from = pts[i - 1] as Point;
    const to = pts[i] as Point;
    const len = Math.hypot(to.x - from.x, to.y - from.y);
    if (len === 0) continue;
    segments.push({ from, to });
    length += len;
  }
  const labelAt = (t: number): PathPointAt => {
    if (labelOverride) return labelOverride(clamp(t, 0, 1));
    const first = segments[0];
    if (!first) {
      const p = pts[0] ?? { x: 0, y: 0 };
      return { x: p.x, y: p.y, angle: 0 };
    }
    let remain = clamp(t, 0, 1) * length;
    for (const s of segments) {
      const len = Math.hypot(s.to.x - s.from.x, s.to.y - s.from.y);
      if (remain <= len) {
        const k = len === 0 ? 0 : remain / len;
        return {
          x: s.from.x + (s.to.x - s.from.x) * k,
          y: s.from.y + (s.to.y - s.from.y) * k,
          angle: Math.atan2(s.to.y - s.from.y, s.to.x - s.from.x),
        };
      }
      remain -= len;
    }
    const last = segments[segments.length - 1] as EdgeSegment;
    return { x: last.to.x, y: last.to.y, angle: Math.atan2(last.to.y - last.from.y, last.to.x - last.from.x) };
  };
  return { d, labelAt, segments, length };
}

/** 소수 둘째 자리로 줄여 문자열로(긴 부동소수 방지). */
const r2 = (n: number): string => String(Math.round(n * 100) / 100);

// ---------------------------------------------------------------------------------------------
// 직선

/** 시작 → 경유점… → 끝 직선. */
export function straightPath(input: EdgePathInput): EdgePathResult {
  const pts = dedupe([input.source, ...input.waypoints, input.target]);
  const d = pts.map((p, i) => `${i === 0 ? "M" : "L"}${r2(p.x)},${r2(p.y)}`).join(" ");
  return makeResult(d, pts);
}

function dedupe(pts: readonly Point[]): Point[] {
  const out: Point[] = [];
  for (const p of pts) {
    const last = out[out.length - 1];
    if (!last || last.x !== p.x || last.y !== p.y) out.push({ x: p.x, y: p.y });
  }
  return out;
}

// ---------------------------------------------------------------------------------------------
// 곡선(베지어)

const curveOffset = (distance: number, curvature: number): number =>
  distance >= 0 ? 0.5 * distance : curvature * 25 * Math.sqrt(-distance);

/** React Flow `getBezierPath`와 같은 규칙의 제어점(곡률 0.25). */
function controlOf(side: Side, p: Point, q: Point): Point {
  const c = 0.25;
  switch (side) {
    case "left":
      return { x: p.x - curveOffset(p.x - q.x, c), y: p.y };
    case "right":
      return { x: p.x + curveOffset(q.x - p.x, c), y: p.y };
    case "top":
      return { x: p.x, y: p.y - curveOffset(p.y - q.y, c) };
    case "bottom":
      return { x: p.x, y: p.y + curveOffset(q.y - p.y, c) };
  }
}

type Cubic = readonly [Point, Point, Point, Point];

const cubicAt = ([a, b, c, e]: Cubic, t: number): Point => {
  const u = 1 - t;
  return {
    x: u * u * u * a.x + 3 * u * u * t * b.x + 3 * u * t * t * c.x + t * t * t * e.x,
    y: u * u * u * a.y + 3 * u * u * t * b.y + 3 * u * t * t * c.y + t * t * t * e.y,
  };
};

function flattenCubics(cubics: readonly Cubic[], steps = 24): Point[] {
  const pts: Point[] = [];
  cubics.forEach((cu, i) => {
    if (i === 0) pts.push(cu[0]);
    for (let k = 1; k <= steps; k += 1) pts.push(cubicAt(cu, k / steps));
  });
  return pts;
}

/**
 * 곡선. 경유점이 없으면 React Flow `getBezierPath`와 같은 문자열(호환, 스냅샷 고정),
 * 있으면 경유점을 지나는 Catmull-Rom 스플라인(접선 = 0.5 × 이웃 점 차)을 3차 베지어로 바꾼 것.
 * 양 끝은 면의 법선 방향으로 나간다.
 */
export function bezierPath(input: EdgePathInput): EdgePathResult {
  const { source: s, target: t } = input;
  if (input.waypoints.length === 0) {
    const c1 = controlOf(s.side, s, t);
    const c2 = controlOf(t.side, t, s);
    const d = `M${s.x},${s.y} C${c1.x},${c1.y} ${c2.x},${c2.y} ${t.x},${t.y}`;
    const cubic: Cubic = [s, c1, c2, t];
    const pts = flattenCubics([cubic]);
    // 라벨은 예전과 같은 위치(매개변수 t, 0.5 = 3차 베지어 t=0.5)에 둔다.
    return makeResult(d, pts, (u) => {
      const p = cubicAt(cubic, u);
      const q = cubicAt(cubic, Math.min(1, u + 0.01));
      const q0 = cubicAt(cubic, Math.max(0, u - 0.01));
      return { ...p, angle: Math.atan2(q.y - q0.y, q.x - q0.x) };
    });
  }
  const P: Point[] = [s, ...input.waypoints, t];
  const tangent = (i: number): Point => {
    const prev = P[i - 1] as Point;
    const next = P[i + 1] as Point;
    return { x: (next.x - prev.x) * 0.5, y: (next.y - prev.y) * 0.5 };
  };
  const cubics: Cubic[] = [];
  for (let i = 0; i < P.length - 1; i += 1) {
    const a = P[i] as Point;
    const b = P[i + 1] as Point;
    const len = Math.hypot(b.x - a.x, b.y - a.y);
    let c1: Point;
    if (i === 0) {
      const n = sideNormal(s.side);
      c1 = { x: a.x + n.x * len * 0.4, y: a.y + n.y * len * 0.4 };
    } else {
      const tg = tangent(i);
      c1 = { x: a.x + tg.x / 3, y: a.y + tg.y / 3 };
    }
    let c2: Point;
    if (i === P.length - 2) {
      const n = sideNormal(t.side);
      c2 = { x: b.x + n.x * len * 0.4, y: b.y + n.y * len * 0.4 };
    } else {
      const tg = tangent(i + 1);
      c2 = { x: b.x - tg.x / 3, y: b.y - tg.y / 3 };
    }
    cubics.push([a, c1, c2, b]);
  }
  const first = cubics[0] as Cubic;
  let d = `M${r2(first[0].x)},${r2(first[0].y)}`;
  for (const [, c1, c2, e] of cubics) d += ` C${r2(c1.x)},${r2(c1.y)} ${r2(c2.x)},${r2(c2.y)} ${r2(e.x)},${r2(e.y)}`;
  return makeResult(d, flattenCubics(cubics));
}

// ---------------------------------------------------------------------------------------------
// 직각(smoothstep / step / auto 공통)

type Axis = "h" | "v";
const axisOf = (n: Point): Axis => (n.x !== 0 ? "h" : "v");
const sign = (n: number): number => (n > 0 ? 1 : n < 0 ? -1 : 0);

/**
 * 직각 경로의 꺾임점 목록(양 끝 포함). 규칙(graph-edges §2.1):
 * 1. 양 끝에서 면 바깥쪽으로 스텁을 먼저/마지막으로 낸다.
 * 2. 진행 축이 가로면 가로로 먼저 세로로 나중에 한 번 꺾는다. 마지막 선분 축이 다음 구간의 진행 축이 된다.
 *    단, 그렇게 하면 직전 선분을 되돌아가게 되면(역주행) 반대 축을 먼저 쓴다.
 * 3. 마지막 구간은 타깃 면의 진입 축으로 끝난다. 진행 축이 이미 같으면 가운데에서 한 번 더 꺾는 Z자(3선분).
 *    가운데 위치는 `bend`(경유점이 있을 땐 0.5).
 */
export function orthogonalPoints(input: EdgePathInput): Point[] {
  const { source: s, target: t } = input;
  const ns = sideNormal(s.side);
  const nt = sideNormal(t.side);
  const start1: Point = { x: s.x + ns.x * input.stub, y: s.y + ns.y * input.stub };
  const end1: Point = { x: t.x + nt.x * input.stub, y: t.y + nt.y * input.stub };
  const targets: Point[] = [...input.waypoints, end1];
  const out: Point[] = [{ x: s.x, y: s.y }, start1];
  let cur = start1;
  let dir: Point = ns;
  const entryAxis = axisOf(nt);
  targets.forEach((q, i) => {
    const last = i === targets.length - 1;
    const mid = last && input.waypoints.length === 0 ? input.bend : 0.5;
    const dx = q.x - cur.x;
    const dy = q.y - cur.y;
    if (dx !== 0 && dy !== 0) {
      const a = axisOf(dir);
      const along = a === "h" ? dx : dy;
      const reversing = sign(along) * (a === "h" ? dir.x : dir.y) < 0;
      if (last && a === entryAxis && !reversing) {
        // Z자: 진행 축 방향으로 mid까지 → 수직 → 진행 축으로 도착
        out.push(
          a === "h" ? { x: cur.x + dx * mid, y: cur.y } : { x: cur.x, y: cur.y + dy * mid },
          a === "h" ? { x: cur.x + dx * mid, y: q.y } : { x: q.x, y: cur.y + dy * mid },
        );
      } else if (last && a === entryAxis) {
        // 역주행 + 같은 축: 수직 먼저 mid까지 → 진행 축으로 → 수직으로 도착
        out.push(
          a === "h" ? { x: cur.x, y: cur.y + dy * mid } : { x: cur.x + dx * mid, y: cur.y },
          a === "h" ? { x: q.x, y: cur.y + dy * mid } : { x: cur.x + dx * mid, y: q.y },
        );
      } else if (reversing) {
        out.push(a === "h" ? { x: cur.x, y: q.y } : { x: q.x, y: cur.y });
      } else {
        out.push(a === "h" ? { x: q.x, y: cur.y } : { x: cur.x, y: q.y });
      }
    }
    out.push(q);
    const prev = out[out.length - 2] as Point;
    const dirx = sign(q.x - prev.x);
    const diry = sign(q.y - prev.y);
    if (dirx !== 0 || diry !== 0) dir = { x: dirx, y: diry };
    cur = q;
  });
  out.push({ x: t.x, y: t.y });
  return simplifyPolyline(out);
}

/** 겹치는 점과 같은 방향으로 이어지는 중간 점을 지운다. */
export function simplifyPolyline(pts: readonly Point[]): Point[] {
  const base = dedupe(pts);
  const out: Point[] = [];
  for (const p of base) {
    while (out.length >= 2) {
      const a = out[out.length - 2] as Point;
      const b = out[out.length - 1] as Point;
      const cross = (b.x - a.x) * (p.y - b.y) - (b.y - a.y) * (p.x - b.x);
      const dot = (b.x - a.x) * (p.x - b.x) + (b.y - a.y) * (p.y - b.y);
      if (cross === 0 && dot > 0) out.pop();
      else break;
    }
    out.push(p);
  }
  return out;
}

/**
 * 직각 경로 + 둥근 모서리. 반경은 인접 선분 길이의 절반을 넘지 않는다. 직각이 아닌 꺾임(되돌아감)은 둥글리지 않는다.
 * 모서리는 2차 베지어(`Q`, 제어점 = 꺾임점).
 */
export function orthogonalPath(input: EdgePathInput): EdgePathResult {
  return roundedPolylinePath(orthogonalPoints(input), input.radius);
}

/** 직각 꺾은선(점 목록)을 둥근 모서리 경로로 만든다. 라우터(`logic/route.ts`)도 이 함수로 결과를 만든다. */
export function roundedPolylinePath(pts: readonly Point[], radius: number): EdgePathResult {
  const input = { radius };
  const flat: Point[] = [];
  const first = pts[0];
  if (!first) return makeResult("", []);
  let d = `M${r2(first.x)},${r2(first.y)}`;
  flat.push(first);
  for (let i = 1; i < pts.length; i += 1) {
    const p = pts[i] as Point;
    const prev = pts[i - 1] as Point;
    const next = pts[i + 1];
    if (!next || input.radius <= 0) {
      d += ` L${r2(p.x)},${r2(p.y)}`;
      flat.push(p);
      continue;
    }
    const lenIn = Math.hypot(p.x - prev.x, p.y - prev.y);
    const lenOut = Math.hypot(next.x - p.x, next.y - p.y);
    const right = (p.x - prev.x) * (next.x - p.x) + (p.y - prev.y) * (next.y - p.y) === 0;
    if (!right) {
      d += ` L${r2(p.x)},${r2(p.y)}`;
      flat.push(p);
      continue;
    }
    const r = Math.min(input.radius, lenIn / 2, lenOut / 2);
    const a: Point = { x: p.x - ((p.x - prev.x) / lenIn) * r, y: p.y - ((p.y - prev.y) / lenIn) * r };
    const b: Point = { x: p.x + ((next.x - p.x) / lenOut) * r, y: p.y + ((next.y - p.y) / lenOut) * r };
    d += ` L${r2(a.x)},${r2(a.y)} Q${r2(p.x)},${r2(p.y)} ${r2(b.x)},${r2(b.y)}`;
    flat.push(a);
    for (let k = 1; k <= 8; k += 1) {
      const u = k / 8;
      const w = 1 - u;
      flat.push({
        x: w * w * a.x + 2 * w * u * p.x + u * u * b.x,
        y: w * w * a.y + 2 * w * u * p.y + u * u * b.y,
      });
    }
  }
  return makeResult(d, flat);
}
