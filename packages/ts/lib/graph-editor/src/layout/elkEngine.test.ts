import { describe, expect, it, vi } from "vitest";
import { createElkEngine, toElkGraph } from "./elkEngine";
import type { ElkInstance } from "./elkEngine";
import { coerceOptionValues, defaultOptionValues } from "./types";
import type { LayoutRequest } from "./types";

/** 진짜 ELK를 메인 스레드용 번들로 불러온다(워커 없이 Node에서 계산). */
const realElk = async (): Promise<ElkInstance> => {
  const mod = (await import("elkjs/lib/elk.bundled.js")) as unknown as { default: new () => ElkInstance };
  return new mod.default();
};

const req = (flow: LayoutRequest["flow"]): LayoutRequest => ({
  nodes: [
    { id: "a", x: 0, y: 0, width: 100, height: 40, ports: [{ id: "out", io: "out", side: flow }] },
    { id: "b", x: 0, y: 0, width: 100, height: 40, ports: [{ id: "in", io: "in", side: flow === "right" ? "left" : "top" }] },
    { id: "c", x: 0, y: 0, width: 100, height: 40, ports: [{ id: "in", io: "in", side: flow === "right" ? "left" : "top" }] },
  ],
  edges: [
    { id: "e1", kind: "k", source: { node: "a", port: "out" }, target: { node: "b", port: "in" } },
    { id: "e2", kind: "k", source: { node: "b", port: "missing" }, target: { node: "c", port: "in" } },
  ],
  flow,
  options: { nodeGap: 40, layerGap: 100 },
});

describe("옵션 선언 도우미", () => {
  it("기본값과 걸러내기", () => {
    const e = createElkEngine({ load: realElk });
    expect(defaultOptionValues(e.options)).toEqual({ nodeGap: 48, layerGap: 80 });
    expect(coerceOptionValues(e.options, { nodeGap: 9999, layerGap: 64, junk: 1 })).toEqual({ nodeGap: 48, layerGap: 64 });
    expect(coerceOptionValues(e.options, "x")).toEqual({ nodeGap: 48, layerGap: 80 });
  });
});

describe("toElkGraph", () => {
  it("방향·포트 면 고정·없는 포트는 노드에 직접 연결", () => {
    const g = toElkGraph(req("bottom"));
    expect(g.layoutOptions?.["elk.direction"]).toBe("DOWN");
    expect(g.layoutOptions?.["elk.algorithm"]).toBe("layered");
    expect(g.layoutOptions?.["elk.edgeRouting"]).toBe("ORTHOGONAL");
    expect(g.layoutOptions?.["elk.spacing.nodeNode"]).toBe("40");
    expect(g.children?.[0]?.layoutOptions?.["elk.portConstraints"]).toBe("FIXED_SIDE");
    expect(g.children?.[0]?.ports?.[0]?.layoutOptions?.["elk.port.side"]).toBe("SOUTH");
    expect(g.edges?.[1]?.sources).toEqual(["b"]); // b에 "missing" 포트가 없음
    expect(g.edges?.[0]?.sources[0]).toMatch(/^p0\./);
  });
});

describe("권장 연결선 모양 선언 (4R.20)", () => {
  it("기본은 자동 경로를 처음부터 권한다(데이터라 덮어쓸 수 있다)", () => {
    expect(createElkEngine().edgeShapeOption).toEqual({ shapeId: "auto", default: true });
    expect(createElkEngine({ edgeShapeOption: { shapeId: "smoothstep", default: false } }).edgeShapeOption).toEqual({ shapeId: "smoothstep", default: false });
  });
  it("null이면 선언하지 않는다", () => {
    expect(createElkEngine({ edgeShapeOption: null })).not.toHaveProperty("edgeShapeOption");
  });
});

describe("createElkEngine (진짜 ELK)", () => {
  it("오른쪽 흐름이면 소스에서 타깃으로 x가 커진다", async () => {
    const e = createElkEngine({ load: realElk });
    const { positions } = await e.run(req("right"));
    expect(Object.keys(positions).sort()).toEqual(["a", "b", "c"]);
    expect(positions["a"]!.x).toBeLessThan(positions["b"]!.x);
    expect(positions["b"]!.x).toBeLessThan(positions["c"]!.x);
  });
  it("아래 흐름이면 y가 커진다", async () => {
    const e = createElkEngine({ load: realElk });
    const { positions } = await e.run(req("bottom"));
    expect(positions["a"]!.y).toBeLessThan(positions["b"]!.y);
  });
  it("위/왼쪽 흐름은 거꾸로", async () => {
    const e = createElkEngine({ load: realElk });
    const up = await e.run(req("top"));
    expect(up.positions["a"]!.y).toBeGreaterThan(up.positions["b"]!.y);
    const left = await e.run(req("left"));
    expect(left.positions["a"]!.x).toBeGreaterThan(left.positions["b"]!.x);
  });
  it("엔진 id·제목·옵션 제목 덮어쓰기", () => {
    const e = createElkEngine({ load: realElk, id: "mine", title: "내 엔진", optionTitles: { nodeGap: "간격" } });
    expect(e.id).toBe("mine");
    expect(e.title).toBe("내 엔진");
    expect(e.options.find((o) => o.key === "nodeGap")?.title).toBe("간격");
  });
});

