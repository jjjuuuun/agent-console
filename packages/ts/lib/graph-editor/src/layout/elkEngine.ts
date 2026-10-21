/**
 * ELK(elkjs) 배치 엔진 어댑터(graph-edges §4.4, 결정 E-5). ELK 타입과 `elk.*` 옵션 문자열은 이 파일 밖으로 나가지 않는다.
 *
 * - elkjs는 동적 import로 처음 [정리]를 계산할 때만 불러오고, 계산은 Web Worker에서 한다(UI를 막지 않음).
 * - 워커를 만들 수 없는 환경(테스트·SSR)이나 다른 번들 방식이면 `load`로 ELK 인스턴스를 직접 준다.
 * - 중단(`signal`)하면 워커를 종료하고 다음 계산 때 새로 만든다.
 * - 결과는 노드 좌표만 쓴다(경유점은 가져오지 않는다. 경로는 자동 경로 라우터가 그린다).
 * - 되돌아가는 연결(`LayoutEdgeInput.back`)이 있으면 노드 입력 순서를 "되돌아가는 연결을 뺀 위상 순서"로 주고 사이클 끊기 전략
 *   (기본 `MODEL_ORDER`)으로 계산한다. 그래도 되돌아가는 연결의 도착 노드가 출발 노드보다 앞 층에 놓이지 않으면
 *   그 연결을 층 계산에서 빼고 한 번 더 계산한다(연결선 자체는 앱이 그린다). 되돌아가는 연결이 없으면 입력·결과가 이전과 같다.
 */
import type { Side } from "../shapes/types";
import type { EdgeShapeOption, LayoutEngineDescriptor, LayoutRequest, LayoutResult, OptionDecl } from "./types";

/** ELK 인스턴스 중 우리가 쓰는 부분(구조적 타입이라 elkjs 타입이 밖으로 새지 않는다). */
export interface ElkInstance {
  layout(graph: ElkGraph): Promise<ElkGraph>;
  terminateWorker(): void;
}

interface ElkGraph {
  id: string;
  layoutOptions?: Record<string, string>;
  children?: {
    id: string;
    x?: number;
    y?: number;
    width?: number;
    height?: number;
    layoutOptions?: Record<string, string>;
    ports?: { id: string; layoutOptions?: Record<string, string> }[];
  }[];
  edges?: { id: string; sources: string[]; targets: string[] }[];
}

export interface ElkEngineOptions {
  /** 엔진 id(기본 `elk-layered`) */
  id?: string;
  title?: string;
  /** ELK 인스턴스를 만든다. 생략하면 elkjs를 동적 import하고 Web Worker로 계산한다. 한 번만 호출하고 재사용한다 */
  load?: () => Promise<ElkInstance>;
  /** `load` 생략 시 워커를 만드는 함수(기본: elkjs의 `elk-worker.min.js`를 가리키는 `new Worker(new URL(...))`) */
  workerFactory?: () => Worker;
  /** 옵션 선언의 제목을 바꿀 때(번역). 키 → 제목 */
  optionTitles?: Readonly<Record<string, string>>;
  /**
   * 되돌아가는 연결이 있을 때 쓰는 ELK 사이클 끊기 전략(엔진 디스크립터 데이터). 기본 `MODEL_ORDER`.
   * 값은 ELK의 `cycleBreaking.strategy` 이름(`GREEDY`·`DEPTH_FIRST`·`MODEL_ORDER` 등)이다.
   */
  cycleBreaking?: string;
  /** 권장 연결선 모양 선언(기본: 자동 경로 `auto`, 처음부터 체크). `null`이면 팝오버에 체크를 두지 않는다 */
  edgeShapeOption?: EdgeShapeOption | null;
}

export const ELK_ENGINE_ID = "elk-layered";

const DIRECTION: Readonly<Record<Side, string>> = { right: "RIGHT", bottom: "DOWN", left: "LEFT", top: "UP" };
const PORT_SIDE: Readonly<Record<Side, string>> = { left: "WEST", right: "EAST", top: "NORTH", bottom: "SOUTH" };

/** 옵션 선언(키는 UI·저장용 이름이고 ELK 옵션 이름은 어댑터 안에서만 쓴다). */
export const ELK_OPTION_DECLS: readonly OptionDecl[] = [
  { key: "nodeGap", title: "노드 사이 간격", type: "number", default: 48, min: 8, max: 400, step: 8 },
  { key: "layerGap", title: "층 사이 간격", type: "number", default: 80, min: 8, max: 600, step: 8 },
];

