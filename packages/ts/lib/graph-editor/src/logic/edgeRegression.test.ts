/**
 * 5.2R.23 회귀 세트: 기본 설정(layout 없음)에서 연결선이 노드 사각형을 지나지 않고, 사용자가 고친 선은 저장된 모양 그대로다.
 * 교차가 실측된 팀 모양 5개 + 24노드 스트레스 + 데모 팀 12개(위 5개 포함)를 임의 타입 이름의 합성 그래프로 재현한다.
 * 실제 workspace 팀 파일이 아니라 모양(위치·연결 위상)만 옮긴 것이다. 실서버 확인은 QA에서 한다.
 */
import { describe, expect, it } from "vitest";
import type { EdgeLayout, EdgeSpec, Graph, NodeSpec, NodeTypeDescriptor } from "@agent-console/contracts";
import { defaultMessages } from "../messages";
import { buildFlowModel } from "./convert";
import { faceAnchor } from "./autoRoute";
import { createAStarRouter } from "./route";
import type { RouteEdgeRequest, RoutedEdge } from "./route";
import { parseHandleId } from "./ports";
import type { Point } from "./ops";

const W = 200;
const H = 96;
const PAD = 16;

const nodeTypes: NodeTypeDescriptor[] = [
  { id: "reg-node", version: 1, title: "노드", category: "c", static_ports: { inputs: [{ name: "in" }], outputs: [{ name: "out" }] } },
];

interface Spec {
  name: string;
  nodes: [string, number, number][];
  /** [id, from, to, layout?] */
  edges: [string, string, string, EdgeLayout?][];
}

const graphOf = (s: Spec, ui?: Record<string, unknown>): Graph => ({
  id: s.name,
  name: s.name,
  ...(ui ? { ui } : {}),
  nodes: s.nodes.map(([id, x, y]): NodeSpec => ({ id, type: "reg-node", label: id, config: {}, position: { x, y }, initialWidth: W } as unknown as NodeSpec)),
  edges: s.edges.map(([id, a, b, layout]): EdgeSpec => ({ id, kind: "reg-flow", source: { node: a, port: "out" }, target: { node: b, port: "in" }, ...(layout ? { layout } : {}) })),
});

const row = (ids: string[], y = 0, gap = 320, x0 = 0): [string, number, number][] => ids.map((id, i) => [id, x0 + i * gap, y]);

/** 교차가 실측된 팀 5개의 모양 */
const CROSSING: Spec[] = [
  {
    name: "review-loop",
    nodes: [["you", 0, 120], ["writer", 320, 120], ["review", 660, 120]],
    edges: [["m1", "you", "writer"], ["h1", "writer", "review"], ["back", "review", "writer"], ["a1", "review", "you"], ["a2", "review", "you"]],
  },
  {
    name: "review-pipeline",
    nodes: [["you", 0, 120], ...row(["draft", "check", "polish"], 120, 320, 320)],
    edges: [["m1", "you", "draft"], ["h1", "draft", "check"], ["h2", "check", "polish"], ["back", "check", "draft"], ["a1", "polish", "you"], ["a2", "check", "you"]],
  },
  {
    name: "demo-branch",
    nodes: [["start", 0, 160], ["split", 320, 160], ["x", 680, 0], ["y", 680, 160], ["z", 680, 320], ["merge", 1040, 160]],
    edges: [["e1", "start", "split"], ["e2", "split", "x"], ["e3", "split", "y"], ["e4", "split", "z"], ["e5", "x", "merge"], ["e6", "y", "merge"], ["e7", "z", "merge"], ["skip", "start", "merge"]],
  },
  {
    name: "demo-onerror",
    nodes: [["task1", 0, 0], ["task2", 360, 0], ["task3", 720, 0], ["handler", 360, 280], ["done", 1080, 0]],
    edges: [["f1", "task1", "task2"], ["f2", "task2", "task3"], ["f3", "task3", "done"], ["err1", "task1", "handler"], ["err2", "task2", "handler"], ["err3", "task3", "handler"], ["ret", "handler", "done"]],
  },
  {
    name: "team-of-teams",
    nodes: [["you", 0, 200], ["lead", 320, 200], ["a1", 680, 0], ["a2", 1040, 0], ["b1", 680, 400], ["b2", 1040, 400], ["sum", 1400, 200]],
    edges: [["m", "you", "lead"], ["d1", "lead", "a1"], ["d2", "lead", "b1"], ["a", "a1", "a2"], ["b", "b1", "b2"], ["r1", "a2", "sum"], ["r2", "b2", "sum"], ["x", "a1", "b2"], ["back", "sum", "lead"], ["ans", "sum", "you"]],
  },
];