describe("생애주기", () => {
  const fake = (layout: ElkInstance["layout"]): ElkInstance & { terminated: number } => {
    const inst = { terminated: 0, layout, terminateWorker() { inst.terminated += 1; } };
    return inst;
  };
  it("인스턴스는 한 번만 만들어 재사용한다", async () => {
    const inst = fake(async (g) => ({ ...g, children: [{ id: "a", x: 1, y: 2 }] }));
    const load = vi.fn(async () => inst);
    const e = createElkEngine({ load });
    await e.run(req("right"));
    await e.run(req("right"));
    expect(load).toHaveBeenCalledTimes(1);
  });
  it("중단하면 AbortError로 거부하고 워커를 종료하며 다음에 새로 만든다", async () => {
    const hang = fake(() => new Promise(() => undefined));
    const ok = fake(async (g) => ({ ...g, children: [{ id: "a", x: 0, y: 0 }] }));
    const load = vi.fn().mockResolvedValueOnce(hang).mockResolvedValueOnce(ok);
    const e = createElkEngine({ load });
    const ctl = new AbortController();
    const p = e.run(req("right"), ctl.signal);
    await Promise.resolve();
    ctl.abort();
    await expect(p).rejects.toMatchObject({ name: "AbortError" });
    await vi.waitFor(() => expect(hang.terminated).toBe(1));
    await e.run(req("right"));
    expect(load).toHaveBeenCalledTimes(2);
  });
  it("이미 중단된 신호면 바로 거부한다", async () => {
    const e = createElkEngine({ load: realElk });
    const ctl = new AbortController();
    ctl.abort();
    await expect(e.run(req("right"), ctl.signal)).rejects.toMatchObject({ name: "AbortError" });
  });
  it("로드 실패는 그대로 거부하고 다음 시도에서 다시 로드한다", async () => {
    const ok = fake(async (g) => ({ ...g, children: [{ id: "a", x: 0, y: 0 }] }));
    const load = vi.fn().mockRejectedValueOnce(new Error("load failed")).mockResolvedValueOnce(ok);
    const e = createElkEngine({ load });
    await expect(e.run(req("right"))).rejects.toThrow("load failed");
    await expect(e.run(req("right"))).resolves.toBeTruthy();
    expect(load).toHaveBeenCalledTimes(2);
  });
});

describe("되돌아가는 연결 (5R.16, 진짜 ELK)", () => {
  /** a → b → c, 되돌림 b → a. 노드 입력 순서는 일부러 뒤집는다. */
  const loopReq = (flow: LayoutRequest["flow"], withBack = true): LayoutRequest => {
    const inSide: LayoutRequest["flow"] = flow === "right" ? "left" : flow === "left" ? "right" : flow === "bottom" ? "top" : "bottom";
    const node = (id: string) => ({ id, x: 0, y: 0, width: 100, height: 40, ports: [{ id: "in", io: "in" as const, side: inSide }, { id: "out", io: "out" as const, side: flow }] });
    return {
      nodes: [node("c"), node("b"), node("a")],
      edges: [
        { id: "e1", kind: "k", source: { node: "a", port: "out" }, target: { node: "b", port: "in" } },
        { id: "e2", kind: "k", source: { node: "b", port: "out" }, target: { node: "c", port: "in" } },
        ...(withBack ? [{ id: "r", kind: "back", source: { node: "b", port: "out" }, target: { node: "a", port: "in" }, back: true }] : []),
      ],
      flow,
      options: { nodeGap: 40, layerGap: 100 },
    };
  };
  it("되돌아가는 연결이 없으면 ELK 입력이 이전과 같다(사이클 끊기 옵션·노드 순서 변경 없음)", () => {
    const g = toElkGraph(loopReq("right", false));
    expect(g.layoutOptions).not.toHaveProperty("elk.layered.cycleBreaking.strategy");
    expect(g.children?.map((c) => c.id)).toEqual(["c", "b", "a"]);
  });
  it("있으면 노드를 되돌림 제외 위상 순서로 주고 MODEL_ORDER(또는 지정 전략)를 쓴다", () => {
    const g = toElkGraph(loopReq("right"));
    expect(g.children?.map((c) => c.id)).toEqual(["a", "b", "c"]);
    expect(g.layoutOptions?.["elk.layered.cycleBreaking.strategy"]).toBe("MODEL_ORDER");
    expect(toElkGraph(loopReq("right"), { cycleBreaking: "GREEDY" }).layoutOptions?.["elk.layered.cycleBreaking.strategy"]).toBe("GREEDY");
    expect(toElkGraph(loopReq("right"), { includeBack: false }).edges?.map((e) => e.id)).toEqual(["e1", "e2"]);
  });
  it.each(["right", "left", "bottom", "top"] as const)("%s 흐름: 되돌림 도착 노드가 출발 노드보다 앞 층에 놓인다", async (flow) => {
    const e = createElkEngine({ load: realElk });
    const { positions } = await e.run(loopReq(flow));
    const axis = flow === "right" || flow === "left" ? "x" : "y";
    const dir = flow === "right" || flow === "bottom" ? 1 : -1;
    expect((positions["b"]![axis] - positions["a"]![axis]) * dir).toBeGreaterThan(0);
    expect((positions["c"]![axis] - positions["b"]![axis]) * dir).toBeGreaterThan(0);
  });
  it("엔진이 제자리로 되돌려 놓으면 되돌림 연결을 빼고 다시 계산한다", async () => {
    const calls: number[] = [];
    const fake: ElkInstance = {
      terminateWorker() {},
      async layout(g) {
        calls.push(g.edges?.length ?? 0);
        // 되돌림 연결이 있으면 도착 노드를 뒤로 보내는 나쁜 결과, 없으면 정상 결과
        const bad = (g.edges?.length ?? 0) === 3;
        return { ...g, children: [{ id: "a", x: bad ? 500 : 0, y: 0 }, { id: "b", x: 200, y: 0 }, { id: "c", x: 400, y: 0 }] };
      },
    };
    const { positions } = await createElkEngine({ load: async () => fake }).run(loopReq("right"));
    expect(calls).toEqual([3, 2]);
    expect(positions["a"]!.x).toBe(0);
  });
});