/** ELK는 노드 좌표만 정하고 경로는 자동 경로 라우터가 그리므로(§4.4) 기본으로 자동 경로를 권한다. */
export const ELK_EDGE_SHAPE_OPTION: EdgeShapeOption = { shapeId: "auto", default: true };

/** 흐름 방향으로 도착 노드가 출발 노드보다 앞에 놓였는지(모든 되돌아가는 연결). */
export function backEdgesPointBack(req: LayoutRequest, positions: Readonly<Record<string, { x: number; y: number }>>): boolean {
  const sign: Readonly<Record<Side, { axis: "x" | "y"; dir: 1 | -1 }>> = { right: { axis: "x", dir: 1 }, left: { axis: "x", dir: -1 }, bottom: { axis: "y", dir: 1 }, top: { axis: "y", dir: -1 } };
  const { axis, dir } = sign[req.flow];
  return req.edges
    .filter((e) => e.back === true)
    .every((e) => {
      const s = positions[e.source.node];
      const t = positions[e.target.node];
      if (s === undefined || t === undefined || e.source.node === e.target.node) return true;
      return (t[axis] - s[axis]) * dir < 0;
    });
}

const abortError = (): Error => {
  const e = new Error("aborted");
  e.name = "AbortError";
  return e;
};

const num = (v: unknown, fallback: number): number => (typeof v === "number" && Number.isFinite(v) ? v : fallback);

export interface ToElkOptions {
  /** 사이클 끊기 전략(되돌아가는 연결이 있을 때만 쓴다). 기본 `MODEL_ORDER` */
  cycleBreaking?: string;
  /** false면 되돌아가는 연결을 입력에서 뺀다(층 계산 제외). 기본 true */
  includeBack?: boolean;
}

/** 되돌아가는 연결을 뺀 위상 순서(안정: 같은 단계에서는 입력 순서). 순환이 남으면 나머지는 입력 순서로 뒤에 붙인다. */
function flowOrder(req: LayoutRequest): string[] {
  const ids = req.nodes.map((n) => n.id);
  const known = new Set(ids);
  const indeg = new Map(ids.map((id) => [id, 0]));
  const next = new Map<string, string[]>();
  for (const e of req.edges) {
    if (e.back === true || !known.has(e.source.node) || !known.has(e.target.node) || e.source.node === e.target.node) continue;
    indeg.set(e.target.node, (indeg.get(e.target.node) ?? 0) + 1);
    next.set(e.source.node, [...(next.get(e.source.node) ?? []), e.target.node]);
  }
  const out: string[] = [];
  const done = new Set<string>();
  for (let progress = true; progress && out.length < ids.length; ) {
    progress = false;
    for (const id of ids) {
      if (done.has(id) || (indeg.get(id) ?? 0) > 0) continue;
      done.add(id);
      out.push(id);
      for (const n of next.get(id) ?? []) indeg.set(n, (indeg.get(n) ?? 1) - 1);
      progress = true;
      break; // 가장 앞선 준비된 노드부터 한 개씩(입력 순서 유지)
    }
  }
  for (const id of ids) if (!done.has(id)) out.push(id);
  return out;
}