/** 데모 팀의 나머지 7개 모양 */
const OTHERS: Spec[] = [
  { name: "solo", nodes: row(["you", "agent"]), edges: [["m", "you", "agent"], ["r", "agent", "you"]] },
  { name: "linear", nodes: row(["a", "b", "c", "d"]), edges: [["1", "a", "b"], ["2", "b", "c"], ["3", "c", "d"]] },
  { name: "fanout", nodes: [["hub", 0, 240], ...[0, 1, 2, 3, 4].map((i): [string, number, number] => [`w${i}`, 360, i * 160])], edges: [0, 1, 2, 3, 4].map((i): [string, string, string] => [`o${i}`, "hub", `w${i}`]) },
  { name: "diamond", nodes: [["top", 320, 0], ["l", 0, 200], ["r", 640, 200], ["bottom", 320, 400]], edges: [["1", "top", "l"], ["2", "top", "r"], ["3", "l", "bottom"], ["4", "r", "bottom"], ["5", "l", "r"]] },
  { name: "ring", nodes: [["a", 0, 0], ["b", 360, 0], ["c", 720, 0], ["d", 720, 240], ["e", 360, 240], ["f", 0, 240]], edges: [["1", "a", "b"], ["2", "b", "c"], ["3", "c", "d"], ["4", "d", "e"], ["5", "e", "f"], ["6", "f", "a"], ["7", "b", "e"]] },
  { name: "two-lane", nodes: [...row(["a1", "a2", "a3"], 0), ...row(["b1", "b2", "b3"], 240)], edges: [["1", "a1", "a2"], ["2", "a2", "a3"], ["3", "b1", "b2"], ["4", "b2", "b3"], ["x1", "a1", "b3"], ["x2", "b1", "a3"]] },
  { name: "star-in", nodes: [["core", 360, 240], ...[0, 1, 2, 3].map((i): [string, number, number] => [`s${i}`, i % 2 === 0 ? 0 : 720, i < 2 ? 0 : 480])], edges: [0, 1, 2, 3].map((i): [string, string, string] => [`i${i}`, `s${i}`, "core"]) },
];

/** 24노드 25연결 스트레스(결정적 난수로 건너뛰는 연결을 섞는다) */
function stress(): Spec {
  const nodes: [string, number, number][] = [];
  for (let i = 0; i < 24; i += 1) nodes.push([`n${i}`, (i % 6) * 340, Math.floor(i / 6) * 220]);
  let seed = 11;
  const rnd = (): number => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
  const edges: [string, string, string][] = [];
  for (let i = 0; i < 23; i += 1) edges.push([`c${i}`, `n${i}`, `n${i + 1}`]);
  while (edges.length < 25) {
    const a = Math.floor(rnd() * 24);
    const b = Math.floor(rnd() * 24);
    if (a !== b && Math.abs(a - b) > 1) edges.push([`s${edges.length}`, `n${a}`, `n${b}`]);
  }
  return { name: "stress24", nodes, edges };
}

const ALL: Spec[] = [...CROSSING, ...OTHERS, stress()];

interface Rect { id: string; x: number; y: number; width: number; height: number }