/** 요청 → ELK 그래프. 포트는 면 고정(`FIXED_SIDE`)이고, 목록에 없는 포트에 걸린 엣지는 노드에 직접 붙인다. */
export function toElkGraph(req: LayoutRequest, opts: ToElkOptions = {}): ElkGraph {
  const includeBack = opts.includeBack !== false;
  const hasBack = req.edges.some((e) => e.back === true);
  const portIds = new Map<string, string>();
  let nodesIn = req.nodes;
  if (hasBack) {
    const order = flowOrder(req);
    const byId = new Map(req.nodes.map((n) => [n.id, n]));
    nodesIn = order.map((id) => byId.get(id) as (typeof req.nodes)[number]);
  }
  const children = nodesIn.map((n, ni) => ({
    id: n.id,
    width: n.width,
    height: n.height,
    layoutOptions: { "elk.portConstraints": "FIXED_SIDE" },
    ports: n.ports.map((p, pi) => {
      const id = `p${ni}.${pi}`;
      portIds.set(`${n.id}\u0000${p.io}\u0000${p.id}`, id);
      return { id, layoutOptions: { "elk.port.side": PORT_SIDE[p.side], "elk.port.index": String(pi) } };
    }),
  }));
  const known = new Set(req.nodes.map((n) => n.id));
  return {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": DIRECTION[req.flow],
      "elk.edgeRouting": "ORTHOGONAL",
      "elk.spacing.nodeNode": String(num(req.options["nodeGap"], 48)),
      "elk.layered.spacing.nodeNodeBetweenLayers": String(num(req.options["layerGap"], 80)),
      ...(hasBack && includeBack ? { "elk.layered.cycleBreaking.strategy": opts.cycleBreaking ?? "MODEL_ORDER" } : {}),
    },
    children,
    edges: req.edges
      .filter((e) => known.has(e.source.node) && known.has(e.target.node) && (includeBack || e.back !== true))
      .map((e) => ({
        id: e.id,
        sources: [portIds.get(`${e.source.node}\u0000out\u0000${e.source.port}`) ?? e.source.node],
        targets: [portIds.get(`${e.target.node}\u0000in\u0000${e.target.port}`) ?? e.target.node],
      })),
  };
}

async function defaultLoad(workerFactory: (() => Worker) | undefined): Promise<ElkInstance> {
  const mod = await import("elkjs/lib/elk-api");
  const Elk = mod.default;
  const factory = workerFactory ?? (() => new Worker(new URL("elkjs/lib/elk-worker.min.js", import.meta.url)));
  return new Elk({ workerFactory: factory }) as unknown as ElkInstance;
}

/** ELK 계층형 배치 엔진 디스크립터를 만든다. 인스턴스는 처음 `run`에서 만들고 중단·오류 때 버린다. */
export function createElkEngine(options: ElkEngineOptions = {}): LayoutEngineDescriptor {
  let instance: Promise<ElkInstance> | null = null;
  const load = options.load ?? (() => defaultLoad(options.workerFactory));
  const titles = options.optionTitles ?? {};
  const drop = (): void => {
    const cur = instance;
    instance = null;
    void cur?.then((i) => i.terminateWorker()).catch(() => undefined);
  };
  return {
    id: options.id ?? ELK_ENGINE_ID,
    title: options.title ?? "ELK 계층형",
    options: ELK_OPTION_DECLS.map((o) => ({ ...o, title: titles[o.key] ?? o.title })),
    ...(options.edgeShapeOption === null ? {} : { edgeShapeOption: options.edgeShapeOption ?? ELK_EDGE_SHAPE_OPTION }),
    async run(req: LayoutRequest, signal?: AbortSignal): Promise<LayoutResult> {
      if (signal?.aborted === true) throw abortError();
      instance ??= load();
      const pending = instance;
      let onAbort: (() => void) | undefined;
      const aborted = new Promise<never>((_, reject) => {
        onAbort = () => {
          drop();
          reject(abortError());
        };
        signal?.addEventListener("abort", onAbort, { once: true });
      });
      try {
        const elk = await Promise.race([pending, aborted]);
        const cycleBreaking = options.cycleBreaking;
        const run = async (includeBack: boolean) => {
          const out = await Promise.race([elk.layout(toElkGraph(req, { includeBack, ...(cycleBreaking !== undefined ? { cycleBreaking } : {}) })), aborted]);
          const positions: Record<string, { x: number; y: number }> = {};
          for (const c of out.children ?? []) positions[c.id] = { x: c.x ?? 0, y: c.y ?? 0 };
          return positions;
        };
        let positions = await run(true);
        // 되돌아가는 연결의 도착 노드가 출발 노드보다 앞 층이 아니면 그 연결을 층 계산에서 빼고 다시 계산한다.
        if (req.edges.some((e) => e.back === true) && !backEdgesPointBack(req, positions)) positions = await run(false);
        return { positions };
      } catch (e) {
        if (!(e instanceof Error && e.name === "AbortError")) {
          if (instance === pending) drop(); // 로드·계산 오류: 다음 시도에서 새로 만든다
        }
        throw e;
      } finally {
        if (onAbort !== undefined) signal?.removeEventListener("abort", onAbort);
        aborted.catch(() => undefined);
      }
    },
  };
}