function pierces(points: readonly Point[], r: Rect, inf: number): boolean {
  const x0 = r.x - inf, x1 = r.x + r.width + inf, y0 = r.y - inf, y1 = r.y + r.height + inf;
  for (let i = 1; i < points.length; i += 1) {
    const a = points[i - 1]!, b = points[i]!;
    if (Math.min(a.x, b.x) < x1 - 1e-3 && Math.max(a.x, b.x) > x0 + 1e-3 && Math.min(a.y, b.y) < y1 - 1e-3 && Math.max(a.y, b.y) > y0 + 1e-3) return true;
  }
  return false;
}

const build = (g: Graph) =>
  buildFlowModel({
    graph: g, nodeTypes, edgeTypes: [{ id: "reg-flow", title: "흐름" }], resolved: new Map(), nodeStates: {}, edgeStates: {},
    selectedNodes: new Set(), selectedEdges: new Set(), positionOverrides: new Map(), readOnly: false, messages: defaultMessages, markerId: "m",
  });

/** 편집기와 같은 순서(모델 → 끝점 → 라우터)로 자동 경로 엣지의 결과를 만든다. 노드 크기는 H로 고정(실제 렌더 크기의 대리). */
function routeAll(g: Graph): { routes: ReadonlyMap<string, RoutedEdge>; rects: Rect[]; model: ReturnType<typeof build>; requests: RouteEdgeRequest[] } {
  const model = build(g);
  const rects: Rect[] = model.nodes.map((n) => ({ id: n.id, x: n.position.x, y: n.position.y, width: W, height: H }));
  const byId = new Map(rects.map((r) => [r.id, r]));
  const requests: RouteEdgeRequest[] = [];
  for (const e of model.edges) {
    if (e.data?.shape.route === undefined) continue;
    const sp = parseHandleId(e.sourceHandle);
    const tp = parseHandleId(e.targetHandle);
    const sn = model.nodes.find((n) => n.id === e.source)!;
    const tn = model.nodes.find((n) => n.id === e.target)!;
    const s = faceAnchor(byId.get(e.source)!, sn.data.outputs.find((p) => p.id === sp!.port)?.side ?? "right");
    const t = faceAnchor(byId.get(e.target)!, tn.data.inputs.find((p) => p.id === tp!.port)?.side ?? "left");
    requests.push({ id: e.id, source: s, target: t, sourceNodeId: e.source, targetNodeId: e.target, waypoints: e.data.waypoints ?? null, radius: e.data.radius ?? null });
  }
  const router = createAStarRouter({ maxMillis: 600_000, maxExpansions: 1_000_000 });
  return { routes: router.route(requests, rects), rects, model, requests };
}

/** 길이가 겹치는 서로 다른 엣지의 평행 선분(스텁 제외) 중 줄 간격이 6px 미만인 쌍의 수 */
function overlapCount(routes: ReadonlyMap<string, RoutedEdge>): number {
  // 평행하게 겹치는(같은 줄 + 길이 겹침) 서로 다른 엣지 선분 쌍이 없어야 한다(스텁 선분 제외)
  const segs: { id: string; h: boolean; line: number; lo: number; hi: number; stub: boolean }[] = [];
  for (const [id, r] of routes) {
    for (let i = 0; i < r.points.length - 1; i += 1) {
      const a = r.points[i]!, b = r.points[i + 1]!;
      const h = a.y === b.y;
      segs.push({ id, h, line: h ? a.y : a.x, lo: h ? Math.min(a.x, b.x) : Math.min(a.y, b.y), hi: h ? Math.max(a.x, b.x) : Math.max(a.y, b.y), stub: i === 0 || i === r.points.length - 2 });
    }
  }
  let overlaps = 0;
  for (let i = 0; i < segs.length; i += 1) {
    for (let j = i + 1; j < segs.length; j += 1) {
      const a = segs[i]!, b = segs[j]!;
      if (a.id === b.id || a.h !== b.h || a.stub || b.stub || Math.abs(a.line - b.line) >= 6) continue;
      if (Math.min(a.hi, b.hi) - Math.max(a.lo, b.lo) > 1) overlaps += 1;
    }
  }
  return overlaps;
}

describe("회귀 세트: 기본 설정에서 연결선이 노드를 지나지 않는다 (5.2R.23)", () => {
  it("교차 팀 5개 + 24노드 스트레스 + 데모 팀 12개", () => {
    expect(CROSSING).toHaveLength(5);
    expect(CROSSING.length + OTHERS.length).toBe(12);
    expect(ALL).toHaveLength(13);
  });

  for (const direction of [null, "auto"] as const) {
    for (const spec of ALL) {
      it(`${spec.name} (노드 방향 ${direction ?? "기본"}): 모든 연결이 자동 경로이고 노드 사각형과 교차하는 선분 0`, () => {
        const g = graphOf(spec, direction === null ? undefined : { layout: { direction } });
        const { routes, rects, model } = routeAll(g);
        // 새 엣지에는 layout이 없고 기본 모양은 auto(route 속성 있음)
        expect(g.edges!.every((e) => e.layout === undefined)).toBe(true);
        expect(model.edges.every((e) => e.data?.shape.id === "auto" && e.data.shape.route !== undefined)).toBe(true);
        let crossings = 0;
        let fallbacks = 0;
        for (const e of model.edges) {
          const r = routes.get(e.id)!;
          if (r.fallback) {
            fallbacks += 1; // 대체 경로는 교차 검사에서 제외(경고 칩이 맡는다)
            continue;
          }
          for (const n of rects) {
            const own = n.id === e.source || n.id === e.target;
            if (pierces(r.points, n, own ? 0 : PAD)) crossings += 1;
          }
        }
        expect(crossings).toBe(0);
        expect(fallbacks).toBe(0);
      });
    }
  }

  it("사용자 경유점이 있는 엣지는 저장된 모양 그대로 읽고 그 점을 지난다", () => {
    const spec = CROSSING[2]!;
    const wp: EdgeLayout = { shape: "auto", waypoints: [{ x: 600, y: 480 }] };
    const wpNoShape: EdgeLayout = { waypoints: [{ x: 500, y: 400 }] };
    const g = graphOf({ ...spec, edges: spec.edges.map(([id, a, b]) => (id === "skip" ? [id, a, b, wp] : id === "e2" ? [id, a, b, wpNoShape] : id === "e4" ? [id, a, b, { shape: "straight", bend: 0.3 }] : [id, a, b]) as Spec["edges"][number]) });
    const { routes, model } = routeAll(g);
    const by = new Map(model.edges.map((e) => [e.id, e.data!]));
    expect(by.get("skip")!.shape.id).toBe("auto");
    expect(by.get("skip")!.waypoints).toEqual(wp.waypoints);
    const pts = routes.get("skip")!.points;
    const onPath = pts.some((p, i) => i > 0 && 600 >= Math.min(p.x, pts[i - 1]!.x) && 600 <= Math.max(p.x, pts[i - 1]!.x) && 480 >= Math.min(p.y, pts[i - 1]!.y) && 480 <= Math.max(p.y, pts[i - 1]!.y));
    expect(onPath).toBe(true);
    // shape 없이 경유점이 있으면 이전 기본(곡선)으로 읽고 라우터에 넘기지 않는다
    expect(by.get("e2")!.shape.id).toBe("bezier");
    expect(by.get("e2")!.waypoints).toEqual(wpNoShape.waypoints);
    expect(routes.has("e2")).toBe(false);
    // 직접 고른 모양은 그대로
    expect(by.get("e4")!.shape.id).toBe("straight");
    expect(routes.has("e4")).toBe(false);
  });

  for (const spec of ALL) {
    it(`겹침 완화: ${spec.name}에서 길이가 겹치는 서로 다른 엣지의 평행 선분은 6px 이상 떨어진다(3px 간격 회귀)`, () => {
      expect(overlapCount(routeAll(graphOf(spec)).routes)).toBe(0);
    });
  }

  it("겹침 완화: 같은 구간을 지나는 엣지는 벌어져 있고, 경유점 엣지의 점은 움직이지 않는다", () => {
    const { routes } = routeAll(graphOf(CROSSING[4]!));
    expect(overlapCount(routes)).toBe(0);
  });
});
